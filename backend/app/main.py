"""FastAPI entrypoint for the Movie Agent backend (Phase 1).

Endpoints:
  GET  /health   -> liveness + feature flags (llm/tracing/tmdb enabled?)
  POST /chat     -> routes to an agent and streams the reply as Server-Sent Events

Flow per turn:  router classifies intent -> specialized agent runs a tool-use loop ->
text streamed to the client. Echo mode is used when no ANTHROPIC_API_KEY is set.

Run locally:
  uvicorn app.main:app --reload --port 8000
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import uuid
from typing import Any, AsyncIterator, List, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .agents.router import route
from .agents.runner import run_agent
from .config import get_settings
from .observability import trace_chat

settings = get_settings()
app = FastAPI(title="Movie Agent API", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class Message(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    messages: List[Message]
    session_id: Optional[str] = None


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "llm_enabled": settings.llm_enabled,
        "tracing_enabled": settings.tracing_enabled,
        "tmdb_enabled": bool(settings.tmdb_api_key),
        "omdb_enabled": settings.omdb_enabled,
        "model": settings.anthropic_model if settings.llm_enabled else None,
    }


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def _echo_stream(text: str) -> AsyncIterator[str]:
    reply = (
        "(echo mode — no ANTHROPIC_API_KEY set) I can't route to the movie agents yet. "
        f"You said: {text}\n\nAdd ANTHROPIC_API_KEY (and TMDB_API_KEY) to backend/.env."
    )
    for word in reply.split(" "):
        yield word + " "
        await asyncio.sleep(0.01)


@app.post("/chat")
async def chat(req: ChatRequest) -> StreamingResponse:
    session_id = req.session_id or str(uuid.uuid4())
    history: list[dict[str, Any]] = [{"role": m.role, "content": m.content} for m in req.messages]
    last_user = next((m["content"] for m in reversed(history) if m["role"] == "user"), "")

    async def event_stream() -> AsyncIterator[str]:
        yield _sse("meta", {"session_id": session_id})

        # No LLM key -> echo mode so the pipeline still demonstrably works.
        if not settings.llm_enabled:
            async for chunk in _echo_stream(last_user):
                yield _sse("token", {"text": chunk})
            yield _sse("done", {})
            return

        with trace_chat(last_user, agent="router", session_id=session_id) as trace:
            full: list[str] = []
            try:
                agent = await route(history, trace=trace)
                yield _sse("agent", {"name": agent.name})
                with contextlib.suppress(Exception):
                    trace.update(metadata={"agent": agent.name})

                async for kind, text in run_agent(agent, history, trace=trace):
                    if kind == "token":
                        full.append(text)
                        yield _sse("token", {"text": text})
                    elif kind == "status":
                        yield _sse("status", {"text": text})
            except Exception as exc:
                yield _sse("error", {"message": str(exc)})
                return

            with contextlib.suppress(Exception):
                trace.update(output="".join(full))
            yield _sse("done", {})

    return StreamingResponse(event_stream(), media_type="text/event-stream")
