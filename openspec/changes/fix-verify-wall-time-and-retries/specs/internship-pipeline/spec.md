## MODIFIED Requirements

### Requirement: Verify stage calls the verifier
The Verify stage SHALL send one `POST /verify` per top-K opportunity that has claims without a stored verdict for its current record hash. Each request gets a new `request_id`, the run's `run_id`, and the configured per-request `time_budget_ms` and budget. The client timeout SHALL be `time_budget_ms` plus `verifier.cold_start_ms`. Connection errors, timeouts, `502`, `503` and `504` SHALL be retried with exponential backoff and jitter, honoring `Retry-After`, up to `verifier.max_attempts`, resending the identical body with the same `request_id`. A retry after `502` or `504` can repeat the verifier's paid Groq call, because the first copy may have made its model call before the gateway gave up; each copy is held to the per-request budget, and the copies are bounded by `verifier.max_attempts` and the run's wall time. Each attempt that reached the verifier and got no valid answer SHALL be charged a full per-request share (`max_steps`, `max_fetches`, `max_tokens`) in the run's totals, because its copy may have made a paid model call. This covers timeouts, connections dropped after sending, `500`, `502`, `504`, an invalid `200`, and a `503` (such as `rate_limited`) whose error code is not `in_progress`. An attempt that got `400`, `401` or `409`, a connection error before sending (`httpx.ConnectError`), or a `503` with error code `in_progress` SHALL NOT be charged. The answer the request finally gets SHALL be charged its `usage` once per `request_id`. A retry SHALL be sent only if another full share still fits the run's remaining steps, tokens and fetches; otherwise the stage SHALL send no further requests or retries in this run, the claims not yet answered stay `unverified`, the stage is `partial`, and the run names `verifier` as the failed service. `400`, `401`, `409` and `500` SHALL NOT be retried. The stage SHALL validate every response against the response schema, including that each verdict's `claim_id` was sent in that request. An invalid response SHALL count as the verifier failing for that request, and none of its content SHALL be stored.

Before each attempt, including each retry, the stage SHALL check that the run's remaining wall time (until `limits.max_wall_seconds`) covers the wait before that attempt plus the client timeout. If it does not, the stage SHALL send no further requests or retries in this run. The claims not yet answered stay `unverified`, the stage is `partial`, and the run names `verifier` as the failed service, as when the verifier is down.

#### Scenario: Timeout then stored copy
- **WHEN** the first attempt times out and the retry returns the verifier's stored response
- **THEN** the verdicts are stored once, the timed-out attempt is charged a full per-request share, and the stored copy's usage is charged once

#### Scenario: Gateway error then success
- **WHEN** the first attempt gets `502` (or, in a second case, `504`) and the retry returns a valid `200`
- **THEN** the request is retried with the same `request_id` and body, the verdicts are stored once, the attempt that got `502` or `504` is charged a full per-request share, and the answer's usage is charged once

#### Scenario: Rate limited then success
- **WHEN** the first attempt gets `503` with error code `rate_limited` and the retry returns a valid `200`
- **THEN** the attempt that got `503` is charged a full per-request share, and the answer's usage is charged once

#### Scenario: Still in progress
- **WHEN** an attempt gets `503` with error code `in_progress` and the retry returns a valid `200`
- **THEN** the `503` attempt is not charged, and only the answer's usage is charged

#### Scenario: No share left for a retry
- **WHEN** an attempt gets `502`, `504`, a `503` that is not `in_progress`, times out, or loses its connection after sending, and after charging its share another full per-request share no longer fits the run's remaining steps, tokens or fetches
- **THEN** no retry and no later request is sent, the remaining claims are `unverified`, the report is partial and names `verifier`, and the command exits `2`

#### Scenario: Not enough wall time left
- **WHEN** the run's remaining wall time is less than `time_budget_ms + cold_start_ms` before a request, or less than the backoff wait plus that timeout before a retry
- **THEN** that attempt and every later request are not sent, the remaining claims are `unverified`, the report is partial and names `verifier`, and the command exits `2`

#### Scenario: Unknown claim id
- **WHEN** a response contains a verdict for a `claim_id` that wasn't sent
- **THEN** the whole response is discarded, its claims stay `unverified`, and the run names `verifier` as failed

#### Scenario: Unauthorized
- **WHEN** the verifier answers `401`
- **THEN** the stage does not retry, and stops sending further requests in this run

### Requirement: Verifier budget share
`verifier.budget` SHALL set the per-request share, and `verifier.max_requests` the number of requests per run. The run's totals SHALL count the `usage` of each valid answer once per `request_id`. Each attempt that reached the verifier and got no valid answer SHALL be charged a full share, as the requirement "Verify stage calls the verifier" lists, including the last attempt of a request that never got a valid answer. There is no further share on top. An attempt that never reached the verifier, or that the verifier refused before doing paid work, costs nothing. The stage SHALL NOT send a request, or a retry, whose full share would take the run past its total budget. Those claims stay `unverified`.

#### Scenario: Never answered
- **WHEN** a request times out on every attempt
- **THEN** the run's totals are charged one full `max_steps`, `max_fetches` and `max_tokens` share per attempt, and nothing more

#### Scenario: Never connected
- **WHEN** every attempt of a request fails with a connection error before sending
- **THEN** the run's totals are not charged for that request
