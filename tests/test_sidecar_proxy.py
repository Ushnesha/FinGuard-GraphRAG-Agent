import json
import pytest
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from sidecar.main import app, ProxyClient
from sidecar.config import settings

# Create a mock upstream LLM FastAPI application for testing
mock_upstream_app = FastAPI()


@mock_upstream_app.get("/v1/models")
async def mock_models():
    return {
        "object": "list",
        "data": [
            {"id": "meta-llama/Meta-Llama-3-8B-Instruct", "object": "model"},
            {"id": "mistralai/Mistral-7B-Instruct-v0.3", "object": "model"}
        ]
    }


@mock_upstream_app.post("/v1/chat/completions")
async def mock_chat_completions(request: Request):
    body = json.loads(await request.body())
    is_stream = body.get("stream", False)
    custom_node = request.headers.get("x-agent-node", "unknown")

    if is_stream:
        async def mock_stream_events():
            chunks = ["Hello", " ", "from", " ", "mock", " ", "vLLM!"]
            for chunk in chunks:
                event_data = {
                    "id": "chatcmpl-mock-123",
                    "object": "chat.completion.chunk",
                    "choices": [{"delta": {"content": chunk}, "index": 0, "finish_reason": None}],
                    "node": custom_node
                }
                yield f"data: {json.dumps(event_data)}\n\n".encode("utf-8")
            yield b"data: [DONE]\n\n"

        return StreamingResponse(mock_stream_events(), media_type="text/event-stream")

    return {
        "id": "chatcmpl-mock-123",
        "object": "chat.completion",
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": "Non-streaming test response from mock vLLM."
            },
            "finish_reason": "stop"
        }],
        "usage": {
            "prompt_tokens": 15,
            "completion_tokens": 8,
            "total_tokens": 23
        },
        "node_received": custom_node
    }


@pytest.fixture(autouse=True)
def setup_test_proxy():
    """Configure sidecar proxy to route to mock upstream app."""
    mock_transport = httpx.ASGITransport(app=mock_upstream_app)
    mock_client = httpx.AsyncClient(transport=mock_transport, base_url="http://mock-upstream")
    
    original_client = ProxyClient.client
    original_target_url = settings.target_llm_url
    
    ProxyClient.client = mock_client
    settings.target_llm_url = "http://mock-upstream"
    
    yield
    
    ProxyClient.client = original_client
    settings.target_llm_url = original_target_url


@pytest.mark.asyncio
async def test_sidecar_health_check():
    """Verify sidecar /health endpoint responds correctly."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "VigilantAI Sidecar Proxy"


@pytest.mark.asyncio
async def test_sidecar_non_streaming_proxy():
    """Verify non-streaming requests are transparently forwarded to upstream LLM."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "model": "meta-llama/Meta-Llama-3-8B-Instruct",
            "messages": [{"role": "user", "content": "Hello!"}],
            "stream": False
        }
        headers = {"x-agent-node": "supervisor_node", "Authorization": "Bearer mock-token"}
        
        response = await client.post("/v1/chat/completions", json=payload, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["choices"][0]["message"]["content"] == "Non-streaming test response from mock vLLM."
        assert data["node_received"] == "supervisor_node"
        assert data["usage"]["total_tokens"] == 23


@pytest.mark.asyncio
async def test_sidecar_streaming_proxy():
    """Verify SSE streaming requests are correctly yielded chunk-by-chunk."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "model": "meta-llama/Meta-Llama-3-8B-Instruct",
            "messages": [{"role": "user", "content": "Stream to me"}],
            "stream": True
        }
        headers = {"x-agent-node": "analyst_node"}
        
        response = await client.post("/v1/chat/completions", json=payload, headers=headers)
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        
        body_text = response.text
        assert "data: " in body_text
        assert "[DONE]" in body_text
        assert "mock" in body_text
        assert "vLLM!" in body_text


@pytest.mark.asyncio
async def test_sidecar_models_endpoint():
    """Verify GET requests (such as /v1/models) are transparently forwarded."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/v1/models")
        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) == 2
        assert data["data"][0]["id"] == "meta-llama/Meta-Llama-3-8B-Instruct"


@pytest.mark.asyncio
async def test_sidecar_upstream_connection_error():
    """Verify graceful 502 response when upstream LLM is unreachable."""
    ProxyClient.client = httpx.AsyncClient(base_url="http://127.0.0.1:59999")
    settings.target_llm_url = "http://127.0.0.1:59999"
    
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/v1/chat/completions", json={"model": "test"})
        assert response.status_code == 502
        data = response.json()
        assert "upstream_connection_error" in data["error"]["type"]
