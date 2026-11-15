## 1. Wall-time check in Verify (D1, D3, D4, D5)

- [ ] 1.1 In `backend/tracker/usecases/internships/verifying.py`, give `Client` the run's `deadline` and `clock` (as `usecases/internships/http.py` does). Before each attempt, stop when `clock() + wait + timeout > deadline`, where `wait` is the backoff or `Retry-After` before a retry (0 before the first attempt) and `timeout` is `time_budget_ms + cold_start_ms`. Do not sleep in that case.
- [ ] 1.2 Raise `VerifierFailed("max_wall_seconds", ..., stop_all=True)` so `verify_top_k` stops sending. A request with no attempt sent is not counted in `requests` and not charged; one stopped after some attempts is charged its full share, as today (D5).
- [ ] 1.3 In `VerifyStage.run` (`wiring.py`), pass `ctx.budget.deadline` and `ctx.budget.clock` to the client.

## 2. Tests (`backend/tests_tracker/test_internships_verifying.py`)

- [ ] 2.1 Scenario "Gateway error then success", parametrized over `502` and `504`: one retry, same `request_id` and body, verdicts stored once, usage charged once.
- [ ] 2.2 Scenario "Not enough wall time left", before a first request: a fake clock leaves less than the timeout; no request is sent, claims are `unverified`, the stage is `partial` with `service:verifier`.
- [ ] 2.3 Same scenario before a retry: the first attempt gets `503`, the clock leaves less than wait plus timeout; no second attempt, no sleep, later opportunities get no request.

## 3. Docs

- [ ] 3.1 `ORCHESTRATION.md` Q2 "How the timeouts were chosen": rewrite the "known gap" paragraph to say the gap is closed. Verify checks the run's remaining wall time (`max_wall_seconds`) before each attempt and stops when the wait plus 75 s would pass it, so the run ends before the 30-minute job limit and the report is still published. Update the line numbers it cites.
- [ ] 3.2 `docs/tracker.md` "Verification": name `502`, `503` and `504` as retried, add the note that a retry after `502` or `504` can repeat a paid Groq call, and add the wall-time stop.
