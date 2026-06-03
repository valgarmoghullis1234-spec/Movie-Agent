"""DNS-over-HTTPS bypass for ISP-poisoned hosts (e.g. api.themoviedb.org).

Some ISPs (commonly Indian broadband) DNS-poison `api.themoviedb.org`, returning blackhole
IPs so the app can never reach TMDB even though TMDB is up. We resolve the *real* IPs via
DNS-over-HTTPS — querying Cloudflare by IP literal (1.1.1.1), which itself can't be
poisoned — and hand them to the TMDB client, which connects by IP while sending the real
hostname as SNI (so TLS/cert verification stay fully intact).

Patching socket.getaddrinfo does NOT work here: anyio (used by httpx) binds getaddrinfo at
import time, so it keeps using the poisoned system resolver. Connecting by IP + SNI is the
reliable approach.
"""
from __future__ import annotations

import httpx

# Hosts known to be DNS-poisoned by some ISPs. (image.tmdb.org is not affected.)
_HOSTS = ("api.themoviedb.org",)
# Cloudflare DoH via IP literal so this lookup can't itself be poisoned.
_DOH_URL = "https://1.1.1.1/dns-query"

_cache: dict[str, list[str]] = {}


async def _doh_a_records(client: httpx.AsyncClient, host: str) -> list[str]:
    """Return ALL A-record IPs for `host` via Cloudflare DoH (may be empty)."""
    try:
        resp = await client.get(
            _DOH_URL,
            params={"name": host, "type": "A"},
            headers={"accept": "application/dns-json"},
        )
        resp.raise_for_status()
        return [a["data"] for a in resp.json().get("Answer", []) if a.get("type") == 1 and a.get("data")]
    except Exception:
        return []


async def resolve(host: str) -> list[str]:
    """Real IPs for `host` via DoH, cached. Empty list if DoH is unreachable (caller then
    falls back to the normal hostname). Only hosts in `_HOSTS` are looked up."""
    if host not in _HOSTS:
        return []
    if host in _cache:
        return _cache[host]
    async with httpx.AsyncClient(timeout=8.0) as client:
        ips = await _doh_a_records(client, host)
    if ips:
        _cache[host] = ips
    return ips
