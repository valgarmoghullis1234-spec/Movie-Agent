# Movie Agent Platform — Architecture & Roadmap

> A chat-based, multi-agent platform for movie discovery (reviews, plots, recommendations
> and more), built to **monetize** and to **learn agent engineering** end-to-end.
> Mobile + web friendly via a single responsive web app.

---

## 1. Vision

A single chat interface where a user can:

1. Ask for **reviews** of a movie.
2. Ask for the **plot** of a movie (spoiler-free or full).
3. Get a **recommendation** — the bot asks clarifying questions (genre, mood, era…) then suggests.

Under the hood, a fleet of **specialized agents** (each = system prompt + tools + model)
is coordinated by a **router**. Every interaction is **traced and evaluated**, every
system prompt is **versioned and editable from a UI**, and usage is **metered for billing**.

The same shell generalizes to many other recommendation use cases (Section 8).

---

## 2. Core Principles

- **Agents are data, not code.** An agent = `{system_prompt, tools[], model, params}` stored
  in a registry. You can edit a prompt and ship it without redeploying.
- **Route by intent + cost.** Cheap/simple turns → Haiku; hard reasoning → Opus.
- **Everything is observable.** No interaction happens without a trace.
- **Eval before you trust.** Each agent has a golden dataset and automated scores (incl. RAGAS).
- **One responsive frontend.** Works as a website and installs as a PWA on phones.

---

## 3. Tech Stack

| Layer | Choice | Why |
|---|---|---|
| Frontend | **Next.js + React + Tailwind + shadcn/ui** | One codebase → mobile + web; PWA installable; streaming chat UI. |
| Backend | **Python + FastAPI** | Best ecosystem for agents, evals, RAGAS. Async, fast, typed. |
| Agent orchestration | **LangGraph** (alt: PydanticAI) | Graph/state machine for routing + multi-turn agents + tool calls. |
| LLM provider | **Anthropic Claude** — Opus 4.8 / Sonnet 4.6 / Haiku 4.5 | Tiered routing for cost control; strong tool use. |
| Movie data | **TMDB** (primary, free) + **OMDb** (ratings) + **JustWatch** (streaming availability) | Plots, metadata, posters, reviews, where-to-stream. |
| Auth + DB + storage | **Supabase (Postgres)** | Auth, row-level security, storage, realtime — all in one. |
| Observability / prompts / evals | **Langfuse** (OSS, self-hostable) | Traces, **prompt registry (view/edit/version)**, datasets, **RAGAS** scoring, cost tracking. |
| Payments | **Stripe** | Subscriptions + usage-based/metered billing. |
| Cache / rate limit | **Redis (Upstash)** | Cache TMDB lookups, per-user rate limits, session state. |
| Deploy | Frontend → Vercel; Backend → Railway/Fly.io; DB → Supabase | Low-ops, scales later. |

**Why Langfuse is central:** it single-handedly satisfies three of your requirements —
trace recording, a UI to **see and tweak system prompts** (versioned), and **evals incl. RAGAS**.

---

## 4. System Architecture

```
                         ┌──────────────────────────────┐
                         │   Next.js Web App (PWA)       │
                         │   Chat UI · streaming · auth  │
                         └───────────────┬──────────────┘
                                         │ HTTPS / SSE (stream)
                         ┌───────────────▼──────────────┐
                         │      FastAPI Backend          │
                         │  /chat  /agents  /billing     │
                         └───────────────┬──────────────┘
                                         │
                         ┌───────────────▼──────────────┐
                         │     Router / Orchestrator     │  ← LangGraph
                         │  classify intent → pick agent │
                         └───┬──────────┬──────────┬─────┘
                             │          │          │
                  ┌──────────▼──┐ ┌─────▼──────┐ ┌─▼───────────────┐
                  │ Reviews     │ │ Plot       │ │ Recommender     │
                  │ Agent       │ │ Agent      │ │ (multi-turn)    │
                  └──────┬──────┘ └─────┬──────┘ └─────┬───────────┘
                         │  tool calls  │              │
                  ┌──────▼──────────────▼──────────────▼───────────┐
                  │              Tool Layer                         │
                  │  tmdb_search · tmdb_details · tmdb_reviews ·    │
                  │  tmdb_discover · justwatch · web_search ·       │
                  │  user_memory · summarize                        │
                  └──────┬──────────────────────────────┬──────────┘
                         │                               │
                  ┌──────▼──────┐               ┌────────▼────────┐
                  │ External    │               │ Supabase (PG)   │
                  │ APIs        │               │ users·prompts·  │
                  │ TMDB/OMDb   │               │ history·usage   │
                  └─────────────┘               └─────────────────┘

   Every node above emits spans → ┌──────────────┐
                                  │  Langfuse    │ traces · prompts · evals · cost
                                  └──────────────┘
```

