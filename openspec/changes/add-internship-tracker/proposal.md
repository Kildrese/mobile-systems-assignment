# Proposal

## Why

The tracker core (merged to `master`) is a general runtime, and `add-agent-orchestration` adds a general multi-agent layer to it (agent profiles, two-level budgets, per-agent privileges, a stage conductor). This change is the concrete use case built on both. Our use case is tracking Summer 2027 software and ML internships at NYC startups, and it has needs that one research loop serves badly. Most postings sit in public job-board JSON (Greenhouse, Lever, Ashby), not in news articles. Whether a posting is still open is a fact we can check, not something to judge. And the useful daily view is cumulative: what's new, everything still open, and what closed. Splitting the work across a few narrow agents, each with its own model, tools and budget, also separates privileges. The one agent that reads the open web can only propose sources, and the agents that write records never see search results. That gives the assignment's injection and budget questions concrete answers.

## What Changes

- **Use case `internships`.** `config.yaml` sets `use_case: internships` and defines three agent profiles (Scout, Curator, Editor) with the orchestration layer's profile format. The pipeline is fixed in code: Scout (agent), Collect (code), Curate (agent), Liveness (code), Rank (code), Edit (agent), Report (code). Stages pass typed records through SQLite.
- **Scout agent** (`openai/gpt-oss-120b`). Uses `search_web` and `fetch_article` to find companies and job boards worth tracking, and proposes them with `propose_source`. Code validates each proposal and adds it to the watchlist.
- **Collectors** (code, no LLM). Read the public Greenhouse, Lever and Ashby board APIs for every watchlist source, with conditional requests, and pre-filter postings by title keywords and location from config.
- **Curator agent** (`openai/gpt-oss-20b`, which draws on separate per-model quota). Turns raw postings into opportunity records with verbatim quotes for key fields. It fetches a posting's detail page when the JSON lacks something, merges duplicates across sources (`mark_same`), and flags unclear postings. Code rejects any record whose quotes are not in the stored posting text.
- **Liveness and lifecycle.** Each opportunity is `open`, `closed` or `unknown`. A posting missing from a board that was read successfully is closed. A board that could not be read changes nothing. Postings found outside the job boards are re-checked through the fetch guardrails, and a 404, a 410 or closing wording marks them closed.
- **Ranking in code** with weights from config: role type, term, location, and recency. Work-authorization wording is shown as a quote and never used to score or filter.
- **Editor agent** (`openai/gpt-oss-120b`). Writes short, quote-grounded summaries of why each top-K opportunity and each new one shown in full fits. It can read records and postings but cannot change ranks, statuses or sources.
- **Cumulative report.** Three sections: **New since last run** (ranked, the top K in full), **Still open** (every earlier opportunity that is still open, accumulated across runs and never shown again as new, with the current top K marked) and **Closed since last run**.
- **State.** The SQLite state gains `sources`, `opportunities`, `opportunity_links` and an HTTP validator cache (ETags).

## Capabilities

### New Capabilities
- `internship-pipeline`: the `internships` use case: its three agents and their privileges, the fixed stage order, and how a run degrades when a budget or provider runs out.
- `opportunity-sources`: the watchlist, proposing sources from the Scout, the Greenhouse, Lever and Ashby collectors, conditional requests, and the pre-filter.
- `opportunity-curation`: the opportunity record, the Curator's tools, quote verification, and same-role resolution.
- `opportunity-lifecycle`: open, closed and unknown status, the liveness checks, and first-seen and last-seen tracking across runs.
- `opportunity-report`: ranking in code, the Editor's summaries, and the cumulative New, Still open and Closed report.

### Modified Capabilities
- `tracker-config`: the policy file may also define `options`, use-case settings validated by the use case before any network call; and `python -m tracker run` checks at startup that the providers still offer the models the policy names.
- `agent-orchestration`: a daily quota skips only the later stages on that model, since Groq counts daily quotas per model; other terminal failures still skip the whole provider. The run's stop reason names a provider failure ahead of an earlier budget stop.

## Impact

- **Code**:
  - New package: `usecases/internships/` (store, sources, curation, lifecycle, ranking, editing, report, wiring; see design D12).
  - Changed core module: `fetch.py` gains optional request headers (for `If-None-Match`/`If-Modified-Since`), `304` pages carrying their validators, and the HTTP status on `FetchError`. All of it is backward-compatible. The internship schema is versioned separately, so `state.py` does not change.
- **Small runtime changes** (all backward-compatible):
  - `config.py`: top-level `options` and `internships` in the known use cases.
  - `tools.py`: `ToolSpec.budget`, so a use-case tool can draw on `max_fetches` or `max_searches`. `python -m tracker.tools` loads the known use cases, so their tools have commands.
  - `agents.py`: `finish` with empty arguments now goes to the finish handler (it used to be refused as invalid), and tool budgets follow `ToolSpec.budget`.
  - `fetch.py`: optional request headers, `304` pages with validators, and the HTTP status on `FetchError`.
- **Repository layout**: the root `config.yaml` runs the internship use case; the single-agent policy moves to `examples/single-agent.yaml`.
- **Dependencies**: needs `add-agent-orchestration` implemented first. This branch is stacked as master → orchestration → internship.
- **Policy**: `config.yaml` switches to the internship use case: topic, K, agents, watchlist, filters, ranking weights, and fetch hosts narrowed to the job-board domains plus watchlist domains for every agent except the Scout.
- **External services**: `boards-api.greenhouse.io`, `api.lever.co` and `api.ashbyhq.com` (public, no keys), plus a second Groq model. The cloud dev environment must allowlist these hosts for real runs.
- **Docs**: `docs/tracker.md` gains an internship use-case section, and the README shows the internship run.
