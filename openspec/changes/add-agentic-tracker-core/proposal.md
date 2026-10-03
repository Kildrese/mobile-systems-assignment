# Proposal

## Why

Assignment 1B asks for an agentic tracker: an agent that finds the top K developments on a topic, ranks and summarizes them with sources, and reports what is new on the next run. Most of the grade depends on runtime behavior that has to be built before any tracking logic: a hand-written loop with enforced budgets, classified API failures, fetch guardrails, retrieved text treated as data, persisted state and a trace log. The assignment forbids agent frameworks (LangChain, CrewAI and similar) because those hide the parts being graded. This change builds that foundation as a general agent runtime. Nothing in it is tied to a use case: the topic, instructions, enabled tools and allowed hosts are all policy, so the same runtime can track any topic by swapping `config.yaml`. The Assignment 1 app is frozen on the `assignment-1a` branch, so `master` is free to grow.

## What Changes

- New Python package `backend/tracker/`. It sits next to the FastAPI app but does not import it, and it needs neither Postgres nor Docker. From a clean clone, `uv sync` plus two API keys is enough to run it.
- A policy file, `config.yaml`, at the repository root. It holds the topic, K (3 to 10), the model, the instructions, the enabled tools, the limits (`max_steps`, `max_fetches`, `max_searches`, a token budget, a cost budget, wall-clock time) and the allowed URL schemes and hosts. Invalid policy stops the run before any network call.
- An agent loop written by hand: model call, then tool calls, then observation, repeated. Code checks budgets before every model call and every tool call. When a budget runs out, the run stops and writes a report marked **partial** from the evidence gathered so far.
- An LLM client for OpenAI-compatible chat-completions APIs, set to Groq by default. Gemini, OpenRouter and Claude can be swapped in through config. Failures are sorted into **transient** (timeouts, connection errors, per-minute 429s, 5xx), which are retried with capped exponential backoff, and **terminal** (bad key, daily or monthly quota, payment required), which stop the run with a clear message. A daily quota is never retried.
- Three tools: `search_web(query)` (Tavily), `fetch_article(url)` and `finish(report)`. Each one runs without the model via `python -m tracker.tools <tool> ...`.
- Guardrails in `fetch_article`, checked before any request: only http(s), every hop of a redirect checked again, hosts that resolve to loopback, private, link-local or other non-public addresses rejected, the connection pinned to the address that passed the check, a timeout, a response size cap, and a content-type allowlist.
- Retrieved web text reaches the model only inside labeled, fenced data blocks. Instructions, the tool set and budgets live in code and config, and nothing the model or a page says can change them.
- SQLite state in a git-ignored file. It records runs, fetched articles (canonical URL, content hash, extracted text) and the final ranked items, so a later run can skip articles it already has.
- A JSONL trace log per run under `traces/`. It records every model call and tool call with step, tool, arguments, status, latency, tokens and credits.
- No secrets in the repo: `GROQ_API_KEY` and `TAVILY_API_KEY` come from the environment. `backend/.env.example` lists them with empty values.
- A new CI job runs the tracker's lint and unit tests without Postgres or network access.

Out of scope, each a follow-up change: the recrawl diff (New, Still in top K, Dropped) and same-development detection, quote-level provenance checks, the concrete use case (topic, instructions, host allowlist and any source-specific connectors), the web UI and API endpoints for viewing reports, and `AGENT.md` plus the graded runs.

## Capabilities

### New Capabilities
- `tracker-config`: the `config.yaml` policy file and environment secrets. Covers which settings exist, how they are validated, and how a bad policy fails before any call is made.
- `agent-loop`: the hand-written loop. Covers step order, budget enforcement, partial reports on exhaustion, and the rule that retrieved text is data that cannot change instructions, tools or budgets.
- `api-failure-handling`: how failures from the model provider and search provider are classified, retried with capped backoff, or turned into a clean terminal stop.
- `tracker-tools`: the `search_web`, `fetch_article` and `finish` contracts, argument validation, and running each tool from the command line.
- `fetch-guardrails`: the network safety rules `fetch_article` enforces before and during a request.
- `tracker-state`: SQLite persistence of runs, articles and ranked items between runs, and skipping articles already stored.
- `trace-log`: the per-run JSONL record of every model and tool call.

### Modified Capabilities
<!-- None: the tracker is a separate package; existing backend, frontend and script behavior is unchanged. -->

## Impact

- **Code**: new `backend/tracker/` package with its tests in `backend/tests_tracker/`. These tests need no database, so they live outside `backend/tests/`, whose conftest requires Postgres. The FastAPI app is untouched.
- **Dependencies** (backend): `httpx` (already pulled in by `fastapi[standard]`, now a direct dependency), `pyyaml`, and `beautifulsoup4` for HTML-to-text. No agent framework. No vendor SDK: the model is called over HTTP, so retries stay under our control.
- **Repository layout**: `config.yaml`, `reports/` and `traces/` at the root, where graders look for them. The SQLite state file is git-ignored.
- **External services**: Groq (LLM, free tier) and Tavily (search, 1,000 free credits a month). Both need keys that the user creates and keeps out of the repo.
- **CI**: one extra job in `.github/workflows/ci.yml` (ruff, then pytest on `tests_tracker`, no services).
- **Docs**: a tracker section in `README.md` and a new `docs/tracker.md`.
