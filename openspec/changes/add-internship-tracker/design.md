# Design

## Context

This change is the first use case on the tracker core (merged to `master`) and `add-agent-orchestration` (proposed, `feat/agent-orchestration`). It relies on the orchestration layer's agent profiles, two-level budgets, tool registry with per-agent visibility, `fetch_hosts`, stage conductor and trace binding, and does not change them. Relevant shape of the core code:
- `config.py`: a frozen `Policy` with one `model` and one `Limits`, and no tool settings: tools are fixed in code.
- `loop.py`: `Runner` owns the run lifecycle (state, trace, budget, clients) and the loop in `_loop()`. Dispatch, finish handling, synthesis and the fallback report live on the same class.
- `budget.py`: a single `Budget` built from the policy, checked by `check_model_call()` and `check_tool()`.
- `state.py`: `StateStore` with a `MIGRATIONS` list and `PRAGMA user_version`. `tools.py`: a `Toolbox` with `search_web`/`fetch_article`, plus a CLI.
- `report.py`: renders one "Top developments" list.

The motivation is in proposal.md (Why). The free-tier context: Groq limits each model separately, so `openai/gpt-oss-120b` (8K TPM / 200K TPD) and `openai/gpt-oss-20b` are separate pools. We confirm the figures on Groq's page before the graded runs. (The first choice, `llama-3.1-8b-instant`, was retired by Groq: it answered `404 model_not_found` in the first real run.)

## Goals / Non-Goals

**Goals:**
- Every decision that can be made from data is made by code: liveness, ranking, deduplication by id or URL, quote verification. Models decide only where judgment is needed: which sources to track, how to read a messy posting, whether two postings are the same role, and how to phrase a summary.
- A run always produces a report, even when every model is unavailable.

**Non-Goals:**
- Running stages in parallel. Stages run one after another. Separate quotas make parallel stages possible later, but they would make the trace harder to read.
- A supervising model, or agents talking to each other.
- Scraping sites behind a login (LinkedIn, Handshake). Only public board APIs and public pages.
- The web UI (a later change).

## Decisions

### D1. Use case as a plugin
`usecases/internships/wiring.py` registers its tools in the orchestration tool registry and returns its stage list, in order, to the conductor. `use_case: internships` in policy selects it. Agent stages are generic `AgentLoop`s with a task prompt per stage. Code stages are plain functions over `StageContext`. Nothing in `loop.py`, `budget.py` or `conductor.py` changes here.

### D2. Tools added by this use case
- `propose_source` (Scout)
- `get_posting`, `fetch_posting_detail`, `save_record`, `mark_same`, `flag_unclear` (Curator)
- `get_opportunities` (Editor)

The Editor ends with its own finish handler (`summaries` instead of `items`). Every tool registers a CLI command, so graders can call each one without a model. `fetch_posting_detail` is `fetch_article` under the Curator's `fetch_hosts`.

### D3. Budget split
The three profiles' limits add up within the global caps (validated by the orchestration layer). Defaults are in D10.

### D4. Stages
The stages, in order:
```
scout     AgentLoop(scout)       -> sources(proposed)  -> validate -> sources(active)
collect   code, per source      -> raw_postings        -> prefilter
curate    AgentLoop(curator) per posting, most relevant first -> opportunities, opportunity_links
liveness  code                  -> opportunities.status / evidence
rank      code                  -> ranks (this run)
edit      AgentLoop(editor)      -> summaries (this run), validated
report    code                  -> reports/<run_id>.md
```
Collect, Rank and Report are `required`. Skipping and outcome rules come from the conductor. Inside Collect, a terminal error from a job-board host only marks that source `unreadable`; it does not stop the stage.

Curate gives the agent one batch (default 5 postings) per user turn: "Process postings A–E; each must end saved, linked or flagged." When a batch is done, the conductor clears the conversation and sends the next batch. That keeps the 8B model's context small and fits the 6K TPM limit. The same-role candidates for each posting (D7) are included in the batch prompt.

### D5. Collectors
In `usecases/internships/sources.py`, one collector per board type, each `collect(source, http) -> list[RawPosting]`:
- Greenhouse: `GET https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true` (`content` is HTML-escaped, so unescape it and convert to text)
- Lever: `GET https://api.lever.co/v0/postings/{company}?mode=json`
- Ashby: `GET https://api.ashbyhq.com/posting-api/job-board/{name}?includeCompensation=true`

All of them go through the `BoardHttp` seam (D12) over the core `fetch` path, so guardrails and address pinning apply, with a JSON content type and a larger `max_bytes` for boards (config `collect.max_bytes`). Board identifiers are checked with `^[a-z0-9][a-z0-9-_.]{0,80}$` before any URL is built. ETag and Last-Modified values are stored in `http_cache(url, etag, last_modified, body_hash, at)`. A `304` reuses the `raw_postings` from the last successful read.

