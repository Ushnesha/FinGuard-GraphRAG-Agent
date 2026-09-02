import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import httpx
import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

from sidecar.config import settings

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.enable_debug_logging else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("VigilantAI-Sidecar")

# Hop-by-hop headers to filter when proxying
HOP_BY_HOP_HEADERS = {
    "host",
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "content-length",
}


class ProxyClient:
    """Manages the shared HTTP client for upstream proxying."""

    client: httpx.AsyncClient | None = None

    @classmethod
    def get_client(cls) -> httpx.AsyncClient:
        if cls.client is None or cls.client.is_closed:
            cls.client = httpx.AsyncClient(
                timeout=httpx.Timeout(settings.timeout_seconds, connect=10.0),
                limits=httpx.Limits(max_keepalive_connections=50, max_connections=200),
                follow_redirects=True,
            )
        return cls.client

    @classmethod
    async def close(cls):
        if cls.client is not None and not cls.client.is_closed:
            await cls.client.aclose()
            cls.client = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for application startup and shutdown."""
    logger.info("Initializing VigilantAI Sidecar Proxy...")
    logger.info("Target Backend LLM URL: %s", settings.target_llm_url)
    logger.info("Listening on: %s:%d", settings.sidecar_host, settings.sidecar_port)
    ProxyClient.get_client()
    yield
    logger.info("Shutting down VigilantAI Sidecar Proxy...")
    await ProxyClient.close()


app = FastAPI(
    title="VigilantAI Sidecar Proxy",
    description="Transparent LLM proxy for telemetry, drift analytics, and safety oversight.",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "VigilantAI Sidecar Proxy",
        "target_llm_url": settings.target_llm_url,
        "version": "0.1.0",
    }


def filter_request_headers(request: Request) -> dict[str, str]:
    """Filter out hop-by-hop headers before forwarding request to upstream LLM."""
    headers = {}
    for key, value in request.headers.items():
        if key.lower() not in HOP_BY_HOP_HEADERS:
            headers[key] = value
    return headers


def filter_response_headers(headers: httpx.Headers) -> dict[str, str]:
    """Filter out hop-by-hop headers before returning upstream response to client."""
    filtered = {}
    for key, value in headers.items():
        if key.lower() not in HOP_BY_HOP_HEADERS:
            filtered[key] = value
    return filtered


async def stream_generator(
    response: httpx.Response,
) -> AsyncGenerator[bytes, None]:
    """Asynchronously stream chunks from upstream LLM back to client."""
    try:
        async for chunk in response.aiter_raw():
            yield chunk
    finally:
        await response.aclose()


@app.api_route(
    "/{full_path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"],
)
async def proxy_wildcard(request: Request, full_path: str):
    """
    Wildcard route to intercept and forward all incoming OpenAI-compatible requests.
    Supports both standard JSON responses and SSE streaming responses transparently.
    """
    target_url = f"{settings.target_llm_url}/{full_path}"
    if request.url.query:
        target_url = f"{target_url}?{request.url.query}"

    headers = filter_request_headers(request)
    body = await request.body()
    client = ProxyClient.get_client()

    logger.debug("Proxying %s request to: %s", request.method, target_url)

    try:
        upstream_req = client.build_request(
            method=request.method,
            url=target_url,
            headers=headers,
            content=body if body else None,
        )
        upstream_resp = await client.send(upstream_req, stream=True)

    except httpx.ConnectError as e:
        logger.error("Failed to connect to upstream LLM at %s: %s", target_url, e)
        return JSONResponse(
            status_code=502,
            content={
                "error": {
                    "message": f"VigilantAI Sidecar: Failed to connect to backend LLM server at {settings.target_llm_url}.",
                    "type": "upstream_connection_error",
                    "code": 502,
                }
            },
        )
    except httpx.TimeoutException as e:
        logger.error("Timeout waiting for upstream LLM at %s: %s", target_url, e)
        return JSONResponse(
            status_code=504,
            content={
                "error": {
                    "message": f"VigilantAI Sidecar: Upstream LLM timed out after {settings.timeout_seconds} seconds.",
                    "type": "upstream_timeout_error",
                    "code": 504,
                }
            },
        )
    except Exception as e:
        logger.exception("Unexpected error while proxying to %s: %s", target_url, e)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "message": f"VigilantAI Sidecar Proxy Error: {str(e)}",
                    "type": "sidecar_internal_error",
                    "code": 500,
                }
            },
        )

    response_headers = filter_response_headers(upstream_resp.headers)
    content_type = upstream_resp.headers.get("content-type", "")

    # Check if streaming response (e.g., SSE / text/event-stream or chunked)
    is_streaming = (
        "text/event-stream" in content_type
        or "application/x-ndjson" in content_type
        or upstream_resp.headers.get("transfer-encoding", "").lower() == "chunked"
    )

    if is_streaming:
        logger.debug("Streaming response detected for path: %s", full_path)
        return StreamingResponse(
            stream_generator(upstream_resp),
            status_code=upstream_resp.status_code,
            headers=response_headers,
            media_type=content_type or "text/event-stream",
        )

    # Standard non-streaming response
    try:
        content = await upstream_resp.aread()
        return Response(
            content=content,
            status_code=upstream_resp.status_code,
            headers=response_headers,
            media_type=content_type,
        )
    finally:
        await upstream_resp.aclose()


if __name__ == "__main__":
    uvicorn.run(
        "sidecar.main:app",
        host=settings.sidecar_host,
        port=settings.sidecar_port,
        reload=True,
    )
