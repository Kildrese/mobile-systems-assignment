# Tracker

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
```

The command prints the outcome and the report and trace paths.

| Exit status | Meaning |
| --- | --- |
| `0` | Complete: the model called `finish` within all budgets |
| `2` | Partial: a budget ran out; the report uses the evidence gathered so far |
| `3` | Terminal provider failure (bad key, quota, payment, unreachable); a partial report is still written |
| `1` | Invalid policy, missing key, or another run holds the state file. Nothing was called |

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

A terminal failure prints one line naming the provider, the class and the likely fix (no stack trace), writes a partial report and the trace, and exits `3`. After a model-provider failure no further model call is made. A Groq `tool_use_failed` 400 (the model emitted a malformed tool call) is not a provider failure: the model is told and the run continues.

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
| `.tracker/state.sqlite` | Runs (status, stop reason, usage), fetched articles by canonical URL with text and content hash, searches, reported items | No |
| `reports/<run_id>.md` | The report: topic, run id, time, status, budget used, ranked items with sources | No |
| `traces/<run_id>.jsonl` | One JSON event per model call attempt and tool call, then a summary event | No |

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
    model: {name: llama-3.1-8b-instant}   # provider, temperature, ... from `model`
    tools: [fetch_article]
    fetch_hosts: ["*.example.com"]
    limits: {max_steps: 4, max_tokens: 8000, max_fetches: 4}
    instructions: Read the pages the scout found and extract the facts.
```

**Budget split.** For `max_steps`, `max_tokens`, `max_searches` and `max_fetches`, the enabled agents' limits must add up to no more than the run's `limits`, or validation fails naming the limit and the total. `max_searches` is required when an agent has `search_web`, and `max_fetches` when it has `fetch_article`. Before every model and tool call, code checks the agent's limits first, then the run's, and charges both. Wall time, cost and `reserve_tokens` are run-level only. A stop reason names the level: `scout.max_steps` for the agent, `max_tokens` for the run.

**Privileges.** An agent is offered only its profile's tools; calling another one returns `unknown_tool` and costs a step. `fetch_hosts` narrows the hosts that agent may fetch (and follow redirects to). Every pattern must be covered by `fetch.allowed_hosts`; it is checked first, then all the core guardrails above still apply. Keys are needed for every provider an enabled agent uses.

**Stages.** The use case defines an ordered list of stages in code: an agent stage runs one agent loop for a profile, a code stage runs plain code. Model output never changes the order. Each stage gets the policy, its own profile, the state store, its trace and its budget, never another agent's conversation: stages hand data on only through records in the state store.

**Outcomes.** Each stage ends `complete`, `partial` (stopped by a budget or a provider failure), `skipped` (its agent has `enabled: false`, or a provider it needs failed for good earlier in the run) or `failed` (it raised). A stage the use case marks required cannot be disabled. The run is `failed` (exit `3`) when a required stage failed; `partial` (exit `2`) when any stage was partial, failed, or skipped after a provider failure; otherwise `complete` (exit `0`). After a terminal provider failure, later stages that need that provider are skipped and the rest, including code stages, still run. A report is written in every case.

**Trace fields.** Every event written during a stage carries `stage`, and agent stages also `agent`. The summary event adds `stages`: per stage its `name`, `agent`, `outcome`, `reason` and `usage`.

## Tests

```bash
cd backend
uv run pytest tests_tracker
```

These tests need no database and no network: providers are faked with respx or a local HTTP server, and DNS with a stub. CI runs them in the `tracker` job.

## Network access

A real run needs outbound HTTPS to `api.groq.com` and `api.tavily.com`, plus whatever hosts the agent fetches. Sandboxed environments (for example a cloud dev environment with a restricted network policy) may block these; allow them in the environment's network settings or run the tracker locally.
