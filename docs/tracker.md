# Tracker

For a step-by-step walkthrough of the loop itself, see [agent-loop.md](agent-loop.md).

The tracker is an agent that finds the top K developments on a topic, ranks and summarizes them with sources, and writes a Markdown report. Its loop is written by hand in `backend/tracker/` (no agent framework). Code enforces the budgets, classifies API failures, guards every fetch and records each call in a trace.

It shares `backend/`'s uv project but imports nothing from the FastAPI app and needs neither Postgres nor Docker.

## Setup

You need Python 3.12+, [uv](https://docs.astral.sh/uv/) and two free API keys:

| Variable | Where to get it |
| --- | --- |
| `GROQ_API_KEY` | <https://console.groq.com/keys> (the model provider, free tier) |
| `TAVILY_API_KEY` | <https://app.tavily.com> (search, 1,000 free credits a month) |

```bash
cd backend
uv sync
cp .env.example .env    # then fill in GROQ_API_KEY and TAVILY_API_KEY
```

Keys come only from the environment or `backend/.env`, never from `config.yaml`. `.env` is git-ignored.

## Running

```bash
cd backend
uv run python -m tracker run                       # policy from config.yaml at the repo root
uv run python -m tracker run --config other.yaml   # another policy file
uv run python -m tracker run --out my-report.md    # another report path
uv run python -m tracker run --config ../config.smoke.yaml --out ../reports/smoke.md
```

`config.smoke.yaml` is `config.yaml` with small budgets (300 s, 2 searches, a few steps per agent): a real run in a few minutes to try a change. It keeps its own state file, `.tracker/smoke.sqlite`, so it never changes the state the graded runs build on.

The command prints the outcome and the report and trace paths.

| Exit status | Meaning |
| --- | --- |
| `0` | Complete: the model called `finish` within all budgets |
| `2` | Partial: a budget ran out; the report uses the evidence gathered so far |
| `3` | Terminal provider failure (bad key, quota, payment, unreachable); a partial report is still written |
| `1` | Invalid policy, missing key, a model the provider does not offer, or another run holds the state file. No model or search call was made |

Before the run starts, the command asks each model provider for its model list (one request per provider) and stops with exit `1` if the policy names a model that is not on it, such as a retired one. If the list cannot be fetched (network down, rejected key), the check is skipped and the run's own failure handling takes over.

## Running the tools without the model

Each tool runs on its own from `backend/`. The result is printed as JSON; the exit status is non-zero on a validation, guardrail or provider error.

```bash
uv run python -m tracker.tools search_web "open-source robotics foundation model"   # needs TAVILY_API_KEY
uv run python -m tracker.tools fetch_article https://example.com/
uv run python -m tracker.tools fetch_article http://127.0.0.1:8000/   # blocked_address, no connection made
uv run python -m tracker.tools finish report.json                     # writes reports/manual-<time>.md
```

`finish` reads a JSON file shaped like the tool's arguments:

```json
{
  "items": [
    {"title": "...", "summary": "...", "sources": ["https://..."]}
  ],
  "note": "optional"
}
```

All three accept `--config PATH` before the tool name. `finish` also takes `--out PATH`.

## Policy (`config.yaml`)

Everything the agent may do is in one file at the repository root. It is validated in full before the first network call (unknown keys are errors, so typos fail loudly) and frozen for the run: neither the model nor a fetched page can change it. Relative paths resolve against the policy file's directory.

| Field | Meaning |
| --- | --- |
| `topic`, `k` | What to track and how many items to report (3 to 10) |
| `model` | `provider` (a key of `providers`), `name`, `max_output_tokens`, optional `temperature`, `reasoning_effort` and `timeout_seconds` |
| `providers.<name>` | An OpenAI-compatible chat-completions API: `base_url`, `key_env` (the variable holding its key), prices per million tokens, `quota_patterns` |
| `search` | Tavily: `key_env`, `max_results`, `depth` (`basic` costs 1 credit, `advanced` 2), `price_per_credit`, `quota_patterns` |
| `limits` | Budgets, see below. Every one is required and positive |
| `retry` | `max_attempts`, `base_seconds`, `max_wait_seconds` |
| `fetch` | Guardrail settings, see below |
| `instructions` | The system prompt; `{topic}` and `{k}` are filled in |
| `state_path`, `reports_dir`, `traces_dir` | Defaults `.tracker/state.sqlite`, `reports`, `traces` |
| `use_case`, `agents`, `options` | Multiple agents for a use case built into the tracker; see [Multiple agents](#multiple-agents) and [The internship use case](#the-internship-use-case) |

Switching provider is a config change: add an entry under `providers` (Groq, OpenRouter and Gemini's OpenAI-compatible endpoint all work) and point `model.provider` at it.

## Budgets

Code checks the budgets before every model call and every tool call. An action that would exceed a budget is not performed.

| Limit | Counts |
| --- | --- |
| `max_steps` | Model calls. An unknown tool or invalid arguments also costs a step |
| `max_searches`, `max_fetches` | Tool calls that reach the network. A fetch served from state is free |
| `max_tokens` | Prompt plus completion tokens for the whole run |
| `reserve_tokens` | Held back from `max_tokens` for the final synthesis call |
| `max_cost_usd` | Tokens times the provider's price, plus search credits times `price_per_credit` |
| `max_wall_seconds` | Wall-clock time, including retry waits |

When a tool budget runs out, the model gets an error result saying so and can still finish. When the step, token, cost or time budget runs out, the run stops and writes a **partial** report: first by one last model call with no tools, from the reserved tokens, then, if that is not possible or fails, by code alone, listing the sources gathered with titles and URLs.

To stay within Groq's per-minute token limit, page text sent to the model is cut to `fetch.max_chars_for_model` (the full text is kept in state), and older tool results are shortened once newer ones arrive.

## Failure handling

Every failed call to the model or search provider is classified and the class is recorded in the trace.

| Class | Cases | What happens |
| --- | --- | --- |
| Transient | Timeouts, connection errors, HTTP 408, 5xx, a per-minute 429 | Retried with exponential backoff and jitter, honoring `retry-after`, up to `retry.max_attempts` |
| Terminal `auth` | 401, 403 | Stop: the key was rejected |
| Terminal `payment` | 402 | Stop: the provider wants payment or credit |
| Terminal `quota` | Tavily 432; a 429 whose body matches `quota_patterns` (Groq daily RPD/TPD); a `retry-after` longer than `retry.max_wait_seconds` | Stop, never retried. The message says when it resets if the provider does |
| Terminal `request` | Any other 4xx | Stop |
| Terminal `unreachable` | Transient failures that used up all attempts | Stop |

A terminal failure prints one line naming the provider, the class and the likely fix (no stack trace), writes a partial report and the trace, and exits `3`. After a model-provider failure no further model call is made. A Groq 400 `tool_use_failed` or `output_parse_failed` (the model emitted a malformed tool call, or output Groq could not parse) is not a provider failure: the model is told and the run continues.

## Fetch guardrails

`fetch_article` checks every URL before any connection, and every redirect hop again:

- Only the schemes in `fetch.allowed_schemes` (`http` and `https` at most). URLs without a host or with credentials are rejected (`invalid_url`, `scheme_not_allowed`).
- The host must match `fetch.allowed_hosts`: exact names, `*.domain` or `*` for any public host (`host_not_allowed`, checked before DNS).
- Every address the host resolves to must be globally routable: no loopback, private, link-local (cloud metadata), CGNAT, multicast, reserved or unspecified addresses, including IPv4-mapped IPv6 and decimal, octal or hex IPv4 forms like `http://2130706433/` (`blocked_address`).
- The connection goes to the address that passed the check, with the original name in the `Host` header and as the TLS server name, so a second DNS answer (rebinding) cannot redirect it and the certificate is still verified.
- Redirects are followed by hand, at most `fetch.max_redirects` (`too_many_redirects`).
- Connect and read timeouts plus an overall `deadline_seconds` (`timeout`); a `Content-Length` or streamed body over `max_bytes` (`too_large`); only HTML, plain text and JSON (`unsupported_content_type`).

Inside a run, a guardrail rejection is an error result for the model, not a crash.

## Retrieved text is data

Search results and page text reach the model only inside `<untrusted_data>` blocks, labeled as untrusted, with look-alike delimiters in the content escaped so a page cannot close its block. The system prompt comes only from policy. A regex detector flags instruction-like text (`injection_suspected: true` on the trace event); it is a signal for review, not the defense. The defense is that the tools, their schemas, the budgets and the guardrails are fixed in code and policy, and that `finish` items citing URLs the run never saw are dropped.

## State, reports and traces

| Path | Contents | In git |
| --- | --- | --- |
| `.tracker/state.sqlite` | Runs (status, stop reason, usage), fetched articles by canonical URL with their text, searches, reported items, and the fetch log | No |
| `reports/<run_id>.md` | The report: topic, run id, time, status, budget used, ranked items with sources | No |
| `traces/<run_id>.jsonl` | One JSON event per model call attempt and tool call, then a summary event | No |

**Fetch log.** `fetch_log` has one row for every document a run tried to read: a page (`fetch_article`, `fetch_posting_detail`), a job board read by Collect, or a posting Collect's prefilter kept. Each row has the stage, kind, URL (cut to 2,048 characters), title (cut to 300, empty when not fetched), time, status and reason:

| Status | Means |
| --- | --- |
| `fetched` | Downloaded in this run (a posting: first seen in this run) |
| `skipped` | Already seen: served from state, a `304`, or a posting first seen in an earlier run |
| `rejected` | Refused by a guardrail: scheme, credentials, host, address, DNS, size, content type or redirects |
| `failed` | Tried and failed: timeout, connection error, HTTP error, unparseable board |

A fetch refused by a budget made no request and is not logged; it is in the trace. The log is published to `tracker_articles` and shown on `/internships/runs/:id`.

Canonical URLs lowercase the scheme and host and drop the fragment, default ports and tracking parameters (`utm_*`, `gclid`, `fbclid`, `ref`), so a known article is served from state without a request. Only one run may use the state file at a time; a second one exits with a message.

Trace events carry the step, kind (`model`, `tool`, `synthesis`, `summary`), tool or model name, arguments, status (`ok`, `cached`, `error`, `retry`, `blocked`, `budget`), latency, and where they apply tokens, credits, HTTP status, failure class and attempt. Fields over 2,000 characters are cut with the original length recorded, and API keys are redacted.

## Multiple agents

A use case can split the work across several narrow agents, each with only the model, tools, hosts and budget its job needs. Without an `agents` section the tracker runs the single agent described above, unchanged.

**Profiles.** `agents` maps lowercase names to profiles. A profile selects tools registered in code (the core `search_web` and `fetch_article`, plus any the use case registers); `finish` is always offered, and policy can never add a tool. `model` fields left out are inherited from the top-level `model`. Two agents of the same use case:

<!-- agents-example -->
```yaml
use_case: <name>          # a use case built into the tracker; required with agents
agents:
  scout:
    tools: [search_web]
    limits: {max_steps: 4, max_tokens: 8000, max_searches: 3}
    instructions: Find candidate pages about {topic}.
  reader:
    model: {name: openai/gpt-oss-20b}     # provider, temperature, ... from `model`
    tools: [fetch_article]
    fetch_hosts: ["*.example.com"]
    limits: {max_steps: 4, max_tokens: 8000, max_fetches: 4}
    instructions: Read the pages the scout found and extract the facts.
```

**Budget split.** For `max_steps`, `max_tokens`, `max_searches` and `max_fetches`, the enabled agents' limits must add up to no more than the run's `limits`, or validation fails naming the limit and the total. `max_searches` is required when an agent has `search_web`, and `max_fetches` when it has `fetch_article`. Before every model and tool call, code checks the agent's limits first, then the run's, and charges both. Wall time, cost and `reserve_tokens` are run-level only. A stop reason names the level: `scout.max_steps` for the agent, `max_tokens` for the run.

**Privileges.** An agent is offered only its profile's tools; calling another one returns `unknown_tool` and costs a step. `fetch_hosts` narrows the hosts that agent may fetch (and follow redirects to). Every pattern must be covered by `fetch.allowed_hosts`; it is checked first, then all the core guardrails above still apply. Keys are needed for every provider an enabled agent uses.

**Stages.** The use case defines an ordered list of stages in code: an agent stage runs one agent loop for a profile, a code stage runs plain code. Model output never changes the order. Each stage gets the policy, its own profile, the state store, its trace and its budget, never another agent's conversation: stages hand data on only through records in the state store.

**Outcomes.** Each stage ends `complete`, `partial` (stopped by a budget with its work unfinished, or by a provider failure), `skipped` (its agent has `enabled: false`, or a provider it needs failed for good earlier in the run) or `failed` (it raised). A stage the use case marks required cannot be disabled. The run is `failed` (exit `3`) when a required stage failed; `partial` (exit `2`) when any stage was partial, failed, or skipped after a provider failure; otherwise `complete` (exit `0`). After a terminal failure, later agent stages that need what failed are skipped and the rest, including code stages, still run. A daily quota skips only the stages on that model, because Groq counts daily quotas per model; any other terminal failure (bad key, payment, a rejected request, unreachable) skips every stage on that provider. The run's stop reason names the first provider failure, if any, ahead of an earlier budget stop. A report is written in every case. A use case may define a budget stop as the end of a stage's work; the stage is then `complete`, with a reason naming the rule (the internship Scout does, see below).

**Trace fields.** Every event written during a stage carries `stage`, and agent stages also `agent`. The summary event adds `stages`: per stage its `name`, `agent`, `outcome`, `reason` and `usage`.

## The internship use case

The repository's `config.yaml` runs `use_case: internships`: it tracks Summer 2027 software and ML internships at NYC startups and keeps a cumulative report. The single-agent tracker on a news topic is in `examples/single-agent.yaml` (`uv run python -m tracker run --config ../examples/single-agent.yaml`). The code is in `backend/tracker/usecases/internships/`.

**Pipeline.** Fixed in code:

| Stage | Kind | What it does | Required |
| --- | --- | --- | --- |
| `scout` | agent (`gpt-oss-120b`) | Searches the web and proposes new job boards with `propose_source` | no |
| `collect` | code | Reads every watchlist board (Greenhouse, Lever, Ashby JSON APIs, no keys) and keeps postings whose title and location match `options.filters` | yes |
| `curate` | agent (`openai/gpt-oss-20b`) | Turns pending postings into opportunity records, most relevant first (title matches `ranking.focus_keywords`), one posting per fresh conversation with the posting in its task | no |
| `liveness` | code | Decides open or closed for every opportunity from the boards Collect read | no |
| `assess` | agent (`gpt-oss-120b`) | Rates each open opportunity's fit with `options.profile`, 0 to 3 with a one-sentence reason, once per profile; newest first, 8 per fresh conversation. Only with an `assessor` profile and a profile text | no |
| `rank` | code | Scores open opportunities with `options.ranking` (role type, term, location, recency, focus: a software, ML or data title, and fit when the run has a profile) and marks the top K | yes |
| `edit` | agent (`gpt-oss-120b`) | Writes short summaries for the opportunities the report shows in full: the first K new ones and the top K | no |

**When the Scout is done.** The Scout's work is open-ended, so its stage has a defined end. It is `complete` when it calls `finish`; when code has accepted `max_new_sources` proposals, which ends the stage without another model call (reason `max_new_sources`); or when its own step or token budget stops it after all its searches are used (reason `searches_spent`). It is `partial` when that budget stops it with searches left, when the run's wall clock stops it, or after a provider failure. The reason is in the report's stage table and the trace summary.

**Wall time.** `config.yaml` allows 1,500 seconds: on Groq's free tier much of a run is spent waiting out per-minute token limits. The scheduled job's timeout must exceed `max_wall_seconds` by at least five minutes for setup, saving state and publishing; a test checks the two files agree.

**Privileges.** Only the Scout reads the open web, and it can only *propose* sources. Code accepts a proposal only for a Greenhouse, Lever or Ashby board with a valid identifier, never a page (a page the Scout read could otherwise put itself on the watchlist for every run), citing an `evidence_url` the Scout actually saw in this run, up to `max_new_sources` per run. The Curator has no search and fetches only a posting's own page on the job-board posting hosts (`fetch_hosts`); posting text and titles reach it only as untrusted data, in its task or through `get_posting`. The Editor can read records but cannot change ranks, statuses or sources. The Assessor has no tool besides `finish`; records and the first 1,500 characters of each posting reach it in its task as untrusted data. Agents never talk to each other: stages hand on records through the state file.

**Verified records.** Every field the Curator fills in (title, role type, term, locations, remote, pay, deadline, work authorization) must carry a quote that code finds word for word in the posting text, after normalizing case, whitespace, curly quotes and dashes; otherwise `save_record` answers `quote_not_found`. If the Curator sends a record for the same posting again with quotes that are still not found, those fields are saved as `unknown` (the title must still be found), so a repeated wrong quote costs one retry, not many. Role type and remote policy are listed as allowed values in the schema, and other capitalizations are accepted. Company and URL come from the source, never from the model. Work-authorization wording is stored as a quote only: it never filters or ranks an opportunity. A posting whose URL is already linked to an opportunity is linked by code; the Curator may link postings only within the same company (`mark_same`), otherwise `company_mismatch`. A posting left unresolved in two batches is parked as unclear.

**Fit.** `options.profile` is a few lines on the candidate and the internship they want; it goes into the Assessor's instructions through `{profile}`. It is committed, so it leaves out employers and anything private. Code stores a rating only for an opportunity in the batch, with a fit from 0 to 3 and a reason of at most 200 characters that passes the summary check below; rejected ratings go back to the model once. Each opportunity keeps one rating, tagged with the SHA-256 of the stripped profile, and is not rated again while the profile is unchanged, also after it closes and reopens. After a profile edit, ratings are redone over the following runs, newest first, and the old ones count until replaced. In the score, fit is `ranking.weights.fit` (default 3) × fit / 3, and an unrated opportunity scores half, like any unknown field. Without a profile, fit is not a criterion and the report doesn't mention it.

**Lifecycle.** An opportunity listed on a job board closes only when every board it is on was read in this run and none lists it; a board that cannot be read changes nothing (the report notes "not checked this run"). Liveness makes no requests of its own: Collect has read the boards. An opportunity that appears again reopens and keeps its first-seen run.

**Report.** It compares this run's top K with the last run's: the newest earlier finished run that has ranks, so a run that failed before Rank is skipped. Four sections, each opportunity in at most one (the first that applies):

1. **New since last run**: first seen in this run, by rank; the first K with all fields, the work-authorization quote and the summary.
2. **Still in top K**: the rest of this run's top K, with each one's rank in the last run, or "entered the top K".
3. **Dropped**: each opportunity in the last run's top K that is not in this one, either `closed` (with the evidence: the boards read without the job) or `outranked` (with its new rank), plus any other opportunity closed in this run.
4. **Also open**: every other earlier opportunity that is still open, accumulated across runs, in one table by rank.

On a first run every open opportunity is new, and Still in top K and Dropped say there is no earlier run to compare with.

Summaries are rejected when they run over 3 sentences or mention a number or month that is not in the record; the report then shows the fields alone. With a profile, full entries show "**Fit:** n/3, reason", and the Still in top K and Also open tables have a Fit column (`-` when not rated).

**Network.** Boards are read with `If-None-Match`/`If-Modified-Since`; a `304` re-parses the cached body, so an unchanged board costs no download and still counts as read. Board JSON may be up to `options.board_max_bytes` (default 8 MB); pages keep `fetch.max_bytes`. The Curator's detail-page fetches draw on its `max_fetches`. Board and page requests honor `Retry-After` up to `retry.max_wait_seconds` and stop at the run's `max_wall_seconds`; a source left unread is `unreadable`, and if none could be read Collect is `partial` (or `failed` on a first run). A board the Scout added that has never been read and fails for good (404 or 410, too large, not JSON the parser accepts) is deactivated, so it does not cost a request every run; config boards never are. When the Curator's budget runs out, the report says how many postings are still waiting for review; the next run starts with them, most relevant first.

**Watchlist.** Without `options.watchlist`, the run starts from `backend/tracker/usecases/internships/watchlist.yaml` (ten NYC boards). Check those boards against the live APIs before relying on them.

**Publishing.** In production the run is scheduled, and its report lands in Postgres for the web app; see [deployment.md](deployment.md#daily-internship-tracker). Locally, `uv run python -m app.publish_report` publishes the latest finished run to `DATABASE_URL`.

**Tools without the model.** Every internship tool runs from the command line against the state file, for example:

```bash
uv run python -m tracker.tools get_posting 1
uv run python -m tracker.tools flag_unclear 7 "no term or location"
uv run python -m tracker.tools save_record 1 '{"title": {"value": "SWE Intern", "quote": "SWE Intern"}}'
```

**Hosts to allow.** A real run needs `api.groq.com`, `api.tavily.com`, `boards-api.greenhouse.io`, `api.lever.co`, `api.ashbyhq.com` and the posting hosts (`boards.greenhouse.io`, `job-boards.greenhouse.io`, `jobs.lever.co`, `jobs.ashbyhq.com`), plus whatever pages the Scout reads.

## Tests

```bash
cd backend
uv run pytest tests_tracker
```

These tests need no database and no network: providers are faked with respx or a local HTTP server, and DNS with a stub. CI runs them in the `tracker` job.

## Network access

A real run needs outbound HTTPS to `api.groq.com` and `api.tavily.com`, plus whatever hosts the agent fetches. Sandboxed environments (for example a cloud dev environment with a restricted network policy) may block these; allow them in the environment's network settings or run the tracker locally.
