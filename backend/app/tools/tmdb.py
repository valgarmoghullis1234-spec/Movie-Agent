"""Low-level TMDB (The Movie Database) async client.

Wraps the handful of TMDB v3 endpoints our agents need. Every function returns plain
JSON-serializable dicts/lists (never raw HTTP objects) so results can be fed straight back
to the model as tool results.

Requires TMDB_API_KEY. If it's missing, calls raise TMDBNotConfigured so the agent layer
can surface a clear message instead of failing opaquely.
"""
from __future__ import annotations

import asyncio
from typing import Any, Optional

import httpx

from ..config import get_settings
from . import _resolver

# Network tuning: TMDB can be slow/flaky over hotspots & VPNs, so use a generous
# timeout and retry transient failures before giving up.
_TIMEOUT = httpx.Timeout(25.0, connect=10.0)
_MAX_ATTEMPTS = 3

API_HOST = "api.themoviedb.org"
BASE_URL = f"https://{API_HOST}/3"
POSTER_BASE = "https://image.tmdb.org/t/p/w342"

# Standard TMDB movie genre map (avoids an extra /genre/movie/list call per request).
GENRES: dict[str, int] = {
    "action": 28,
    "adventure": 12,
    "animation": 16,
    "comedy": 35,
    "crime": 80,
    "documentary": 99,
    "drama": 18,
    "family": 10751,
    "fantasy": 14,
    "history": 36,
    "horror": 27,
    "music": 10402,
    "mystery": 9648,
    "romance": 10749,
    "science fiction": 878,
    "sci-fi": 878,
    "thriller": 53,
    "war": 10752,
    "western": 37,
}


class TMDBNotConfigured(RuntimeError):
    pass


def _api_key() -> str:
    key = get_settings().tmdb_api_key
    if not key:
        raise TMDBNotConfigured("TMDB_API_KEY is not set in backend/.env")
    return key


async def _request(client: httpx.AsyncClient, path: str, params: dict[str, Any], ip: Optional[str]) -> dict[str, Any]:
    """One GET, either to the normal hostname (ip=None) or to a pinned IP with SNI/Host set
    to the real hostname (so TLS/cert verification still validate against api.themoviedb.org)."""
    if ip:
        url = f"https://{ip}/3{path}"
        kwargs: dict[str, Any] = {"headers": {"Host": API_HOST}, "extensions": {"sni_hostname": API_HOST}}
    else:
        url = f"{BASE_URL}{path}"
        kwargs = {}
    resp = await client.get(url, params=params, **kwargs)
    resp.raise_for_status()
    return resp.json()


