## Why

The Verify stage checks steps, tokens and fetches before each request, but never wall time. A verifier that hangs can add about 26 minutes to a run, past `max_wall_seconds: 1500` (`config.yaml:47`) and GitHub's `timeout-minutes: 30` (`.github/workflows/tracker.yml:30`). Then the job is killed before Report and publish, and that day's report is lost. Kilian decided to close this gap (D1, from `add-orchestration-doc` D12).

The client also retries `502` and `504` (`verifying.py:189`), but the spec names only `503`. Kilian decided the spec should match the code (D2, from `add-orchestration-doc` D13).

## What Changes

- Before each verifier request, and before each retry, Verify checks that the run's remaining wall time covers the request's worst case: the wait before it plus the client timeout (`time_budget_ms + cold_start_ms`). If not, it sends nothing more. The remaining claims stay `unverified`, the stage is `partial`, and the run names `verifier` as the failed service, as when the verifier is down.
- The deadline is the run's existing one (`Budget.deadline`), the same that the board fetcher, the model client and search already use.
- The spec names `502`, `503` and `504` as retried, with a note that a retry after `502` or `504` can repeat a paid Groq call.
- `ORCHESTRATION.md` Q2 and `docs/tracker.md` are updated to match.

## Capabilities

### New Capabilities
None.

### Modified Capabilities
- `internship-pipeline`: "Verify stage calls the verifier" gains the wall-time check and the `502`/`504` retries.

## Impact

- **Code:** `backend/tracker/usecases/internships/verifying.py` (the client and `verify_top_k`), and the Verify stage in `wiring.py` passes the run's deadline and clock.
- **Tests:** `backend/tests_tracker/test_internships_verifying.py`.
- **Docs:** `ORCHESTRATION.md`, `docs/tracker.md`.
- **No** new dependency, migration, config key, deploy or paid-call path. The change only sends fewer verifier requests.
