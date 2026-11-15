# Decisions: fix-verify-wall-time-and-retries

## D1 Verify stage ignores max_wall_seconds
- class: mine
- source: grilling (copied from add-orchestration-doc D12, raised by the reviewer)
- status: decided (user)
- question: Verifier hangs can push a run past GitHub's 30-minute job limit (`.github/workflows/tracker.yml:30`), so nothing is published. `config.yaml:47` sets `max_wall_seconds: 1500`, but `_fits` (`verifying.py:299-306`) never checks wall time. Make Verify stop at the run's wall-time budget?
- options: A Verify checks remaining wall time before each request and marks the rest unverified / B lower `max_attempts` or `cold_start_ms` / C leave it and document
- built: A
- decision: A. Kilian, 2026-11-15: Verify checks the run's remaining wall time before each request; claims it can't send are marked unverified.
- landed: specs/internship-pipeline/spec.md#Requirement: Verify stage calls the verifier (second paragraph); #Scenario: Not enough wall time left; tasks.md 1.1-1.3, 2.2, 2.3, 3.1; backend/tracker/usecases/internships/verifying.py:179 (check), :328-329 (not sent: not counted); backend/tests_tracker/test_internships_verifying.py test_no_request_when_wall_time_is_short, test_no_retry_when_the_wait_would_pass_the_deadline, test_verify_stops_at_the_run_wall_time; ORCHESTRATION.md Q2; docs/tracker.md Verification

## D2 Retried statuses
- class: mine
- source: grilling (copied from add-orchestration-doc D13, raised by the reviewer)
- status: decided (user)
- question: The client retries 502, 503 and 504 (`verifying.py:189`); the spec names only 503. Add 502/504 to the spec plus a tracker test, or narrow the code to 503?
- options: A spec + test / B code to 503 only
- built: A
- note: a retry after a 504 can repeat a paid Groq call, because the first copy may have finished its model call before the gateway gave up.
- decision: A. Kilian, 2026-11-15: add 502 and 504 to the spec's retried statuses, plus a tracker test.
- landed: specs/internship-pipeline/spec.md#Requirement: Verify stage calls the verifier (first paragraph, with the paid-retry note); #Scenario: Gateway error then success; tasks.md 2.1, 3.2; backend/tracker/usecases/internships/verifying.py:237; backend/tests_tracker/test_internships_verifying.py test_gateway_error_then_success_charges_the_lost_copy_and_the_answer (renamed for D6); docs/tracker.md Verification; ORCHESTRATION.md Q2

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
- landed: specs/internship-pipeline/spec.md#Scenario: Not enough wall time left; tasks.md 1.1; backend/tracker/usecases/internships/verifying.py:179-187

