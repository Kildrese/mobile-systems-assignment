## ADDED Requirements

### Requirement: Orchestrate command
`uv run python -m tracker.orchestrate [--config PATH]` (in `backend/`) SHALL run one orchestrated run in plain code: no model call of its own, no agent framework. It SHALL be started only by hand. No API route, cron or workflow SHALL start it. It SHALL talk to the workers only over HTTP (`RESEARCHER_URL`, `VERIFIER_URL`) and import from them nothing but `agentkit.contract`. Exit codes: `0` complete, `2` partial, `1` when it refuses to start (invalid policy, missing setting, non-local database); on `1` it SHALL send no request and write nothing.

#### Scenario: Missing researcher URL
- **WHEN** `RESEARCHER_URL` is not set in the environment or `backend/.env`
- **THEN** the command prints `RESEARCHER_URL is not set`, exits `1`, and sends no request

### Requirement: Settings and secrets
The command SHALL read the policy with `load_policy`. It SHALL require `options.researcher` and `options.verifier`, both validated by `VerifierSettings` (the researcher's `max_requests` is ignored: one `/research` per run). It SHALL read `RESEARCHER_URL`, `RESEARCHER_TOKEN`, `VERIFIER_URL` and `VERIFIER_TOKEN` through `TrackerSecrets.load(policy, model=False, search=False)` and exit `1` naming each one that is missing. It SHALL read `DATABASE_URL` through the app's settings and exit `1` with `refusing to write to a non-local database` unless its host is `localhost`, `127.0.0.1` or `::1`. All checks SHALL happen before any request.

#### Scenario: Neon URL
- **WHEN** `DATABASE_URL` points at a `*.neon.tech` host
- **THEN** the command exits `1` before any request, and nothing is written

### Requirement: One budget split between the workers
The run's total SHALL be `config.yaml` `limits.max_steps`, `limits.max_fetches` and `limits.max_tokens`, held in one `tracker.budget.Budget`. The researcher's share SHALL be `options.researcher`'s `max_steps`, `max_fetches`, `max_tokens` and `time_budget_ms`; each verifier request's share SHALL be `options.verifier`'s. For each of the three limits, the researcher's share plus `options.verifier.max_requests` times the verifier's share SHALL NOT exceed the total, or the command exits `1` with `Invalid policy: limits.<name>: researcher and verifier add up to <n>, more than <cap>`. Each `request_id` SHALL be charged once with the `usage` its valid answer reported; each attempt that reached a worker and got no valid answer SHALL be charged that worker's full share (the existing client rule). A `/verify` request SHALL NOT be sent when its full share no longer fits the remaining total.

#### Scenario: Over-allocated
- **WHEN** `limits.max_tokens` is 60,000, the researcher's share is 20,000 and the verifier's is 5 × 12,000
- **THEN** the command exits `1` naming `limits.max_tokens` and 80,000

#### Scenario: Stored copy counted once
- **WHEN** the first `/research` attempt times out and the retry returns the stored response
- **THEN** the run's totals hold one full researcher share for the timed-out attempt plus the response's `usage`, once

### Requirement: Calls to the workers
The command SHALL send one `POST /research` with a new `request_id`, the run's `run_id` (a UUID that is also the run's id everywhere), the researcher's `time_budget_ms` and budget, and `payload` `{topic: policy.topic, k: policy.k}`. Then, for each development in the order received, it SHALL send one `POST /verify` with that development's claims (`claim_id`, `text`, `source_url` exactly as received), a new `request_id`, the same `run_id` and the verifier's `time_budget_ms` and budget, up to `options.verifier.max_requests` requests. Both workers SHALL be called through the existing client in `verifying.py`: timeout `time_budget_ms + cold_start_ms`, up to `max_attempts` attempts with the same bytes and `request_id`, backoff `min(2^n, 30)` s with ±20% jitter, `Retry-After` honored, connection errors, timeouts, `502`, `503` and `504` retried, `400`, `401`, `409` and `500` not retried, and no attempt started that would pass `limits.max_wall_seconds`. A `401` from the verifier SHALL stop all further `/verify` requests in the run.

#### Scenario: Retry keeps the body
- **WHEN** the first `/verify` attempt gets `503` with `Retry-After: 5`
- **THEN** the client waits at least 5 s and resends byte-identical content with the same `request_id`

#### Scenario: Verifier request cap
- **WHEN** the researcher returns 5 developments and `max_requests` is 3
- **THEN** 3 `/verify` requests are sent, the other 2 developments' claims are `unverified`, and the run is partial with stop reason `verifier.max_requests`

