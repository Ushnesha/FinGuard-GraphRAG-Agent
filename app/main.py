# app/main.py
import os
import json
import urllib.request
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from agents.agentic import StateAgent
from services.semantic_cache import RedisCache
from app.models import QueryRequest
from services.telemetry import init_telemetry
init_telemetry()

app = FastAPI(title="Autonomous Enterprise Analyst API")

# Enable CORS for cross-origin requests (e.g. if running UI in another container or local dev server)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

import app.config as cfg

agent = StateAgent(llm_model=cfg.RETRIEVAL_LLM_MODEL)
cache = RedisCache()

@app.get("/api/v1/models")
async def list_available_models():
    return {"models": [cfg.RETRIEVAL_LLM_MODEL]}

@app.post("/api/v1/query")
async def handle_analyst_query(payload: QueryRequest):
    # Include selected model in cache key to partition cache by model
    cache_key = f"user:{payload.user_id}:model:{payload.model}:query:{hash(payload.query.strip().lower())}"
    
    # 1. Redis Caching Guard
    cached_val = cache.get(cache_key)
    if cached_val:
        if isinstance(cached_val, dict):
            return {
                "source": "redis_cache",
                "result": cached_val.get("result"),
                "tokens": cached_val.get("tokens", {"prompt_tokens": 0, "completion_tokens": 0})
            }
        return {
            "source": "redis_cache",
            "result": cached_val,
            "tokens": {"prompt_tokens": 0, "completion_tokens": 0}
        }

    # 2. Pipeline Execution
    try:
        execution_state = agent.run(payload.query, payload.model)
        tokens = execution_state.get("tokens", {"prompt_tokens": 0, "completion_tokens": 0})
        
        # If blocked by safety boundaries
        if not execution_state["is_safe"]:
            return {
                "source": "guardrail_shield",
                "result": "Request blocked by safety policy.",
                "tokens": tokens
            }
            
        output = execution_state["final_output"]
        
        # 3. Hydrate cache
        cache_data = {"result": output, "tokens": tokens}
        cache.set(cache_key, cache_data, ttl=3000) # Cache for 5 minutes
        
        return {"source": "live_compute_nodes", "result": output, "tokens": tokens}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal Server Pipeline Error: {str(e)}")

@app.get("/", response_class=HTMLResponse)
async def read_index():
    template_path = os.path.join(os.path.dirname(__file__), "templates", "index.html")
    try:
        with open(template_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read(), status_code=200)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="UI Template index.html not found. Make sure it is placed under app/templates/index.html.")
