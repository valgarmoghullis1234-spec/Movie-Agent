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
    "get_streaming_availability": {
        "name": "get_streaming_availability",
        "description": (
            "Find where a movie can be watched: which subscription services stream it, and "
            "where to rent or buy it, in a given country. Use this for 'where can I watch X', "
            "'is X on Netflix', 'where is X streaming' questions. Default country is US; pass a "
            "2-letter ISO country code (e.g. 'GB', 'IN', 'CA') if the user names a country."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "year": {"type": "integer"},
                "country": {
                    "type": "string",
                    "description": "ISO-3166-1 alpha-2 country code, e.g. 'US', 'GB', 'IN'.",
                },
            },
            "required": ["title"],
        },
    },
    "get_movie_facts": {
        "name": "get_movie_facts",
        "description": (
            "Get a rich factual record about a movie for trivia/quiz purposes: cast, "
            "director, writer, release date, runtime, awards, box office and ratings. Use "
            "this to ground trivia questions or to verify a user's answer. Pass a year when "
            "known to pin the right film."
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
    "get_content_guidance": {
        "name": "get_content_guidance",
        "description": (
            "Get parental/family-safety info for a movie: its MPAA certification (G, PG, "
            "PG-13, R, NC-17), genres, runtime and plot. Use this when the user asks whether "
            "a movie is appropriate for kids/children/family, or about its age rating. Pass a "
            "year when known."
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
    "find_similar_movies": {
        "name": "find_similar_movies",
        "description": (
            "Given ONE movie the user already likes, return movies that fans of it tend to "
            "enjoy (taste-based recommendations). Use this for 'if you liked X…' or 'more "
            "movies like X' requests. Pass a year when known to pin the right film."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "The movie the user already likes."},
                "year": {"type": "integer", "description": "Optional release year of that movie."},
            },
            "required": ["title"],
        },
    },
    "present_choices": {
        "name": "present_choices",
        "description": (
            "Render tappable choice BUTTONS for the user instead of asking them to type a "
            "choice. Use this whenever you ask the user to pick from a small, discrete set of "
            "options: disambiguating which movie they meant, multiple-choice trivia answers "
            "(A–D), or offering moods/vibes to pick from. Write your question or intro as "
            "normal text FIRST, then call this tool as your LAST action with the options. Do "
            "NOT also spell out the options as a numbered/lettered list in your text — the "
            "buttons replace them. After calling this, STOP and wait for the user's tap."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "options": {
                    "type": "array",
                    "description": "2–6 choices to show as buttons.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "label": {
                                "type": "string",
                                "description": (
                                    "Short button text shown to the user, e.g. "
                                    "\"Charlie's Angels (2000)\" or \"Andy Dufresne\"."
                                ),
                            },
                            "value": {
                                "type": "string",
                                "description": (
                                    "The message sent back as the user's reply when this "
                                    "button is tapped — usually the same as the label, or a "
                                    "fuller phrase like 'The 2000 version with Drew Barrymore'."
                                ),
                            },
                        },
                        "required": ["label", "value"],
                    },
                },
            },
            "required": ["options"],
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
    "find_similar_movies": movies.similar,
    "get_content_guidance": movies.content_guidance,
    "get_movie_facts": movies.movie_facts,
    "get_streaming_availability": movies.where_to_stream,
    "discover_movies": movies.discover,
    # NOTE: "present_choices" is intentionally absent — it is a UI action, not a data
    # tool. The runner intercepts it before dispatch (see agents/runner.py) and emits a
    # "choices" event to the client instead of executing anything.
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
