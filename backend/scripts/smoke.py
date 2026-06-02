"""End-to-end smoke test for the Phase 1 agents.

Runs the router + each specialized agent directly (no HTTP) and prints the streamed
output, so you can confirm tool-use against TMDB works. Requires ANTHROPIC_API_KEY and
TMDB_API_KEY in backend/.env.

Usage:
    cd backend && source .venv/bin/activate && python scripts/smoke.py
"""
import asyncio
import os
import sys

# Make `app` importable when run from backend/.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agents.router import route  # noqa: E402
from app.agents.runner import run_agent  # noqa: E402
from app.config import get_settings  # noqa: E402

CASES = [
    ("Plot", "What's the plot of Inception?"),
    ("Reviews", "What did people think of Dune: Part Two?"),
    ("Recommend", "Recommend me a sci-fi thriller from the 2010s, in English."),
]


async def run_case(label: str, message: str) -> None:
    print(f"\n{'=' * 70}\n[{label}]  user: {message}\n{'-' * 70}")
    history = [{"role": "user", "content": message}]
    agent = await route(history)
    print(f"router → {agent.name}\n")
    async for kind, text in run_agent(agent, history):
        if kind == "status":
            print(f"\n  · {text}")
        else:
            print(text, end="", flush=True)
    print()


async def main() -> None:
    s = get_settings()
    if not s.llm_enabled:
        sys.exit("✗ ANTHROPIC_API_KEY missing — add it to backend/.env and restart.")
    if not s.tmdb_api_key:
        print("⚠ TMDB_API_KEY missing — tools will return errors, but routing still runs.\n")
    for label, message in CASES:
        await run_case(label, message)
    print(f"\n{'=' * 70}\n✓ smoke test complete")


if __name__ == "__main__":
    asyncio.run(main())
