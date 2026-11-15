## 1. Wall-time check in Verify (D1, D3, D4, D5)

- [x] 1.1 In `backend/tracker/usecases/internships/verifying.py`, give `Client` the run's `deadline` and `clock` (as `usecases/internships/http.py` does). Before each attempt, stop when `clock() + wait + timeout > deadline`, where `wait` is the backoff or `Retry-After` before a retry (0 before the first attempt) and `timeout` is `time_budget_ms + cold_start_ms`. Do not sleep in that case.
- [x] 1.2 Raise `VerifierFailed("max_wall_seconds", ..., stop_all=True)` so `verify_top_k` stops sending. A request with no attempt sent is not counted in `requests` and not charged; one stopped after some attempts is charged its full share, as today (D5).
- [x] 1.3 In `VerifyStage.run` (`wiring.py`), pass `ctx.budget.deadline` and `ctx.budget.clock` to the client.

## 2. Tests (`backend/tests_tracker/test_internships_verifying.py`)

- [x] 2.1 Scenario "Gateway error then success", parametrized over `502` and `504`: one retry, same `request_id` and body, verdicts stored once, usage charged once.
- [x] 2.2 Scenario "Not enough wall time left", before a first request: a fake clock leaves less than the timeout; no request is sent, claims are `unverified`, the stage is `partial` with `service:verifier`.
- [x] 2.3 Same scenario before a retry: the first attempt gets `503`, the clock leaves less than wait plus timeout; no second attempt, no sleep, later opportunities get no request.

## 3. Docs

- [x] 3.1 `ORCHESTRATION.md` Q2 "How the timeouts were chosen": rewrite the "known gap" paragraph to say the gap is closed. Verify checks the run's remaining wall time (`max_wall_seconds`) before each attempt and stops when the wait plus 75 s would pass it, so the run ends before the 30-minute job limit and the report is still published. Update the line numbers it cites.
- [x] 3.2 `docs/tracker.md` "Verification": name `502`, `503` and `504` as retried, add the note that a retry after `502` or `504` can repeat a paid Groq call, and add the wall-time stop.

## 4. Charge copies lost to 502/504 or a timeout (D6)

- [x] 4.1 In `verifying.py`, `Client.send` takes the run's `budget` from `verify_top_k`. After an attempt that got `502` or `504` or timed out, charge a full share with `_charge`. Before each retry, stop with `VerifierFailed("no_budget_share", ..., stop_all=True)` when `_fits` says another full share doesn't fit. `VerifierFailed.lost` counts the charged attempts, so `verify_top_k` adds the "never answered" share only when `lost` is 0 (D9).
- [x] 4.2 Tests: "Timeout then stored copy" and "Gateway error then success" (502 and 504) charge one share plus the answer's usage; three lost copies are charged three shares and no more; "No share left for a retry" (502 and 504): one attempt, no sleep, no request for the next opportunity, claims `unverified`.
- [x] 4.3 Spec: the requirement's charging sentence, the two scenarios above, and the new scenario "No share left for a retry". Docs: `ORCHESTRATION.md` Q2 and Q3, `docs/tracker.md` "Verification".
