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
    "find_similar_movies": "🎬 Finding similar movies",
    "get_content_guidance": "👨‍👩‍👧 Checking content rating",
    "get_movie_facts": "🧠 Digging up movie facts",
    "get_streaming_availability": "📺 Checking where to stream",
}

SMALLTALK_PROMPT = (
    "You are MovieBot, a warm, concise movie companion. The user is making small talk or "
    "greeting you. Reply briefly and invite them to ask for a movie's plot, its reviews, or "
    "a recommendation. Do not use tools."
)

# Appended to every specialist agent's system prompt. The client renders Markdown, so
# keep formatting purposeful and restrained.
STYLE_GUIDE = (
    "\n\nFORMATTING: Your reply is rendered as Markdown. Use **bold** for titles/labels, "
    "Markdown tables for side-by-side comparisons, and '- ' bullet or numbered lists where "
    "they help. Do NOT open with a filler line like 'Let me look that up!' — answer "
    "directly. Use emoji sparingly: at most one or two in a reply, never one per line."
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
        system = get_prompt(agent.prompt_key) + STYLE_GUIDE
        tools = schemas_for(agent.tools)

    working: list[dict[str, Any]] = list(history)

    # When an iteration produces text and then calls a tool, the next iteration's text
    # would butt right up against it ("…right away!Here are…"). This flag inserts a blank
    # line between the two text segments the first time the next one streams.
    pending_separator = False

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
                if pending_separator:
                    yield ("token", "\n\n")
                    pending_separator = False
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

        # If this iteration emitted text, separate it from any later text segment.
        if collected:
            pending_separator = True

        # Split tool calls: present_choices is a UI action handled here (not dispatched);
        # everything else is a real data tool that gets executed and fed back.
        choice_block = None
        data_blocks: list[Any] = []
        for block in final.content:
            if getattr(block, "type", None) != "tool_use":
                continue
            if block.name == "present_choices":
                choice_block = block
            else:
                data_blocks.append(block)

        if choice_block is not None:
            options = []
            if isinstance(choice_block.input, dict):
                options = choice_block.input.get("options", []) or []
            yield ("choices", json.dumps({"options": options}))

        # No real tools to run -> the question text streamed and buttons are shown;
        # end the turn and wait for the user to tap a choice.
        if not data_blocks:
            return

        # Otherwise run the real tools and feed results back (satisfying present_choices
        # too, since the API requires a result for every tool_use in the turn).
        results: list[dict[str, Any]] = []
        if choice_block is not None:
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": choice_block.id,
                    "content": json.dumps({"ok": True}),
                }
            )
        for block in data_blocks:
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
