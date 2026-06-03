"""Low-level OMDb (omdbapi.com) async client.

OMDb is our fallback data source when TMDB is slow/blocked, and our primary source for
aggregate ratings (IMDb / Rotten Tomatoes / Metacritic), which TMDB doesn't provide.

OMDb keys movies by title or IMDb id (ttXXXXXXX) — there are no TMDB-style integer ids,
which is why the higher-level layer (movies.py) is title-based.

Requires OMDB_API_KEY. Raises OMDbNotConfigured if absent.
"""
from __future__ import annotations

import asyncio
from typing import Any, Optional

import httpx

from ..config import get_settings

BASE_URL = "https://www.omdbapi.com/"
_TIMEOUT = httpx.Timeout(20.0, connect=10.0)
_MAX_ATTEMPTS = 3


class OMDbNotConfigured(RuntimeError):
    pass


class OMDbNotFound(RuntimeError):
    pass


def _api_key() -> str:
    key = get_settings().omdb_api_key
    if not key:
        raise OMDbNotConfigured("OMDB_API_KEY is not set in backend/.env")
    return key


async def _get(params: dict[str, Any]) -> dict[str, Any]:
    params = dict(params)
    params["apikey"] = _api_key()
    last_exc: Optional[Exception] = None
    for attempt in range(_MAX_ATTEMPTS):
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(BASE_URL, params=params)
                resp.raise_for_status()
                data = resp.json()
            if data.get("Response") == "False":
                raise OMDbNotFound(data.get("Error", "not found"))
            return data
        except httpx.TransportError as exc:
            last_exc = exc
            if attempt < _MAX_ATTEMPTS - 1:
                await asyncio.sleep(0.5 * (attempt + 1))
    raise last_exc  # type: ignore[misc]


def _year(value: Optional[str]) -> Optional[str]:
    return value.split("–")[0].strip() if value else None  # OMDb uses en-dash ranges


async def by_title(title: str, year: Optional[int] = None) -> dict[str, Any]:
    """Look up a single movie by title (best match), full plot + ratings."""
    params: dict[str, Any] = {"t": title, "type": "movie", "plot": "full"}
    if year:
        params["y"] = year
    m = await _get(params)
    return {
        "source": "omdb",
        "title": m.get("Title"),
        "year": _year(m.get("Year")),
        "plot": m.get("Plot"),
        "rated": m.get("Rated"),  # MPAA certification: G / PG / PG-13 / R / NC-17 / N/A
        "genres": [g.strip() for g in (m.get("Genre") or "").split(",") if g.strip()],
        "runtime": m.get("Runtime"),
        "actors": m.get("Actors"),
        "director": m.get("Director"),
        "imdb_id": m.get("imdbID"),
        "imdb_rating": m.get("imdbRating"),
        "ratings": [
            {"source": r.get("Source"), "value": r.get("Value")}
            for r in m.get("Ratings", [])
        ],
    }


async def facts_by_title(title: str, year: Optional[int] = None) -> dict[str, Any]:
    """Rich factual record for trivia: cast, crew, awards, box office, release, ratings."""
    params: dict[str, Any] = {"t": title, "type": "movie", "plot": "short"}
    if year:
        params["y"] = year
    m = await _get(params)
    return {
        "source": "omdb",
        "title": m.get("Title"),
        "year": _year(m.get("Year")),
        "rated": m.get("Rated"),
        "released": m.get("Released"),
        "runtime": m.get("Runtime"),
        "genres": [g.strip() for g in (m.get("Genre") or "").split(",") if g.strip()],
        "director": m.get("Director"),
        "writer": m.get("Writer"),
        "actors": m.get("Actors"),
        "plot": m.get("Plot"),
        "language": m.get("Language"),
        "country": m.get("Country"),
        "awards": m.get("Awards"),
        "box_office": m.get("BoxOffice"),
        "imdb_rating": m.get("imdbRating"),
        "metascore": m.get("Metascore"),
    }


async def search(title: str, year: Optional[int] = None) -> list[dict[str, Any]]:
    """Search movie titles (for disambiguation). Returns up to 5 candidates."""
    params: dict[str, Any] = {"s": title, "type": "movie"}
    if year:
        params["y"] = year
    try:
        data = await _get(params)
    except OMDbNotFound:
        return []
    return [
        {
            "title": r.get("Title"),
            "year": _year(r.get("Year")),
            "imdb_id": r.get("imdbID"),
        }
        for r in data.get("Search", [])[:5]
    ]