---

## 5. Agent Model

Each agent is defined declaratively:

```python
Agent(
    name="recommender",
    model="claude-sonnet-4-6",        # tiered per agent
    system_prompt_ref="recommender@v7",  # pulled from Langfuse prompt registry
    tools=[tmdb_discover, tmdb_search, user_memory],
    params={"temperature": 0.7, "max_tokens": 1024},
)
```

- **Prompts live in Langfuse**, referenced by name+version. Edit in the Langfuse UI,
  A/B versions, roll back — no deploy needed.
- **Tools** are plain Python functions with typed args, exposed to the model via the
  Anthropic tool-use API.
- **Model tier** chosen per agent (Haiku for routing/plot lookups, Sonnet/Opus for
  reasoning-heavy recommendation).

### The Router

A lightweight Haiku call (or embedding classifier) maps each message to an intent:
`reviews | plot | recommend | smalltalk | other`, plus extracts entities (movie title).
It then dispatches to the matching agent and maintains conversation state.

---

## 6. Use Cases — Detailed Specs

### 6.1 Reviews Agent
- **Goal:** Given a movie, return a synthesized review summary (critic + audience sentiment).
- **Flow:** `tmdb_search` (resolve title→id) → `tmdb_reviews` + `omdb` ratings →
  optional `web_search` for recent critic takes → `summarize` into pros/cons + verdict.
- **Output:** Score snapshot (e.g. IMDb/RT-style), 2–3 sentence sentiment summary, pros/cons.
- **Edge cases:** ambiguous titles (disambiguate with year/poster), no reviews found.
- **Eval focus:** factual grounding (RAGAS faithfulness), no hallucinated scores.

### 6.2 Plot Agent
- **Goal:** Return the plot. **Spoiler-aware** by default (synopsis without ending),
  with a "full plot / reveal ending" toggle.
- **Flow:** `tmdb_search` → `tmdb_details` (overview + optional full synopsis) → format.
- **Output:** Logline → spoiler-free synopsis → [expandable] full plot.
- **Eval focus:** spoiler leakage detection, factual accuracy vs. TMDB.

### 6.3 Recommender Agent (multi-turn)
- **Goal:** Ask clarifying questions, then recommend 3–5 titles with reasons.
- **Flow (stateful):**
  1. Detect missing slots: `genre`, `mood`, `era`, `language`, `length`, `already_seen`.
  2. Ask **one or two** concise questions to fill the most important gaps.
  3. Call `tmdb_discover` with assembled filters; rank; explain each pick.
  4. Offer "more like #2" / "where to stream" follow-ups.
- **State:** preference object persisted to `user_memory` for next time.
- **Eval focus:** relevance to stated prefs, diversity, no repeats of seen titles.

---

## 7. Observability, Prompts & Evals

**Tracing (Langfuse):** every request opens a trace; router, agent, each tool call, and
each LLM call become nested spans with inputs/outputs, latency, tokens, and **cost**.

**Prompt management:** all system prompts stored in Langfuse's registry. The admin can
**view, edit, version, and A/B** prompts from the UI; the backend fetches by ref at runtime
(cached). This is the "see the system prompt, change it, tweak it" requirement.

**Evals & RAGAS:**
- Build a **golden dataset** per agent (inputs + ideal outputs / references).
- Run automated scorers on each release:
  - **RAGAS:** `faithfulness`, `answer_relevancy`, `context_precision`, `context_recall`
    (treat TMDB/review data as the retrieved context).
  - **LLM-as-judge:** helpfulness, tone, spoiler-leakage, format adherence.
  - **Deterministic checks:** valid movie IDs, no fabricated scores, JSON schema valid.
- Gate deploys on eval thresholds; track score trends over prompt versions in Langfuse.

---

## 8. Additional Use Cases (Expansion Agents)

Same architecture, new agents/tools. Prioritized by value × effort:

