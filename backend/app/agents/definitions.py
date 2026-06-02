"""Declarative agent definitions.

An agent is just data: a name, the prompt key (resolved via prompts.get_prompt, which
prefers Langfuse), the tools it may call, and its model tier. Adding a new agent in later
phases means adding an entry here + a prompt — no new control flow.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AgentDef:
    name: str
    prompt_key: str
    tools: list[str] = field(default_factory=list)
    model: str = "claude-haiku-4-5"


AGENTS: dict[str, AgentDef] = {
    "plot": AgentDef(
        name="plot",
        prompt_key="plot",
        tools=["search_movies", "get_movie_details"],
        model="claude-haiku-4-5",
    ),
    "reviews": AgentDef(
        name="reviews",
        prompt_key="reviews",
        tools=["search_movies", "get_movie_reviews"],
        model="claude-haiku-4-5",
    ),
    "recommend": AgentDef(
        name="recommend",
        prompt_key="recommender",
        # Recommendation needs more reasoning for slot-filling + taste matching.
        tools=["discover_movies", "search_movies", "get_movie_details"],
        model="claude-sonnet-4-6",
    ),
    "smalltalk": AgentDef(
        name="smalltalk",
        prompt_key="router",  # unused; smalltalk handled inline, see runner
        tools=[],
        model="claude-haiku-4-5",
    ),
}

DEFAULT_INTENT = "smalltalk"
