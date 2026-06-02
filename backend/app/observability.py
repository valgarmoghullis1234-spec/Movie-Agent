"""Langfuse tracing wiring.

Designed to be a no-op when Langfuse keys are absent, so the app runs identically
with or without observability configured. In Phase 0 we expose a single helper,
`trace_chat`, a context manager that opens a trace for one chat turn and lets you
attach the LLM generation + final output.
"""
from __future__ import annotations

import contextlib
from typing import Any, Optional

from .config import get_settings

try:  # langfuse is optional at runtime
    from langfuse import Langfuse  # type: ignore
except Exception:  # pragma: no cover
    Langfuse = None  # type: ignore


_client: Optional["Langfuse"] = None


def get_langfuse() -> Optional["Langfuse"]:
    """Return a cached Langfuse client, or None if tracing is disabled."""
    global _client
    settings = get_settings()
    if not settings.tracing_enabled or Langfuse is None:
        return None
    if _client is None:
        _client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
    return _client


class _NoopSpan:
    """Stand-in that swallows all calls when tracing is disabled."""

    def __getattr__(self, _name: str):
        def _noop(*_args: Any, **_kwargs: Any) -> "_NoopSpan":
            return self

        return _noop


@contextlib.contextmanager
def trace_chat(user_message: str, agent: str, session_id: Optional[str] = None):
    """Open a trace for one chat turn.

    Yields a trace handle (real Langfuse trace or a no-op). Always safe to call.
    """
    client = get_langfuse()
    if client is None:
        yield _NoopSpan()
        return

    trace = client.trace(
        name="chat-turn",
        session_id=session_id,
        input=user_message,
        metadata={"agent": agent},
    )
    try:
        yield trace
    finally:
        # Best-effort flush so traces show up promptly in local/dev runs.
        with contextlib.suppress(Exception):
            client.flush()