async def _get(path: str, params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    params = dict(params or {})
    params["api_key"] = _api_key()

    # Build connection candidates: real IPs first (bypasses ISPs that DNS-poison the host),
    # then the plain hostname as a last resort. DoH returns several IPs; some ISPs blackhole
    # a subset, so we fail over across them — the first that answers 2xx wins.
    real_ips = await _resolver.resolve(API_HOST)
    candidates: list[Optional[str]] = [*real_ips, None]

    last_exc: Optional[Exception] = None
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        for ip in candidates:
            for attempt in range(_MAX_ATTEMPTS):
                try:
                    return await _request(client, path, params, ip)
                except httpx.HTTPStatusError as exc:
                    # Don't retry/fail-over on genuine client errors (401 bad key, 404).
                    if exc.response.status_code < 500:
                        raise
                    last_exc = exc
                    break  # server error: try the next candidate
                except httpx.TransportError as exc:
                    last_exc = exc
                    if attempt < _MAX_ATTEMPTS - 1:
                        await asyncio.sleep(0.3 * (attempt + 1))  # brief backoff, then retry
            # exhausted retries for this candidate → fall through to the next IP
    raise last_exc  # type: ignore[misc]


def _year(date: Optional[str]) -> Optional[str]:
    return date.split("-")[0] if date else None


def _slim_movie(m: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": m.get("id"),
        "title": m.get("title") or m.get("name"),
        "year": _year(m.get("release_date")),
        "overview": m.get("overview"),
        "vote_average": m.get("vote_average"),
        "vote_count": m.get("vote_count"),
        "poster": POSTER_BASE + m["poster_path"] if m.get("poster_path") else None,
    }


async def search_movies(query: str, year: Optional[int] = None) -> list[dict[str, Any]]:
    """Search movies by title. Returns up to 5 slim results (best matches first)."""
    params: dict[str, Any] = {"query": query, "include_adult": "false"}
    if year:
        params["year"] = year
    data = await _get("/search/movie", params)
    return [_slim_movie(m) for m in data.get("results", [])[:5]]


async def movie_details(movie_id: int) -> dict[str, Any]:
    """Full details for one movie id, including genres, runtime, tagline."""
    m = await _get(f"/movie/{movie_id}")
    out = _slim_movie(m)
    out.update(
        {
            "tagline": m.get("tagline"),
            "runtime": m.get("runtime"),
            "genres": [g["name"] for g in m.get("genres", [])],
            "status": m.get("status"),
        }
    )
    return out


async def movie_reviews(movie_id: int) -> dict[str, Any]:
    """User reviews for a movie plus its aggregate rating. Content truncated for brevity."""
    details = await _get(f"/movie/{movie_id}")
    data = await _get(f"/movie/{movie_id}/reviews")
    reviews = []
    for r in data.get("results", [])[:5]:
        content = (r.get("content") or "").strip()
        reviews.append(
            {
                "author": r.get("author"),
                "rating": (r.get("author_details") or {}).get("rating"),
                "content": content[:600] + ("…" if len(content) > 600 else ""),
            }
        )
    return {
        "title": details.get("title"),
        "year": _year(details.get("release_date")),
        "vote_average": details.get("vote_average"),
        "vote_count": details.get("vote_count"),
        "reviews": reviews,
    }


async def watch_providers(movie_id: int, country: str = "US") -> dict[str, Any]:
    """Where a movie can be streamed/rented/bought in a country (TMDB's JustWatch data).
    Returns provider names grouped by access type for the given ISO-3166-1 country code."""
    data = await _get(f"/movie/{movie_id}/watch/providers")
    region = (data.get("results") or {}).get(country.upper(), {})

    def names(key: str) -> list[str]:
        return [p.get("provider_name") for p in region.get(key, []) if p.get("provider_name")]

    return {
        "country": country.upper(),
        "stream": names("flatrate"),  # subscription streaming
        "rent": names("rent"),
        "buy": names("buy"),
        "link": region.get("link"),  # JustWatch deep link
    }


async def similar_movies(movie_id: int) -> list[dict[str, Any]]:
    """Movies TMDB recommends for fans of this one. Uses the curated /recommendations
    endpoint (taste-based) rather than /similar (keyword-based). Returns up to 8 slim results."""
    data = await _get(f"/movie/{movie_id}/recommendations")
    return [_slim_movie(m) for m in data.get("results", [])[:8]]


async def discover_movies(
    genres: Optional[list[str]] = None,
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    language: Optional[str] = None,
    sort_by: str = "popularity.desc",
    min_votes: int = 100,
) -> list[dict[str, Any]]:
    """Discover movies by filters. Maps genre names to TMDB ids; returns up to 8 results."""
    params: dict[str, Any] = {
        "sort_by": sort_by,
        "include_adult": "false",
        "vote_count.gte": min_votes,
    }
    if genres:
        ids = [str(GENRES[g.lower()]) for g in genres if g.lower() in GENRES]
        if ids:
            params["with_genres"] = ",".join(ids)
    if year_from:
        params["primary_release_date.gte"] = f"{year_from}-01-01"
    if year_to:
        params["primary_release_date.lte"] = f"{year_to}-12-31"
    if language:
        params["with_original_language"] = language
    data = await _get("/discover/movie", params)
    return [_slim_movie(m) for m in data.get("results", [])[:8]]
