## ADDED Requirements

### Requirement: Researcher service
The researcher SHALL be a separate HTTP service in `services/researcher`, run locally with `uv run uvicorn main:app --port 8101`, with `GET /healthz` and `POST /research`. It SHALL have no database, make no model calls and no fetches, and import nothing from `backend/` or `services/verifier`; shared code comes only from `packages/agentkit`. `GET /healthz` SHALL need no auth and return `{"status": "ok"}`. Request handling (token, body, idempotency, `in` log line) SHALL go through `agentkit.service.serve` with `service="researcher"` and `path="/research"`.

#### Scenario: Health check
- **WHEN** `GET /healthz` is called without a token
- **THEN** it returns `200` with `{"status": "ok"}`

### Requirement: Researcher token
`POST /research` SHALL require `Authorization: Bearer <RESEARCHER_TOKEN>`, compared in constant time, checked before the body is parsed, and SHALL return `401` when the header is missing or wrong. The service SHALL refuse to start without `RESEARCHER_TOKEN`.

#### Scenario: No token, bad body
- **WHEN** `POST /research` is called without `Authorization` and with an invalid body
- **THEN** it returns `401`, not `400`

#### Scenario: Verifier's token
- **WHEN** `POST /research` is called with the verifier's token
- **THEN** it returns `401`

### Requirement: Research request
A request SHALL be the envelope `{request_id, run_id, time_budget_ms, budget: {max_steps, max_fetches, max_tokens}, payload: {topic, k}}`, validated by `agentkit.contract.ResearchRequest`: UUIDs, positive integers, `topic` 1 to 200 characters, `k` an integer from 1 to 20, unknown fields rejected. A request that fails the schema SHALL return `400` naming the failing fields.

#### Scenario: k out of range
- **WHEN** an authenticated request has `payload.k` 0
- **THEN** it returns `400`, naming `payload.k`

#### Scenario: Unknown field
- **WHEN** an authenticated request's payload has an extra field `reasoning`
- **THEN** it returns `400`

### Requirement: Research response
A `200` response SHALL be `{request_id, run_id, status, result: {developments: [{id, title, summary, claims: [{claim_id, text, source_url}]}]}, usage: {steps, fetches, tokens}, error}`, valid against `agentkit.contract.ResearchResponse`. `status` is `complete` or `partial`; `error` is null when complete and `{code, message, retryable}` when partial. Developments SHALL come in rank order, at most `k` of them, with unique `id`s; each SHALL have 1 to 20 claims; `claim_id`s SHALL be unique across the whole response. `usage` SHALL be `{steps: 0, fetches: 0, tokens: 0}`.

#### Scenario: Top 2
- **WHEN** a request asks for `k` 2 and the data file has 5 developments
- **THEN** the response is `complete` with the file's first 2 developments, in file order

#### Scenario: k larger than the file
- **WHEN** a request asks for `k` 20 and the file has 5 developments
- **THEN** the response is `complete` with all 5

### Requirement: Developments file
The developments SHALL come from `services/researcher/developments.json`, a JSON list of developments in rank order, built by hand from the top K of the tracker report `20261115T093900Z-8e97` (the newest D7 artifact). Each development SHALL have `id` `d<rank>`, the posting's title and company as `title` (`"<title>, <company>"`), the report's summary as `summary` (empty string when the report has none), and one claim per claim listed for it in the report's "Claims checked (top K)" section, with the report's claim sentence as `text`, `claim_id` `d<rank>:<field>` (field one of `title`, `role_type`, `term`, `locations`, `remote`, `compensation`, `deadline`, `work_authorization`, read from the sentence's template) and the posting's URL from the report as `source_url`. Every `source_url` SHALL be `https` and answer `200` when the file is built. The file SHALL hold public posting data only: no fit reasons, no profile text, nothing from `private/`. The service SHALL validate the file at startup against the development model and refuse to start if it is missing, invalid or empty. The `topic` SHALL NOT filter the file.

#### Scenario: Invalid file
- **WHEN** the service starts and a development in the file has no claims
- **THEN** it raises at import and does not serve

### Requirement: Researcher time budget
The researcher's clock SHALL start when `work` is called. It SHALL spend `DELAY_MS` (a module constant, 100 ms; tests patch it) per development to stand in for research work. Before taking each development it SHALL check whether elapsed time plus the delay would pass `time_budget_ms`; if so it SHALL stop and return `200`, status `partial`, the developments it took, and `error` `{code: "time_budget_exhausted", message: "stopped after <i> of <n> developments", retryable: false}`, where `n` is `min(k, file size)`. `max_steps`, `max_fetches` and `max_tokens` are accepted and never reached.

#### Scenario: Tiny time budget
- **WHEN** a request has `time_budget_ms` 1 and the delay is 100 ms
- **THEN** the response is `200`, `partial`, `error.code` `time_budget_exhausted`, with 0 developments

### Requirement: Researcher idempotency
The researcher SHALL follow the same rules as the verifier through `agentkit.service.Store`: a repeated `request_id` with the same body hash returns the stored `200` response without running `work` again; with a different body hash, `409`; while the first copy is running, `503` with `Retry-After: 5`, and `work` does not start twice. Only `200` responses are stored, in process memory.

#### Scenario: Same request twice
- **WHEN** the same `request_id` and body are sent twice
- **THEN** both answers are identical and `work` ran once

#### Scenario: Same id, reordered keys
- **WHEN** the second copy has the same JSON with keys in another order
- **THEN** it gets the stored answer

#### Scenario: Same id, different body
- **WHEN** the second copy has a different `payload.k`
- **THEN** it returns `409`

#### Scenario: Duplicate while running
- **WHEN** a copy arrives while the first is still in `work`
- **THEN** it returns `503` with `Retry-After: 5`, and `work` was entered once

### Requirement: Researcher log
The researcher SHALL write one JSON line per received request through `agentkit.wire_log.log_line` (via `serve`), with `service` `researcher`, the request's `run_id` and `request_id`, `direction` `in`, `endpoint_or_tool` `/research`, `status` and `latency_ms`. It makes no outgoing calls, so it writes no `out` lines. Lines SHALL NOT contain `RESEARCHER_TOKEN` or the `Authorization` header.

#### Scenario: Token never logged
- **WHEN** the log of a test session with a `401`, a `400` and a `200` is searched for the token value
- **THEN** there is no match, and the `200` line carries the request's `run_id` and `request_id`