## D5 How a wall-time stop is reported and charged
- class: cheap
- source: spec-writer
- status: resolved (spec-writer)
- question: What does the run record when Verify stops on wall time?
- options: A failure reason `max_wall_seconds`, stop all requests, stage `partial` naming `verifier` (as D1 says, like a verifier that's down); a request with no attempt sent is not counted or charged; one stopped after some attempts is charged its full share under the existing "never got a valid answer" rule / B something else
- built: A
- decision: A. Follows D1 and the existing "Verifier budget share" requirement; `max_wall_seconds` is the reason name `http.py` and `report.py` already use.
- landed: tasks.md 1.2; backend/tracker/usecases/internships/verifying.py:115-125 (`VerifierFailed.attempts`), :328-329

## D6 Charge the run for copies lost to 502/504
- class: mine
- source: spec-writer
- status: decided (user)
- question: The brief says a repeated Groq call after 502/504 is bounded by "the run's budget". The run's totals count each `request_id` once, with the usage of the answer it got, so a copy lost to a 502/504 is not counted in the run's token totals. Each copy is held to the per-request share by the verifier, and the copies to `max_attempts` and wall time. Should the run's totals also charge the lost copies?
- options: A leave as is (totals count the answer's usage) / B charge a full share for each attempt that got 502/504 / C charge once per request but a full share when any attempt got 502/504
- built: B (fb1ee5d); widened by D11 and D12
- decision: B. Kilian, 2026-11-15: lost copies count. Each attempt that got a 502 or 504 (or timed out) is charged a full per-request share on top of the answer's usage, as the brief requires for a worker that never answers. A retry is only sent if another full share still fits the run's remaining totals; otherwise Verify stops and the remaining claims are unverified.
- landed: specs/internship-pipeline/spec.md#Requirement: Verify stage calls the verifier (first paragraph, charging sentences); #Scenario: Timeout then stored copy; #Scenario: Gateway error then success; #Scenario: No share left for a retry; tasks.md 4.1-4.3; backend/tracker/usecases/internships/verifying.py:172-178 (share check before a retry), :227-229 (charge a failed attempt), :326 (budget passed in); backend/tests_tracker/test_internships_verifying.py test_timeout_then_stored_copy_charges_the_lost_copy_and_the_answer, test_gateway_error_then_success_charges_the_lost_copy_and_the_answer, test_lost_copies_are_each_charged_a_share_and_no_more, test_no_retry_without_a_full_share_left, test_no_share_left_for_a_retry_is_a_partial_run; ORCHESTRATION.md Q2 "What a failed attempt costs", Q3; docs/tracker.md Verification

## D7 How the client tells Verify a request was never sent
- class: cheap
- source: implementer, task 1.2
- status: resolved (implementer)
- question: D5 says a request with no attempt sent is not counted or charged. How does `verify_top_k` know?
- options: A `VerifierFailed` carries `attempts` (copies sent; 0 = never sent) / B a separate exception class
- built: A
- decision: A. One field on the existing exception; every raise site sets it.
- landed: backend/tracker/usecases/internships/verifying.py:115-125, :328-329

## D8 One attempt can run past the client timeout
- class: cheap
- source: reviewer
- status: resolved (reviewer)
- question: httpx's numeric timeout applies per phase (connect, read, write, pool), not to the whole attempt. A response that streams slowly can keep one attempt past `time_budget_ms + cold_start_ms`, so the wall-time check can undercount. Bound it?
- options: A leave it; the 300 s margin between `max_wall_seconds` (1500) and the 30-minute job limit absorbs it / B add a whole-attempt deadline
- built: A
- decision: A. Not changed here; the margin covers it.
- landed: ORCHESTRATION.md Q2 (wall-time paragraph)

## D9 How lost copies and the "never answered" share combine
- class: cheap
- source: implementer, D6
- status: superseded by D12
- question: D6 charges a full share per attempt that got 502/504 or timed out. A request that then never gets a valid answer was charged a full share under the existing rule. Charge both?
- options: A the "never answered" share only when no attempt was charged as lost (so at least one share per sent request, one per lost copy) / B both, always
- built: A
- decision: A. A lost copy's share already covers what that request may have spent; B would charge one share too many when every attempt was lost. `VerifierFailed.lost` carries the count.
- landed: removed by D12 (`VerifierFailed.lost` and the fallback share are gone)

## D10 Which retries the share check covers, and how the stop is named
- class: cheap
- source: implementer, D6
- status: resolved (implementer)
- question: D6 says a retry is sent only if another full share fits. Check before every retry or only after a lost copy? What failure reason? D6 also names timeouts, which changes "Timeout then stored copy".
- options: A check before every retry (503 and connection errors too), reason `no_budget_share`, `stop_all` like `max_wall_seconds`, update the timeout scenario and its test to charge the lost copy / B check only after a 502/504/timeout
- built: A
- decision: A. One check in one place, before every retry, using the existing `_fits`; it matches how a first request is gated. A 503 or connection-error attempt is not charged, so the check only fails there when the run was already short. No `config.yaml` value changes.
- note: D11 now charges a 503 that is not `in_progress` and a connection dropped after sending, so the "503 or connection-error attempt is not charged" sentence holds only for `in_progress` and `httpx.ConnectError`.
- landed: backend/tracker/usecases/internships/verifying.py:172-178; specs/internship-pipeline/spec.md#Scenario: Timeout then stored copy

## D11 Which failed attempts cost a share
- class: mine
- source: reviewer + security-reviewer (review of fb1ee5d)
- status: decided (user)
- question: D6 charges only 502, 504 and timeouts. A 503 rate_limited or a dropped connection can follow a paid Groq call too. Which attempts cost a full share?
- options: A every attempt that reached the verifier and got no valid answer, except 400, 401, 409, a connection error before sending (httpx.ConnectError) and 503 in_progress / B only 502, 504 and timeouts
- built: B (fb1ee5d)
- decision: A. Kilian, 2026-11-15.
- landed: specs/internship-pipeline/spec.md#Requirement: Verify stage calls the verifier (charging sentences); #Scenario: Rate limited then success; #Scenario: Still in progress; #Scenario: No share left for a retry; tasks.md 5.1-5.4; backend/tracker/usecases/internships/verifying.py:129-130 (`FREE_STATUSES`), :206-209 (ConnectError vs dropped after sending), :218-223 (invalid 200), :227-229 (charge), :263-270 (`_error_code`); backend/tests_tracker/test_internships_verifying.py test_terminal_statuses_are_not_retried, test_in_progress_503_is_not_charged, test_no_retry_without_a_full_share_left (502, 504, timeout, 503_rate_limited, dropped); ORCHESTRATION.md Q2 "What a failed attempt costs", Q3; docs/tracker.md Verification

## D12 A request that fails every attempt
- class: mine
- source: reviewer (review of fb1ee5d)
- status: decided (user)
- question: How much is a request charged when every attempt fails? This rewrites the base spec scenario "Never answered" (one share) in "Verifier budget share". Replaces D9.
- options: A one share per charged attempt, no extra share on top / B one share total
- built: D9's rule (one share per lost attempt, plus one share only when none was lost)
- decision: A. Kilian, 2026-11-15. The final failing attempt is charged like any other under D11; drop D9's separate fallback share. An attempt that never reached the verifier (exempt under D11) costs nothing, so a request whose attempts all failed to connect costs nothing.
- landed: specs/internship-pipeline/spec.md#Requirement: Verifier budget share (MODIFIED); #Scenario: Never answered; #Scenario: Never connected; tasks.md 5.1-5.2; backend/tracker/usecases/internships/verifying.py:241-245 (no_answer, no extra share), :328-330 (verify_top_k charges nothing on failure); backend/tests_tracker/test_internships_verifying.py test_timeout_on_every_attempt_is_charged_a_share_per_attempt, test_connection_refused_on_every_attempt_costs_nothing, test_lost_copies_are_each_charged_a_share_and_no_more; ORCHESTRATION.md Q2, Q3; docs/tracker.md Verification

## D13 Which transport errors count as "never reached the verifier"
- class: cheap
- source: implementer, D11
- status: resolved (implementer)
- question: D11 exempts `httpx.ConnectError`. httpx raises `ConnectTimeout` (a `TimeoutException`, not a `ConnectError`) and `ProxyError` before sending too. Exempt them?
- options: A exempt only `httpx.ConnectError`, as D11 names it; every other `httpx.HTTPError`, `ConnectTimeout` included, is charged / B also exempt `ConnectTimeout` and `ProxyError`
- built: A
- decision: A. Follows D11's wording; it can only overcount, never miss a copy. The trace status stays `connection_error` for both refused and dropped connections. B would need the user's call, since it changes what is charged.
- landed: backend/tracker/usecases/internships/verifying.py:204-209
