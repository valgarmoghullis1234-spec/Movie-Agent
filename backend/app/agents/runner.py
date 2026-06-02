"""Generic agent runner: an Anthropic tool-use loop that streams output.

Given an AgentDef and the conversation history, it runs the standard agent loop:

    call Claude (with tools)  ->  if tool_use: run tools, feed results back, repeat
                              ->  else: done

Text deltas are streamed to the caller as ("token", str). Tool activity is surfaced as
("status", str) so the UI can show "🔎 Searching TMDB…". Designed to be swapped for a
LangGraph implementation later without changing the API contract.
"""
from __future__ import annotations

import json
from typing import Any, AsyncIterator, Optional

from ..config import get_settings
from ..prompts import get_prompt
from ..tools.registry import dispatch, schemas_for
from .definitions import AgentDef

MAX_ITERATIONS = 6  # guard against tool-call loops

_TOOL_LABELS = {
    "search_movies": "🔎 Searching movies",
    "get_movie_details": "📄 Fetching details",
    "get_movie_reviews": "⭐ Reading ratings & reviews",
    "discover_movies": "🎯 Finding recommendations",
}

SMALLTALK_PROMPT = (
    "You are MovieBot, a warm, concise movie companion. The user is making small talk or "
    "greeting you. Reply briefly and invite them to ask for a movie's plot, its reviews, or "
    "a recommendation. Do not use tools."
)


async def run_agent(
    agent: AgentDef,
    history: list[dict[str, Any]],
    trace: Optional[Any] = None,
) -> AsyncIterator[tuple[str, str]]:
    """Yield (event_type, text) pairs: 'token' for reply text, 'status' for tool activity."""
    from anthropic import AsyncAnthropic

    settings = get_settings()
    client = AsyncAnthropic(api_key=settings.anthropic_api_key)

    if agent.name == "smalltalk":
        system = SMALLTALK_PROMPT
        tools: list[dict[str, Any]] = []
    else:
        system = get_prompt(agent.prompt_key)
        tools = schemas_for(agent.tools)

    working: list[dict[str, Any]] = list(history)

    for _ in range(MAX_ITERATIONS):
        generation = None
        if trace is not None:
            generation = trace.generation(
                name=f"{agent.name}-llm",
                model=agent.model,
                input=working[-1] if working else None,
                metadata={"system_prompt": system, "tools": agent.tools},
            )

        collected: list[str] = []
        kwargs: dict[str, Any] = dict(
            model=agent.model,
            max_tokens=1024,
            system=system,
            messages=working,
        )
        if tools:
            kwargs["tools"] = tools

        async with client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                collected.append(text)
                yield ("token", text)
            final = await stream.get_final_message()

        if generation is not None:
            generation.end(output="".join(collected) or "[tool calls]")

        # Record the assistant turn (text + any tool_use blocks) for the next round.
        working.append(
            {"role": "assistant", "content": [b.model_dump() for b in final.content]}
        )

        if final.stop_reason != "tool_use":
            return

        # Execute each requested tool and feed results back.
        results: list[dict[str, Any]] = []
        for block in final.content:
            if getattr(block, "type", None) != "tool_use":
                continue
            label = _TOOL_LABELS.get(block.name, f"Using {block.name}")
            yield ("status", f"{label}…")
            span = trace.span(name=f"tool:{block.name}", input=block.input) if trace else None
            result = await dispatch(block.name, dict(block.input))
            if span is not None:
                span.end(output=result)
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result),
                }
            )
        working.append({"role": "user", "content": results})

    yield ("token", "\n\n(Stopped: too many tool calls.)")
