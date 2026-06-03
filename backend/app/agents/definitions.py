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
        tools=["search_movies", "get_movie_details", "present_choices"],
        model="claude-haiku-4-5",
    ),
    "reviews": AgentDef(
        name="reviews",
        prompt_key="reviews",
        tools=["search_movies", "get_movie_reviews", "present_choices"],
        model="claude-haiku-4-5",
    ),
    "recommend": AgentDef(
        name="recommend",
        prompt_key="recommender",
        # Recommendation needs more reasoning for slot-filling + taste matching.
        tools=["discover_movies", "search_movies", "get_movie_details"],
        model="claude-sonnet-4-6",
    ),
    "streaming": AgentDef(
        name="streaming",
        prompt_key="streaming",
        # Where-to-watch. TMDB/JustWatch watch-providers; search to resolve the title.
        tools=["search_movies", "get_streaming_availability", "present_choices"],
        model="claude-haiku-4-5",
    ),
    "tonight": AgentDef(
        name="tonight",
        prompt_key="tonight",
        # Mood-based instant pick — maps a vibe to genres and returns fast. Reuses discover.
        tools=["discover_movies", "present_choices"],
        model="claude-haiku-4-5",
    ),
    "trivia": AgentDef(
        name="trivia",
        prompt_key="trivia",
        # Quiz/trivia. OMDb-backed facts — multi-turn (ask → user answers → grade).
        tools=["get_movie_facts", "present_choices"],
        model="claude-haiku-4-5",
    ),
    "parental": AgentDef(
        name="parental",
        prompt_key="parental",
        # Family-safety check. OMDb-backed (certification) — needs no TMDB.
        tools=["get_content_guidance"],
        model="claude-haiku-4-5",
    ),
    "similar": AgentDef(
        name="similar",
        prompt_key="similar",
        # "If you liked X…" — resolve the seed title, then fetch taste-based picks.
        tools=["search_movies", "find_similar_movies", "present_choices"],
        model="claude-haiku-4-5",
    ),
    "compare": AgentDef(
        name="compare",
        prompt_key="compare",
        # Comparison reuses the existing detail/review tools (one call per movie) and
        # needs reasoning to weigh them side by side — hence Sonnet, not Haiku.
        tools=["search_movies", "get_movie_details", "get_movie_reviews", "present_choices"],
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