### D6. Internship schema
The use case keeps its own schema version in a `component_versions(name, version)` table, not in the core's `PRAGMA user_version`, so the core never needs to know these tables exist. `http_cache` stores the response body, so a `304` re-parses the last body and the board still counts as read with its current postings.

```
sources(id PK, company, kind, board, url, added_by, added_run, active, last_read_run, last_read_status)
raw_postings(id PK, source_id, external_id, url, title, location, text, updated_at, content_hash, seen_run, pending)
opportunities(id PK, company, title, role_type, term, locations_json, remote, url, fields_json, quotes_json,
              status, status_evidence, first_seen_run, last_seen_open_run, closed_run, unclear_reason)
opportunity_links(opportunity_id, raw_posting_id, linked_by, reason)
ranks(run_id, opportunity_id, rank, score, top_k)
summaries(run_id, opportunity_id, text)
http_cache(url PK, etag, last_modified, body_hash, at)
```
`raw_postings` is unique on `(source_id, external_id)`, falling back to `canonical_url` for pages. The `pending` flag survives across runs, so unfinished curation carries over for postings still listed: Curate takes only pending postings seen in the current run.

### D7. Quote verification and same-role candidates
Normalization: NFKC, collapse whitespace, lowercase, and unify straight and curly quotes and dashes. A quote must be at least 3 characters and be a substring of the normalized posting text (board text plus any fetched detail page for that posting). Candidates for same-role matching: same normalized company, and title token Jaccard ≥ 0.5 after removing filler words ("intern", "internship", "summer", years, punctuation). An exact `(board, external_id)` or canonical URL match is linked by code without asking the model.

### D8. Ranking
`score = w_role * role_match + w_term * term_match + w_loc * loc_match + w_recent * recency + w_focus * focus`, where `focus` is 1 when the title names a role the search is for (`ranking.focus_keywords`: software, ML, data, ...); the first real run put a design internship in the top K without it. Each match is 0, 0.5 (`unknown`) or 1. Recency decays linearly over `ranking.recency_days`. Weights live in config. Ranks are stored per run, so "top K" in any past report can be reproduced.

### D9. Summary checks
The Editor's `finish(summaries=[{opportunity_id, text}])` is checked per summary: the id exists and is in the requested set, the text is at most 3 sentences, and every number, currency amount or date in the text appears in the record's fields or quotes (regex extraction plus normalization). A rejected summary is dropped and the rejection is traced. The report then falls back to the fields alone.

### D10. Policy shape (internship `config.yaml`)
As built, use-case settings live under a top-level `options` section (the core rejects unknown keys), and agent settings under `agents.<name>.options`. The committed `config.yaml` is the source of truth; the sketch below shows the original plan.

```yaml
use_case: internships
topic: "Summer 2027 software/ML internships at NYC startups"
k: 5
model: { provider: groq, name: openai/gpt-oss-120b, max_output_tokens: 1024, reasoning_effort: low }
limits: { max_steps: 60, max_searches: 6, max_fetches: 40, max_tokens: 150000, reserve_tokens: 5000, max_cost_usd: 0.5, max_wall_seconds: 900 }
agents:
  scout:   { model: {name: openai/gpt-oss-120b}, tools: [search_web, fetch_article, propose_source],
             limits: { max_steps: 12, max_tokens: 50000, max_searches: 6, max_fetches: 10 }, options: { max_new_sources: 5 } }
  curator: { model: {name: openai/gpt-oss-20b, max_output_tokens: 1024},
             tools: [get_posting, fetch_posting_detail, save_record, mark_same, flag_unclear],
             limits: { max_steps: 35, max_tokens: 70000, max_fetches: 20 }, options: { batch_size: 1 },
             fetch_hosts: [boards.greenhouse.io, job-boards.greenhouse.io, jobs.lever.co, jobs.ashbyhq.com, "<watchlist domains>"] }
  editor:  { model: {name: openai/gpt-oss-120b}, tools: [get_opportunities, finish],
             limits: { max_steps: 6, max_tokens: 25000 } }
watchlist: [ { company: "...", kind: greenhouse, board: "..." }, ... ]
filters: { title_keywords: [intern, internship, co-op], locations: ["New York", "NYC", "Brooklyn", "Remote"] }
ranking: { weights: { role: 3, term: 3, location: 2, recency: 1, focus: 3 }, recency_days: 30 }
lifecycle: { closed_patterns: ["no longer accepting", "position has been filled", "job is closed"] }
```
Profiles inherit any model fields they omit (provider, temperature) from the top-level `model`. There is no top-level `tools` list: the use case registers its tools in code, and each profile selects from them.