| # | Use case | New tool(s) | Notes |
|---|---|---|---|
| 1 | **What to watch tonight** (mood-based) | reuse `tmdb_discover` | Low effort, high engagement. |
| 2 | **Where to stream** | `justwatch` | "Which service has X in my country?" High utility. |
| 3 | **Watchlist + memory** | `user_memory` CRUD | Remembers seen/liked; avoids repeats; boosts retention. |
| 4 | **Couple / group mode** | blend 2+ taste profiles | Differentiator; viral/shareable. |
| 5 | **"If you liked X…"** similarity | `tmdb_similar` | Cheap, very popular query type. |
| 6 | **Trivia / quiz bot** | `tmdb_facts` | Pure engagement + retention loop. |
| 7 | **Parental guidance** | `omdb`/ratings + content flags | Family-safe niche; monetizable. |
| 8 | **Compare two movies** | parallel `tmdb_details` | Decision-support. |
| 9 | **Vertical expansion: TV / Anime / Books** | swap data source | The real platform play — same chat+agent+billing shell, new domain. |
| 10 | **Personalized digest** (weekly "new for you") | cron + `user_memory` | Re-engagement via email/push; ties to subscription. |

**Strategic read:** use cases 1–8 deepen the movie product; #9 is how this becomes a
*platform* (reusable recommendation engine for any domain); #10 drives retention/LTV.

---

## 9. Monetization

- **Free:** N messages/day, Haiku-tier, basic agents.
- **Pro (subscription):** unlimited, Sonnet/Opus quality, all agents (group mode, streaming
  finder, watchlist, weekly digest).
- **Usage credits:** for premium actions (deep web-research reviews, batch recommendations).
- **Metered billing:** Stripe meters tied to Langfuse token-cost traces → margin visibility.
- **Future:** affiliate links (streaming sign-ups, ticketing), B2B API of the recommender.

**Unit-economics tip:** route aggressively by tier and cache TMDB calls; your Langfuse cost
traces tell you exact $/conversation so you can price the Pro tier with real margin data.

---

## 10. Data Model (initial)

```
users(id, email, tier, stripe_customer_id, created_at)
conversations(id, user_id, created_at)
messages(id, conversation_id, role, content, agent, trace_id, created_at)
user_prefs(user_id, genres[], languages[], disliked[], seen[]) -- memory
watchlist(user_id, movie_id, status)           -- want / seen / liked
usage(user_id, day, message_count, tokens, cost)
-- prompts/versions live in Langfuse, not in app DB
```

---

## 11. Build Roadmap (phased)

**Phase 0 — Foundations (week 1)**
- Repo scaffold: `frontend/` (Next.js) + `backend/` (FastAPI).
- Supabase project + auth; TMDB + Anthropic + Langfuse keys.
- Minimal streaming chat UI ↔ `/chat` endpoint (single echo agent) with tracing wired in.

**Phase 1 — Core three agents (weeks 2–3)**
- Tool layer: `tmdb_search/details/reviews/discover`.
- Plot Agent → Reviews Agent → Recommender (multi-turn).
- Router with intent classification. Prompts in Langfuse.

**Phase 2 — Observability & evals (week 4)**
- Golden datasets per agent; RAGAS + LLM-judge scorers; deploy gating.
- Admin prompt-tweaking workflow validated end-to-end.

**Phase 3 — Monetization (week 5)**
- Stripe subscriptions + usage metering; free/pro gating; rate limits via Redis.

**Phase 4 — Expansion (ongoing)**
- Add expansion agents (Section 8) by value; weekly digest cron; PWA polish.

---

## 12. Key Risks & Decisions

- **Movie data licensing:** TMDB requires attribution; review text usage limits — verify ToS.
- **LLM cost creep:** enforce tiered routing + caching from day one (traces make this visible).
- **Spoiler safety:** treat as a first-class eval, not an afterthought.
- **Latency:** stream responses; parallelize tool calls; cache hot lookups.
- **Open decisions:** LangGraph vs. PydanticAI; self-host vs. cloud Langfuse; PWA vs. later
  native wrapper (Capacitor/Expo) if you want app-store presence.

---

## 13. Next Step

When ready to build, start at **Phase 0**: scaffold `frontend/` + `backend/`, wire one
streaming agent with Langfuse tracing, then layer in the three agents. Ask me to
"scaffold Phase 0" and I'll generate the repo skeleton.
```
