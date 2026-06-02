# 🎬 Movie Agent Platform

A chat-based, multi-agent platform for movie reviews, plots, and recommendations.
See [`ARCHITECTURE.md`](./ARCHITECTURE.md) for the full design & roadmap.

**Status: Phase 1 complete** — intent **router** dispatches to three specialized agents
(**Plot**, **Reviews**, **Recommender**) that call **TMDB** tools via an Anthropic
tool-use loop. Streaming chat (web + mobile), agent badges, live tool-activity status,
multi-turn history, Langfuse tracing + prompt-registry override. Runs in echo mode with
zero keys.

## Agents & tools
| Agent | Trigger | Tools | Model |
|---|---|---|---|
| Plot | "plot of X" | search_movies, movie_details | Haiku |
| Reviews | "reviews for X" | search_movies, movie_reviews | Haiku |
| Recommender | "recommend…" (asks questions first) | discover_movies, search_movies, movie_details | Sonnet |

Prompts live in `backend/app/prompts.py` and are **overridden by Langfuse** if a prompt of
the same name exists there (edit/version without redeploy).

## Stack
- **Frontend:** Next.js 16 + React 19 + Tailwind (`frontend/`)
- **Backend:** FastAPI + Anthropic SDK + Langfuse (`backend/`)

## Run locally

### 1. Backend (port 8000)
```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # optional: add ANTHROPIC_API_KEY + Langfuse keys
uvicorn app.main:app --reload --port 8000
```
- No `ANTHROPIC_API_KEY` → runs in **echo mode** (pipeline still works).
- Add Anthropic key → router + agents come alive.
- Add `TMDB_API_KEY` → the agents can fetch real movie data.
- Add Langfuse keys → traces appear at https://cloud.langfuse.com.

> **Restart the server after editing `.env`** — settings are cached at startup.

Check it: `curl http://localhost:8000/health` → all flags should be `true`.

### Get the keys (both free)
- **Anthropic:** https://console.anthropic.com/ → API Keys → set `ANTHROPIC_API_KEY`.
- **TMDB:** https://www.themoviedb.org/settings/api → request an API key (v3 auth) →
  set `TMDB_API_KEY`.

### Live smoke test (after keys + restart)
```bash
cd backend && source .venv/bin/activate
python scripts/smoke.py        # exercises router + each agent end-to-end
```

### 2. Frontend (port 3000)
```bash
cd frontend
npm install      # if needed: npm_config_cache=../.npm-cache npm install
npm run dev
```
Open http://localhost:3000

> Note: this machine's global npm cache is broken; a project-local `.npm-cache/`
> is used as a workaround (`npm_config_cache=...`).

## What works now
- Streaming SSE chat (`POST /chat`) with `meta → agent → status → token → done` events
- Intent router → Plot / Reviews / Recommender agents (Anthropic tool-use loop over TMDB)
- Multi-turn history (recommender asks clarifying questions before suggesting)
- UI: agent badge per reply + live "🔎 Searching movies…" tool status
- Prompts overridable via Langfuse; traces no-op cleanly without keys

## Next: Phase 2
Golden datasets + RAGAS/LLM-judge evals + deploy gating. See `ARCHITECTURE.md` §11.
