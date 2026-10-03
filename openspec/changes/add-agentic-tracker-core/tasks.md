# Tasks

## 1. Scaffolding

- [x] 1.1 Create `backend/tracker/` (`__init__.py`, `__main__.py`, `tools.py`, `config.py`, `llm.py`, `search.py`, `guard.py`, `fetch.py`, `state.py`, `trace.py`, `loop.py`, `report.py`, `errors.py`) and `backend/tests_tracker/` with a conftest that never touches Postgres. Verify `uv run python -c "import tracker"` succeeds from `backend/`
- [x] 1.2 Add `httpx`, `pyyaml` and `beautifulsoup4` as direct backend dependencies and `respx` as a dev dependency with `uv add`, add `tests_tracker` to `testpaths`, and verify `uv sync --locked` and `uv run pytest tests_tracker` (empty suite) succeed
- [x] 1.3 Add `.tracker/` to `.gitignore` and create `reports/.gitkeep` and `traces/.gitkeep`. Verify `git status` after creating `.tracker/state.sqlite` shows no untracked state file

## 2. Policy and secrets (tracker-config)

- [x] 2.1 Implement the frozen pydantic `Policy` (`extra="forbid"`) and its loader, including root discovery, `--config`, K range, required limits, known and required tools, and the http(s)-only scheme rule. Verify with unit tests for each invalid-field scenario in the spec
- [x] 2.2 Implement `TrackerSecrets`, which reads the provider key variables and `TAVILY_API_KEY` from the environment and `backend/.env` without requiring `DATABASE_URL`, with a missing-key message pointing to `.env.example`. Verify with unit tests
- [x] 2.3 Write the root `config.yaml` (design D10) and add `GROQ_API_KEY=` and `TAVILY_API_KEY=` to `backend/.env.example`. Verify a test loads the committed `config.yaml` successfully

## 3. Trace log (trace-log)

- [x] 3.1 Implement the JSONL trace writer (flush per line, event schema, truncation with `*_len`, secret redaction, summary event). Verify with unit tests: fields present, a long argument is truncated, and a planted key value never appears in the file

## 4. Failure handling and clients (api-failure-handling)

- [x] 4.1 Implement `classify()` and the retry helper (exponential backoff with jitter, `retry-after`, attempt and wait caps, an injectable sleep). Verify with table tests covering timeout, connection error, 401, 402, 403, 408, Tavily 432, Groq per-minute 429, Groq daily 429, a long `retry-after`, 5xx, other 4xx, and attempt exhaustion becoming `unreachable`
- [x] 4.2 Implement `ChatClient` for OpenAI-compatible chat completions with tool calls, usage parsing and per-attempt trace events. Verify with respx tests: success, retry-then-success (trace shows `retry` then `ok`), daily 429 raises terminal without retry, and 401 gives a clean terminal message
- [x] 4.3 Implement the Tavily search client (result capping, credit accounting, the same classification). Verify with respx tests for success, 432 terminal and 429 transient

## 5. Fetch guardrails and fetch_article (fetch-guardrails)

- [x] 5.1 Implement `guard.check()`: parsing, scheme, credentials, host patterns, resolution, and non-public address rejection, including IPv4-mapped IPv6 and decimal, octal and hex literals. Verify with unit tests for every spec scenario (`file://`, `127.0.0.1`, `[::1]`, `169.254.169.254`, `2130706433`, a name resolving to `10.0.0.5` via a stubbed resolver, a host outside the allowlist)
- [x] 5.2 Implement the pinned-IP request (Host header plus `sni_hostname`), manual redirects with a re-check on each hop, timeouts plus an overall deadline, a streamed size cap, `Content-Length` pre-rejection and the content-type allowlist. Verify with respx tests: redirect to localhost is blocked, too many redirects, an oversized body is cut off with `too_large`, unsupported type, and the connection goes to the vetted IP even when a second lookup would differ
- [x] 5.3 Implement HTML-to-text extraction and title capture. Verify with a fixture page that script, style and nav are removed and the title is extracted

## 6. State (tracker-state)

- [x] 6.1 Implement the SQLite store (schema with `user_version`, WAL, the `runs`, `articles`, `items` and `searches` tables, URL canonicalization, a lock file that refuses concurrent runs). Verify with unit tests: first-run creation, a tracking-parameter URL maps to the same article, a partial run is recorded with its stop reason, items are stored in rank order, and a second open while locked fails

## 7. Tools and CLI (tracker-tools)

- [x] 7.1 Implement the `search_web`, `fetch_article` (cache hit served from state without counting a fetch) and `finish` (validation, truncation to K, Markdown render) tool functions with pydantic argument schemas and error-result reasons. Verify with unit tests per spec scenario
- [x] 7.2 Implement `python -m tracker.tools <tool> <args>`, which prints JSON and exits non-zero on error. Verify with subprocess tests: `fetch_article http://127.0.0.1:8000/` exits non-zero with `blocked_address` and makes no connection, and `finish sample.json` writes a report
- [x] 7.3 Document the tool commands in `docs/tracker.md` and verify each documented offline command (the blocked-URL fetch, finish) runs as written

## 8. Agent loop and reports (agent-loop)

- [x] 8.1 Implement the untrusted-data wrapper (delimiter escaping) and the injection-signal detector. Verify with unit tests that a page containing `</untrusted_data>` yields exactly one closing delimiter, and that a planted "ignore previous instructions" sets `injection_suspected`
- [x] 8.2 Implement the budget tracker (steps, tokens with reserve, cost, wall time, per-tool counts). Verify with unit tests for each exhaustion path
- [x] 8.3 Implement the loop (design D5): tool dispatch, an unknown tool returning an error result that counts as a step, a no-tool-call nudge, `finish` ending the run, `finish` items whose URLs were not seen being dropped with a trace record, and the partial-report path with a reserved no-tools synthesis call and a code-only fallback. Verify with a scripted fake model: complete run, step-budget partial, token-budget partial, terminal failure after evidence leading to a fallback partial, and unknown-tool handling
- [x] 8.4 Implement `python -m tracker run [--config] [--out]` with exit codes 0, 2 and 3, report and trace paths printed, and run status recorded in state. Verify with subprocess tests against fake providers: a bogus key exits 3 with a one-line message and no stack trace, a network cut (connection refused) exits 3 after the capped retries and writes a partial report, and a scripted complete run exits 0
- [x] 8.5 Add an injection fixture page and a test where the fake model "obeys" it by calling a disallowed tool and requesting a blocked URL. Verify the tools, budgets and policy are unchanged and the trace shows `injection_suspected` and the rejected actions

## 9. CI and docs

- [x] 9.1 Add the `tracker` CI job (uv sync, ruff check, ruff format check, `pytest tests_tracker`; no services, no secrets). Verify the workflow YAML parses and the same commands pass locally
- [ ] 9.2 Add a tracker section to `README.md` (keys, `uv run python -m tracker run`, tool CLI) and finish `docs/tracker.md` (policy fields, budgets, failure classes, guardrails, state and trace locations, network allowlist note). Verify the README commands work from a clean clone with fake keys up to the expected terminal `auth` failure

## 10. Integration check

- [ ] 10.1 With real keys on a machine that can reach Groq and Tavily, run `uv run python -m tracker run` once. Verify a report is written to `reports/`, a trace to `traces/`, and a run row with status `complete` or `partial` exists in state. This is a smoke run, not a graded run
