"""Provider-agnostic movie data layer (the functions agents actually call).

Each function is title-based and self-healing: it prefers TMDB and falls back to OMDb when
TMDB errors out (slow/blocked network) or has no data. Reviews additionally merge OMDb's
IMDb/RT/Metacritic ratings, which TMDB lacks.

Keeping this layer separate from the raw clients (tmdb.py / omdb.py) means the agents never
deal with provider quirks or id formats — they pass a title and get clean, merged results.
"""
from __future__ import annotations

from typing import Any, Optional

from . import omdb, tmdb


def _provider_error(tmdb_exc: Exception, omdb_exc: Optional[Exception]) -> dict[str, Any]:
    return {
        "error": "Could not fetch movie data from any source.",
        "tmdb": f"{type(tmdb_exc).__name__}: {tmdb_exc}",
        "omdb": f"{type(omdb_exc).__name__}: {omdb_exc}" if omdb_exc else "not configured",
    }


async def search_titles(title: str, year: Optional[int] = None) -> dict[str, Any]:
    """Return candidate movies matching a title, for disambiguation. TMDB → OMDb."""
    try:
        results = await tmdb.search_movies(title, year)
        if results:
            return {"source": "tmdb", "candidates": results}
    except Exception:
        pass
    try:
        candidates = await omdb.search(title, year)
        return {"source": "omdb", "candidates": candidates}
    except omdb.OMDbNotConfigured:
        return {"source": "none", "candidates": []}
    except Exception:
        return {"source": "none", "candidates": []}


async def get_details(title: str, year: Optional[int] = None) -> dict[str, Any]:
    """Plot/overview, genres, runtime, year for the best title match. TMDB → OMDb."""
    tmdb_exc: Optional[Exception] = None
    try:
        results = await tmdb.search_movies(title, year)
        if results:
            d = await tmdb.movie_details(results[0]["id"])
            d["plot"] = d.get("overview")
            d["source"] = "tmdb"
            return d
        tmdb_exc = RuntimeError("no TMDB match")
    except Exception as exc:
        tmdb_exc = exc

    omdb_exc: Optional[Exception] = None
    try:
        return await omdb.by_title(title, year)
    except omdb.OMDbNotConfigured as exc:
        omdb_exc = exc
    except Exception as exc:
        omdb_exc = exc

    return _provider_error(tmdb_exc, omdb_exc)


async def get_reviews(title: str, year: Optional[int] = None) -> dict[str, Any]:
    """Aggregate ratings + user reviews, merging both providers where possible.

    OMDb supplies IMDb/Rotten Tomatoes/Metacritic scores; TMDB supplies written user
    reviews and its own average. We return whatever each source yields.
    """
    out: dict[str, Any] = {"title": title, "ratings": [], "reviews": [], "sources": []}

    # OMDb: cross-site rating aggregates (the valuable part).
    try:
        o = await omdb.by_title(title, year)
        out["title"] = o["title"] or title
        out["year"] = o.get("year")
        out["ratings"] = o.get("ratings", [])
        if o.get("imdb_rating") and o["imdb_rating"] != "N/A":
            out["imdb_rating"] = o["imdb_rating"]
        out["sources"].append("omdb")
    except Exception:
        pass

    # TMDB: written user reviews + its own average.
    try:
        results = await tmdb.search_movies(title, year)
        if results:
            r = await tmdb.movie_reviews(results[0]["id"])
            out["title"] = out["title"] or r.get("title")
            out["tmdb_average"] = r.get("vote_average")
            out["tmdb_vote_count"] = r.get("vote_count")
            out["reviews"] = r.get("reviews", [])
            out["sources"].append("tmdb")
    except Exception:
        pass

    if not out["sources"]:
        out["error"] = "Could not fetch ratings or reviews from any source."
    return out


async def discover(
    genres: Optional[list[str]] = None,
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    language: Optional[str] = None,
    sort_by: str = "popularity.desc",
) -> dict[str, Any]:
    """Recommend movies by filters. TMDB only (OMDb has no discovery endpoint)."""
    try:
        results = await tmdb.discover_movies(
            genres=genres,
            year_from=year_from,
            year_to=year_to,
            language=language,
            sort_by=sort_by,
        )
        return {"source": "tmdb", "results": results}
    except tmdb.TMDBNotConfigured as exc:
        return {"error": str(exc), "hint": "Recommendations require TMDB_API_KEY."}
    except Exception as exc:
        return {
            "error": f"TMDB unavailable: {type(exc).__name__}: {exc}",
            "hint": "Recommendations need TMDB (OMDb can't discover). Try again shortly.",
        }