### Requirement: Responses are validated
Every `200` SHALL be validated against the response model (`ResearchResponse`, `VerifyResponse`) and `check_against` the request: same `request_id` and `run_id`; for `/research`, at most `k` developments, unique development ids, unique `claim_id`s across the response; for `/verify`, only `claim_id`s that were sent in that request, each at most once. An invalid response SHALL count as that worker failing for that request, SHALL NOT crash the run, and none of its content SHALL reach the report or the database. Worker text SHALL be treated as data: nothing in a response changes the topic, `k`, the budgets, the number of requests or which worker is called.

#### Scenario: Unknown claim id
- **WHEN** a `/verify` response has a verdict for a `claim_id` not in that request
- **THEN** the whole response is discarded, that development's claims are `unverified`, and the run names `verifier` as failed

#### Scenario: Too many developments
- **WHEN** `/research` returns 6 developments for `k` 5
- **THEN** the response is discarded and the run is handled as researcher down

### Requirement: Failed workers
The researcher has failed when its request ends without a valid `200`, or with a valid `200` that is `partial`. The verifier has failed when any `/verify` request ends without a valid `200`, or with a valid `200` that is `partial`. The run SHALL be `complete` only when neither failed and no development was left unverified for `max_requests` or budget; otherwise `partial`. Its `failed_services` SHALL list `researcher` and/or `verifier`, in that order. Its stop reason SHALL be `service:researcher`, else `service:verifier`, else `verifier.max_requests`, else null.

- Researcher down (no valid `200`, or a `partial` one with no developments): the report SHALL say there are no new results and show the top K of the newest earlier run in `tracker_runs` that has `top_k` rows in `internship_offers`, each marked stale, with their stored claims and verdicts. If there is none, it says `No earlier run to show.` No `/verify` request is sent, and the run writes no `internship_offers` rows.
- Researcher `partial` with developments: they are verified and reported as usual, and `researcher` is named.
- Verifier down or invalid: the affected claims SHALL be `unverified`; developments are still reported and saved.

#### Scenario: Researcher down
- **WHEN** `/research` gets connection refused on every attempt and the last run's top K had 5 offers
- **THEN** the report says there are no new results and lists those 5 offers marked stale, the run is partial with `failed_services` `["researcher"]`, no `/verify` is sent, and the command exits `2`

#### Scenario: Verifier down
- **WHEN** every `/verify` attempt times out
- **THEN** every claim is `unverified`, the run is partial with `failed_services` `["verifier"]`, the developments are saved, and the command exits `2`

#### Scenario: All good
- **WHEN** both workers answer `complete` and every development was verified
- **THEN** the run is complete with `failed_services` `[]`, and the command exits `0`

### Requirement: Report, trace and run history
The command SHALL write the report to `<reports dir>/orchestrate-<run_id>.md` and the trace to `<traces dir>/orchestrate-<run_id>.jsonl` (the policy's directories, ignored by git). The report SHALL state the topic, run id, start time, status, each failed worker with its reason, the budget used, and then either each development in rank order (title, summary, and per claim its label `supported`, `unsupported`, `unreachable` or `unverified`, its text, its source URL, and evidence for supported claims) or the stale section above. Text from workers SHALL be collapsed to one line per field. The trace SHALL hold one `service` event per attempt to a worker with `service` `orchestrator`, `run_id`, `request_id`, `step`, `direction` `out`, `endpoint_or_tool` (`researcher:/research` or `verifier:/verify`), `status`, `latency_ms` measured by the command, `attempt` and `tokens`, and SHALL NOT contain either token. Run history SHALL be written with `app.publish_report.publish` to the local database: one `tracker_runs` row (id = `run_id`, topic, status, stop reason, start and end time, the report Markdown, `failed_services`) and, unless the researcher was down, one `internship_offers` row per development: `opportunity_id` = rank, `section` `top_k`, `rank`, `top_k` true, `title` the development's title, `company` empty string, `url` its first claim's `source_url`, `summary`, `role_type`, `term`, `remote` and `status` `unknown`, `locations` `[]`, `verified` false, `first_seen_at` the run's start, other nullable columns null, and `claims` `[{field, text, verdict, evidence}]` with `field` the part of `claim_id` after the first `:` (the whole id if it has none).

#### Scenario: Following a request across logs
- **WHEN** the run's trace has a `/verify` event with a `request_id`
- **THEN** the verifier's log has an `in` line with that `request_id` and the same `run_id`

#### Scenario: Run history written
- **WHEN** a run completes with 5 developments
- **THEN** `tracker_runs` has its row with status `complete` and `internship_offers` has 5 rows for it, ranks 1 to 5, with their claims

#### Scenario: Stale run leaves the last top K findable
- **WHEN** a run with the researcher down follows a complete run
- **THEN** the next stale lookup still finds the complete run's top K
