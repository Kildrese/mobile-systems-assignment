## ADDED Requirements

### Requirement: Cross-service events
Every attempt of a call to another service SHALL produce a trace event with kind `service`, `service` (`tracker`), `run_id`, `request_id`, `step`, `direction` `out`, `endpoint_or_tool` (such as `verifier:/verify`), `status` (HTTP status, or `timeout` / `connection_error`), `latency_ms` measured by the tracker, `attempt` (starting at 1) and `tokens` (from the response's `usage`, or null). A retry SHALL have the same `request_id` and the next `attempt`.

#### Scenario: Retry after cold start
- **WHEN** the first `/verify` attempt times out and the second returns `200`
- **THEN** the trace has two `service` events with the same `request_id`, attempts 1 and 2, statuses `timeout` and `200`

#### Scenario: Token never logged
- **WHEN** a run's trace is searched for the value of `VERIFIER_TOKEN`
- **THEN** there is no match
