## MODIFIED Requirements

### Requirement: Verify stage calls the verifier
The Verify stage SHALL send one `POST /verify` per top-K opportunity that has claims without a stored verdict for its current record hash. Each request gets a new `request_id`, the run's `run_id`, and the configured per-request `time_budget_ms` and budget. The client timeout SHALL be `time_budget_ms` plus `verifier.cold_start_ms`. Connection errors, timeouts, `502`, `503` and `504` SHALL be retried with exponential backoff and jitter, honoring `Retry-After`, up to `verifier.max_attempts`, resending the identical body with the same `request_id`. A retry after `502` or `504` can repeat the verifier's paid Groq call, because the first copy may have made its model call before the gateway gave up; each copy is held to the per-request budget, and the copies are bounded by `verifier.max_attempts` and the run's wall time. Each attempt that got `502` or `504` or timed out SHALL be charged a full per-request share (`max_steps`, `max_fetches`, `max_tokens`) in the run's totals, and the answer the request finally gets SHALL be charged its `usage` once per `request_id`. A retry SHALL be sent only if another full share still fits the run's remaining steps, tokens and fetches; otherwise the stage SHALL send no further requests or retries in this run, the claims not yet answered stay `unverified`, the stage is `partial`, and the run names `verifier` as the failed service. `400`, `401`, `409` and `500` SHALL NOT be retried. The stage SHALL validate every response against the response schema, including that each verdict's `claim_id` was sent in that request. An invalid response SHALL count as the verifier failing for that request, and none of its content SHALL be stored.

Before each attempt, including each retry, the stage SHALL check that the run's remaining wall time (until `limits.max_wall_seconds`) covers the wait before that attempt plus the client timeout. If it does not, the stage SHALL send no further requests or retries in this run. The claims not yet answered stay `unverified`, the stage is `partial`, and the run names `verifier` as the failed service, as when the verifier is down.

#### Scenario: Timeout then stored copy
- **WHEN** the first attempt times out and the retry returns the verifier's stored response
- **THEN** the verdicts are stored once, the timed-out attempt is charged a full per-request share, and the stored copy's usage is charged once

#### Scenario: Gateway error then success
- **WHEN** the first attempt gets `502` (or, in a second case, `504`) and the retry returns a valid `200`
- **THEN** the request is retried with the same `request_id` and body, the verdicts are stored once, the attempt that got `502` or `504` is charged a full per-request share, and the answer's usage is charged once

#### Scenario: No share left for a retry
- **WHEN** an attempt gets `502` or `504` or times out, and after charging its share another full per-request share no longer fits the run's remaining steps, tokens or fetches
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
