"""Tool registry: Anthropic tool-use schemas + an async dispatcher.

Tools are title-based and provider-agnostic (see tools/movies.py): the agent passes a movie
title (and optional year) and gets clean, merged results with automatic TMDB→OMDb fallback.
One source of truth for what Claude can call.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from . import movies

# --- Tool schemas exposed to Claude (Anthropic tool-use format) ---------------

TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "search_movies": {
        "name": "search_movies",
        "description": (
            "Search movie titles to disambiguate when a name is ambiguous. Returns a list "
            "of candidate titles with years. Use this when several different movies could "
            "match the user's request."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Movie title to search for."},
                "year": {"type": "integer", "description": "Optional release year."},
            },
            "required": ["title"],
        },
    },
    "get_movie_details": {
        "name": "get_movie_details",
        "description": (
            "Get the plot/overview, genres, runtime and year for a specific movie by title. "
            "Pass a year when known to pick the right one. Auto-falls back across data sources."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "year": {"type": "integer"},
            },
            "required": ["title"],
        },
    },
    "get_movie_reviews": {
        "name": "get_movie_reviews",
        "description": (
            "Get aggregate ratings (IMDb, Rotten Tomatoes, Metacritic) and written user "
            "reviews for a movie by title. Pass a year when known."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "year": {"type": "integer"},
            },
            "required": ["title"],
        },
    },
    "discover_movies": {
        "name": "discover_movies",
        "description": (
            "Find movie recommendations by filters. Use genre names like 'comedy', "
            "'thriller', 'science fiction'. Use this for recommendation requests."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "genres": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Genre names, e.g. ['thriller', 'mystery'].",
                },
                "year_from": {"type": "integer"},
                "year_to": {"type": "integer"},
                "language": {
                    "type": "string",
                    "description": "ISO-639-1 original language code, e.g. 'en', 'ko', 'hi'.",
                },
                "sort_by": {
                    "type": "string",
                    "description": "TMDB sort, e.g. 'popularity.desc' or 'vote_average.desc'.",
                },
            },
            "required": [],
        },
    },
}

# --- Dispatch table -----------------------------------------------------------

_DISPATCH: dict[str, Callable[..., Awaitable[Any]]] = {
    "search_movies": movies.search_titles,
    "get_movie_details": movies.get_details,
    "get_movie_reviews": movies.get_reviews,
    "discover_movies": movies.discover,
}


def schemas_for(names: list[str]) -> list[dict[str, Any]]:
    """Return the Anthropic tool schemas for the given tool names."""
    return [TOOL_SCHEMAS[n] for n in names if n in TOOL_SCHEMAS]


async def dispatch(name: str, args: dict[str, Any]) -> Any:
    """Execute a tool call, returning a JSON-serializable result (or an error dict)."""
    fn = _DISPATCH.get(name)
    if fn is None:
        return {"error": f"unknown tool: {name}"}
    try:
        return await fn(**args)
    except Exception as exc:  # last-resort guard; movies.py already handles provider errors
        return {"error": f"{type(exc).__name__}: {exc}"}
