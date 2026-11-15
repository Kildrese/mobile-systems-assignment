## Why

The Verify stage checks steps, tokens and fetches before each request, but never wall time. A verifier that hangs can add about 26 minutes to a run, past `max_wall_seconds: 1500` (`config.yaml:47`) and GitHub's `timeout-minutes: 30` (`.github/workflows/tracker.yml:30`). Then the job is killed before Report and publish, and that day's report is lost. Kilian decided to close this gap (D1, from `add-orchestration-doc` D12).

The client also retries `502` and `504` (`verifying.py:189`), but the spec names only `503`. Kilian decided the spec should match the code (D2, from `add-orchestration-doc` D13).

A retry can repeat the verifier's paid Groq call, but the run's totals only counted each request's final answer, or one share when there was none. Kilian decided that every failed attempt that may have spent is charged (D6, widened by D11 and D12).

## What Changes

- Before each verifier request, and before each retry, Verify checks that the run's remaining wall time covers the request's worst case: the wait before it plus the client timeout (`time_budget_ms + cold_start_ms`). If not, it sends nothing more. The remaining claims stay `unverified`, the stage is `partial`, and the run names `verifier` as the failed service, as when the verifier is down.
- The deadline is the run's existing one (`Budget.deadline`), the same that the board fetcher, the model client and search already use.
- The spec names `502`, `503` and `504` as retried, with a note that a retry after `502` or `504` can repeat a paid Groq call.
- Each attempt that reached the verifier and got no valid answer is charged a full per-request share, the last one included, with no extra share on top. `400`, `401`, `409`, a connection error before sending and a `503` `in_progress` cost nothing. A retry is sent only if another full share still fits the run's budget (D6, D10, D11, D12).
- `ORCHESTRATION.md` Q2 and Q3 and `docs/tracker.md` are updated to match.

## Capabilities

### New Capabilities
None.

### Modified Capabilities
- `internship-pipeline`: "Verify stage calls the verifier" gains the wall-time check, the `502`/`504` retries and the per-attempt charging.
- `internship-pipeline`: "Verifier budget share" charges one share per failed attempt that reached the verifier, replacing the single "never answered" share.

## Impact

- **Code:** `backend/tracker/usecases/internships/verifying.py` (the client and `verify_top_k`), and the Verify stage in `wiring.py` passes the run's deadline and clock.
- **Tests:** `backend/tests_tracker/test_internships_verifying.py`.
- **Docs:** `ORCHESTRATION.md`, `docs/tracker.md`.
- **No** new dependency, migration, config key, deploy or paid-call path. The change sends fewer verifier requests and charges the run's totals more for failed attempts, so a run can stop verifying sooner.
