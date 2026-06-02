"""Intent router.

A fast, cheap Haiku call that classifies the latest user turn into one of the agent
intents. Returns the AgentDef to dispatch to. Falls back to 'recommend' or 'smalltalk'
heuristically if the model output can't be parsed.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from ..config import get_settings
from ..prompts import get_prompt
from .definitions import AGENTS, DEFAULT_INTENT, AgentDef

VALID = {"plot", "reviews", "recommend", "smalltalk"}


async def route(history: list[dict[str, Any]], trace: Optional[Any] = None) -> AgentDef:
    from anthropic import AsyncAnthropic

    settings = get_settings()
    client = AsyncAnthropic(api_key=settings.anthropic_api_key)

    # Give the router light context: last few turns, flattened to text.
    convo = "\n".join(
        f"{m['role']}: {m['content']}"
        for m in history[-6:]
        if isinstance(m.get("content"), str)
    )

    span = trace.span(name="router", input=convo) if trace else None
    try:
        resp = await client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=64,
            system=get_prompt("router"),
            messages=[{"role": "user", "content": convo}],
        )
        text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
        intent = _parse_intent(text)
    except Exception:
        intent = DEFAULT_INTENT

    if span is not None:
        span.end(output=intent)

    return AGENTS.get(intent, AGENTS[DEFAULT_INTENT])


def _parse_intent(text: str) -> str:
    text = text.strip()
    try:
        start, end = text.index("{"), text.rindex("}") + 1
        intent = json.loads(text[start:end]).get("intent", "")
    except (ValueError, json.JSONDecodeError):
        intent = text.lower()
    intent = intent.strip().lower()
    return intent if intent in VALID else DEFAULT_INTENT
