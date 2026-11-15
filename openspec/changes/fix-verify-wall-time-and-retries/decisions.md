# Decisions: fix-verify-wall-time-and-retries

## D1 Verify stage ignores max_wall_seconds
- class: mine
- source: grilling (copied from add-orchestration-doc D12, raised by the reviewer)
- status: decided (user)
- question: Verifier hangs can push a run past GitHub's 30-minute job limit (`.github/workflows/tracker.yml:30`), so nothing is published. `config.yaml:47` sets `max_wall_seconds: 1500`, but `_fits` (`verifying.py:299-306`) never checks wall time. Make Verify stop at the run's wall-time budget?
- options: A Verify checks remaining wall time before each request and marks the rest unverified / B lower `max_attempts` or `cold_start_ms` / C leave it and document
- built: A
- decision: A. Kilian, 2026-11-15: Verify checks the run's remaining wall time before each request; claims it can't send are marked unverified.
- landed: specs/internship-pipeline/spec.md#Requirement: Verify stage calls the verifier (second paragraph); #Scenario: Not enough wall time left; tasks.md 1.1-1.3, 2.2, 2.3, 3.1; backend/tracker/usecases/internships/verifying.py:160 (check), :293 (not sent: not counted); backend/tests_tracker/test_internships_verifying.py test_no_request_when_wall_time_is_short, test_no_retry_when_the_wait_would_pass_the_deadline, test_verify_stops_at_the_run_wall_time; ORCHESTRATION.md Q2; docs/tracker.md Verification

## D2 Retried statuses
- class: mine
- source: grilling (copied from add-orchestration-doc D13, raised by the reviewer)
- status: decided (user)
- question: The client retries 502, 503 and 504 (`verifying.py:189`); the spec names only 503. Add 502/504 to the spec plus a tracker test, or narrow the code to 503?
- options: A spec + test / B code to 503 only
- built: A
- note: a retry after a 504 can repeat a paid Groq call, because the first copy may have finished its model call before the gateway gave up.
- decision: A. Kilian, 2026-11-15: add 502 and 504 to the spec's retried statuses, plus a tracker test.
- landed: specs/internship-pipeline/spec.md#Requirement: Verify stage calls the verifier (first paragraph, with the paid-retry note); #Scenario: Gateway error then success; tasks.md 2.1, 3.2; backend/tracker/usecases/internships/verifying.py:212; backend/tests_tracker/test_internships_verifying.py test_gateway_error_then_success_is_charged_once; docs/tracker.md Verification; ORCHESTRATION.md Q2

## D3 Which deadline Verify reads
- class: cheap
- source: spec-writer
- status: resolved (spec-writer)
- question: Where does Verify get the run's wall-time budget?
- options: A `Budget.deadline` and `Budget.clock`, passed to the client like `http.py`, `llm.py` and `search.py` do / B a new setting
- built: A
- decision: A. Reuses the existing deadline; no new config.
- landed: proposal.md#What Changes; tasks.md 1.1, 1.3; backend/tracker/usecases/internships/wiring.py:820-821

## D4 The check before a retry includes the wait
- class: cheap
- source: spec-writer
- status: resolved (spec-writer)
- question: D1 says check before each retry. Does the check count the backoff or `Retry-After` wait before that retry?
- options: A yes: stop when wait plus timeout would pass the deadline, without sleeping / B check only the timeout, after sleeping
- built: A
- decision: A. Sleeping first and then giving up would waste the wait; `http.py` also checks the wait against the deadline.
- landed: specs/internship-pipeline/spec.md#Scenario: Not enough wall time left; tasks.md 1.1; backend/tracker/usecases/internships/verifying.py:158-169

## D5 How a wall-time stop is reported and charged
- class: cheap
- source: spec-writer
- status: resolved (spec-writer)
- question: What does the run record when Verify stops on wall time?
- options: A failure reason `max_wall_seconds`, stop all requests, stage `partial` naming `verifier` (as D1 says, like a verifier that's down); a request with no attempt sent is not counted or charged; one stopped after some attempts is charged its full share under the existing "never got a valid answer" rule / B something else
- built: A
- decision: A. Follows D1 and the existing "Verifier budget share" requirement; `max_wall_seconds` is the reason name `http.py` and `report.py` already use.
- landed: tasks.md 1.2; backend/tracker/usecases/internships/verifying.py:115-126 (`VerifierFailed.attempts`), :292-297

## D6 Charge the run for copies lost to 502/504
- class: mine
- source: spec-writer
- status: open
- question: The brief says a repeated Groq call after 502/504 is bounded by "the run's budget". The run's totals count each `request_id` once, with the usage of the answer it got, so a copy lost to a 502/504 is not counted in the run's token totals. Each copy is held to the per-request share by the verifier, and the copies to `max_attempts` and wall time. Should the run's totals also charge the lost copies?
- options: A leave as is (totals count the answer's usage) / B charge a full share for each attempt that got 502/504 / C charge once per request but a full share when any attempt got 502/504
- built: A (status quo; the scenario "Gateway error then success" and test_gateway_error_then_success_is_charged_once assert it, so answering B or C changes both)
- decision:
- landed:

## D7 How the client tells Verify a request was never sent
- class: cheap
- source: implementer, task 1.2
- status: resolved (implementer)
- question: D5 says a request with no attempt sent is not counted or charged. How does `verify_top_k` know?
- options: A `VerifierFailed` carries `attempts` (copies sent; 0 = never sent) / B a separate exception class
- built: A
- decision: A. One field on the existing exception; every raise site sets it.
- landed: backend/tracker/usecases/internships/verifying.py:115-126, :292-297

## D8 One attempt can run past the client timeout
- class: cheap
- source: reviewer
- status: resolved (reviewer)
- question: httpx's numeric timeout applies per phase (connect, read, write, pool), not to the whole attempt. A response that streams slowly can keep one attempt past `time_budget_ms + cold_start_ms`, so the wall-time check can undercount. Bound it?
- options: A leave it; the 300 s margin between `max_wall_seconds` (1500) and the 30-minute job limit absorbs it / B add a whole-attempt deadline
- built: A
- decision: A. Not changed here; the margin covers it.
- landed: ORCHESTRATION.md Q2 (wall-time paragraph)