### D11. Network shape per run (for AGENT.md Q2)
Expected round trips on a first run:
- Scout: ~12 Groq calls, ≤6 Tavily searches and ≤10 page fetches.
- Collect: one request per watchlist source (~15–20).
- Curate: about one Groq call per posting (a few thousand tokens, the posting in the task) and ≤20 detail fetches. The first real run used two calls per posting in a conversation that grew to ~6K tokens, and the per-minute token limit let it save only 7 of 28 postings in the 900 s budget; what is left waits for the next run, most relevant first.
- Liveness: requests only for page-only opportunities.
- Edit: ≤6 Groq calls.

On later runs most board requests return `304`, and only new postings are curated. Each host gets one reused `httpx.Client`, so keep-alive and TLS session reuse apply. Requests go out one at a time, which is polite toward the job boards.

### D12. Working in parallel with orchestration: the seam
This change is implemented while `add-agent-orchestration` is still being built, so the use-case code has to compile and be tested without it. The rule: **domain code depends only on the merged core; only the wiring layer depends on orchestration.**

```
backend/tracker/usecases/internships/
  store.py        OpportunityStore: the internship tables, over the core StateStore connection   [parallel]
  sources.py      watchlist, identifier checks, Greenhouse/Lever/Ashby collectors, prefilter   [parallel]
  curation.py     quote checks, matching, candidates, the Curator's tool functions             [parallel]
  lifecycle.py    board and page liveness                                                        [parallel]
  ranking.py      scoring, ranks                                                                 [parallel]
  editing.py      summary checks, the Editor's tool functions                                    [parallel]
  report.py       cumulative renderer                                                            [parallel]
  wiring.py       ToolSpecs, Stage objects, prompts, use-case registration                      [after orchestration]
```

Domain functions take their dependencies explicitly and return the core's `ToolOutcome` (from `tracker.tools`) for anything a model will call, for example:

```python
def save_record(store: OpportunityStore, posting_id: int, record: dict) -> ToolOutcome
def mark_same(store: OpportunityStore, posting_id: int, opportunity_id: int, reason: str) -> ToolOutcome
def propose_source(store: OpportunityStore, seen_urls: set[str], run_id: str, cap: int, **args) -> ToolOutcome
def collect_source(source: Source, http: BoardHttp, trace: Trace) -> CollectResult
```

They never import `tracker.conductor`, `tracker.agents`, or registry symbols. HTTP for boards and pages goes through a small `BoardHttp` protocol, implemented over the core `fetch.fetch_page` path (guardrails and pinning included), so tests can inject respx transports.

`wiring.py` is the only file that touches orchestration. It assumes the interfaces in `add-agent-orchestration` design D4/D6: `ToolSpec(name, args_model, schema, handler, cli)` plus `register(spec)`; `Stage` with `name`, `kind`, `agent`, `required`, `providers` and `run(ctx) -> StageOutcome`; and `StageContext(policy, profile, state, trace, budget, clients)`. If the orchestration implementation lands with different names, only `wiring.py` changes.

## Risks / Trade-offs

- [The 8B model makes malformed tool calls] → Strict argument validation already returns error results. The core's `ModelOutputError` handling re-prompts once. Small batches limit the damage, and a posting that fails twice is flagged `unclear` by code.
- [Pre-filter keywords miss postings with unusual titles] → The keywords live in config, filtered counts are traced, and the Scout can also bring in page sources. Accepted for scope.
- [A board API changes shape or blocks us] → Each collector validates the response with pydantic, a source that fails is `unreadable` without being closed, and fixtures in tests pin the expected shape.
- [Cumulative "Still open" grows long] → Shown as a compact table. Only the opportunities shown in full get summaries (the first K new ones and the top K, at most 2K), so the Editor's cost does not grow with the list and its summaries fit in one reply (its output cap is 2,048 tokens, since gpt-oss reasoning counts against it).
- [Grader expects "Still in top K" and "Dropped"] → Still open marks the top K, Closed is the dropped list, and AGENT.md explains the mapping.
- [The orchestration layer isn't implemented yet] → Implement `add-agent-orchestration` first. This change only adds use-case modules, so merges from below should be clean.

## Migration Plan

The internship schema is additive. A state file from the core works as is, and its `articles` and `items` tables stay. Archive order: `add-agent-orchestration`, then this change. Rollback means reverting the change. Old state files remain readable by the core, which ignores the extra tables.

## Open Questions

- The initial watchlist: about 15 NYC startups whose Greenhouse, Lever or Ashby boards are public. The list is data in `config.yaml` and can be finalized during implementation, after checking each board URL by hand.
