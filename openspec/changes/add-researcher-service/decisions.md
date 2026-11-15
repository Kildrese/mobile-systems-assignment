# Decisions: add-researcher-service

Context: Assignment 2 (Agentic Orchestration), due 2026-11-15 23:59 ET. The brief is extracted at
/private/tmp/claude-501/-Users-kiliandresse-Developer-nyu-mobileSystems/c9ffc0c6-afb0-4e08-ac25-22ff799bb4ad/scratchpad/pdf/assignments.txt
(sections 2–8, 13, 14, "Test it yourself", ORCHESTRATION.md Q1–Q5). Prior doc decisions: openspec/changes/add-orchestration-doc/decisions.md.
Gap being closed: the researcher is not its own HTTP service; only the verifier is (services/verifier, shared code in packages/agentkit).

## D1 Stub researcher service
- class: mine
- source: grilling
- status: decided
- question: The researcher isn't a separate service. What do we build tonight?
- options: A stub researcher / B real tracker pipeline as a local service / C document only
- decision: user, A, 2026-11-15. New `services/researcher`: POST /research {topic, k} returns developments from a JSON file with real fetchable URLs, every claim citing one source_url; GET /healthz; RESEARCHER_TOKEN (separate from VERIFIER_TOKEN); same envelope, status codes, idempotency (request_id + canonical body hash, 409, 503 + Retry-After while running), time budget → partial, and JSON-lines wire log as the verifier, reusing packages/agentkit (serve, contract, wire_log). Accepts losing the 3 points for a real top-K report.
- landed: specs/researcher-service/spec.md (all requirements); proposal.md#What Changes; tasks.md 1.1-1.7

## D2 Orchestrate command, daily tracker untouched
- class: mine
- source: grilling
- status: decided
- question: How does the stub fit in, given the tracker is both orchestrator and in-process researcher?
- options: A new plain-code orchestrate command / B rewire the daily tracker to call /research
- decision: user, A, 2026-11-15. A plain-code command (e.g. `uv run python -m tracker.orchestrate`): split the config.yaml budget between the workers, POST /research → validate → POST /verify the claims → validate (claim_ids must be ones it sent) → write report + trace + run history. Reuse the existing verifier client (backend/tracker/usecases/internships/verifying.py) and retry/backoff/charging logic rather than duplicating it. Researcher down → report says no new results and shows last run's top K marked stale; verifier down → claims unverified; either way the run is partial and names the failed worker. The daily cron tracker and its workflow are not changed.
- landed: specs/run-orchestration/spec.md#Orchestrate command, #One budget split between the workers, #Calls to the workers, #Responses are validated, #Failed workers; design.md#Decisions (reuse the client); tasks.md 2.1, 2.4, 2.5

## D3 Researcher runs as a local process
- class: mine
- source: grilling
- status: decided
- question: Where does the stub researcher run?
- options: A local uvicorn on its own port / B 4th Vercel project
- decision: user, A, 2026-11-15. Local process on its own port (e.g. :8101), started separately from the orchestrator. Verifier stays the deployed Vercel one. RESEARCHER_URL and RESEARCHER_TOKEN go in .env.example. No new Vercel project, secret or workflow.
- landed: specs/researcher-service/spec.md#Researcher service (uvicorn :8101); tasks.md 1.3, 2.7 (.env.example)

## D4 Data and database
- class: mine
- source: grilling
- status: decided
- question: What does the stub serve and where does the orchestrate command write run history?
- options: A real postings, local DB / B real postings, Neon / C hand-written JSON, local DB
- decision: user, A, 2026-11-15. The JSON file is built from a real tracker report's top K (real posting URLs; public data only, nothing from private/). Run history and last top K are written via the existing tables to the DB that DATABASE_URL points at, run against local Postgres (./scripts/db-up.sh). Production Neon is still reached only by the daily cron.
- landed: specs/researcher-service/spec.md#Developments file; specs/run-orchestration/spec.md#Settings and secrets (local DATABASE_URL only), #Report, trace and run history; tasks.md 1.2, 2.4, 2.6

## D5 Who can trigger paid calls
- class: mine
- source: grilling
- status: decided
- question: Each orchestrate run spends Groq through the verifier. Who can trigger it?
- options: A only a VERIFIER_TOKEN holder running it locally / B also an API route
- decision: user, A, 2026-11-15. Only the owner, locally, with VERIFIER_TOKEN in env. No API route, no cron. The stub researcher makes no paid calls. Spend capped by config.yaml budgets.
- landed: specs/run-orchestration/spec.md#Orchestrate command (started only by hand, no route/cron/workflow); proposal.md#Impact (Paid calls)

## D6 Verifier stays on Vercel
- class: mine
- source: grilling
- status: decided
- question: The brief says Render; the verifier is on Vercel. Keep it?
- options: A keep Vercel / B also deploy on Render
- decision: user, A, 2026-11-15. Keep Vercel; ORCHESTRATION.md already justifies it. Measured 2026-11-15 ~16:30 ET: first /healthz 1.75 s (cold), then 0.18–0.20 s (warm). Use these in Q2's placeholders.
- landed: tasks.md 3.4

## D7 No manual tracker run; answer from existing artifacts
- class: mine
- source: grilling
- status: decided
- question: Trigger a manual tracker workflow run for fresh traces?
- options: A no, use artifacts / B yes after code lands / C yes now
- decision: user, A, 2026-11-15. The Actions artifacts of 13 daily runs (Nov 3–15) are saved at /private/tmp/claude-501/-Users-kiliandresse-Developer-nyu-mobileSystems/c9ffc0c6-afb0-4e08-ac25-22ff799bb4ad/scratchpad/artifacts/<run_id>/tracker-<run_id>/{traces,reports}/ (6 runs contain /verify calls, 13 calls in total). Q2 and Q5 use these plus local orchestrate runs. Never commit them wholesale (reports/ and traces/ are ignored except run1/run2); quote numbers in ORCHESTRATION.md instead.
- landed: tasks.md 1.2 (stub data from the newest artifact), 3.4, 3.7

## D8 Q5 verdict check done by an agent
- class: mine
- source: grilling
- status: decided
- question: Who hand-checks every unsupported verdict plus 10 random supported ones?
- options: A agent preps, user checks / B agent checks
- decision: user, B, 2026-11-15. An agent re-fetches each URL and judges each verdict. ORCHESTRATION.md must say plainly that a model, not a person, did this check (orchestrator's condition; the brief says "hand-check").
- landed: tasks.md 3.7

## D9 ORCHESTRATION.md completed in this change
- class: expensive
- source: grilling
- status: resolved
- decision: orchestrator, 2026-11-15. Q1, Q4, Q5 are TODO and Q2 has `<measure:>` placeholders on master. This change fills them and updates the intro and Q2/Q3 to cover three services (researcher, verifier, orchestrator). Q2's "run 1" is the first local orchestrate run with all three services. Every number comes from a trace, a report or D6; no invented numbers (add-orchestration-doc D3). The extra normalisation in packages/agentkit text.py (quote/dash/nbsp mapping) must be stated, per brief §9.
- landed: tasks.md 3.1-3.8

## D25 Production numbers for Q5 (read-only Neon query)
- class: cheap
- source: grilling
- status: resolved
- decision: orchestrator, 2026-11-15, read-only query on Neon project "Mobile Systems" (empty-firefly-03102623); the DB is awake. tracker_runs: 41 runs, 19 complete, 22 partial (curator.max_steps 6, editor.max_steps 8, scout.max_steps 6, terminal:request 2); failed_services is empty on all 41. Claims across all internship_offers rows: 322 supported, 7 unsupported, 4 unverified, 0 unreachable. Latest verdict per (opportunity, field): 43 supported, 2 unsupported. Rows repeat across runs, so use the "latest per claim" figures as the per-claim counts. Q5's check covers these 2 unsupported claims plus 10 random supported ones (D8). Query the claims with `neon connection-string --project-id empty-firefly-03102623` and a read-only psycopg session (`default_transaction_read_only=on`); never print the connection string.

## D10 The researcher's budget share in config.yaml
- class: mine
- source: spec-writer
- status: decided
- question: D2 says split the config.yaml budget between the workers but not how. What are `options.researcher`'s `time_budget_ms`, `max_steps`, `max_fetches`, `max_tokens`, `cold_start_ms` and `max_attempts`? The researcher's share plus 5 x the verifier's share must fit `limits` (today 74 steps, 70 fetches, 235,000 tokens; the verifier takes 10 / 30 / 60,000). The stub spends nothing, so only `time_budget_ms` (and the timeout) changes behaviour today.
- options: values are yours; no default picked
- built: code and tests read `options.researcher` from the policy, tests use fixture values; `config.yaml` is not edited, so the command exits 1 on the real config until this is decided
- decision: user, the agents' share, 2026-11-15: time_budget_ms 60000, max_steps 63, max_fetches 30, max_tokens 170000, cold_start_ms 5000, max_attempts 4, so researcher + 5 × verifier = limits. If the reserve_tokens check (D28a) rejects this exact split, say so and stop; don't change the values. (User also asked about separate Groq accounts per agent; the orchestrator advised against it, since Groq's AUP reportedly forbids getting around rate limits with multiple accounts. Not pursued.)
- landed: specs/run-orchestration/spec.md#One budget split between the workers (rule only, no values); tasks.md 2.8 (blocked), 3.1, 3.4

## D11 Who runs the orchestrate command for Q2 run 1 and Q5
- class: mine
- source: spec-writer
- status: decided
- question: Run 1 (D9) calls the deployed verifier, which spends Groq (up to `max_requests` = 5 calls). D5 says only the owner, locally, with VERIFIER_TOKEN. May a group 3 agent run it on your machine with the token from backend/.env, or do you run it and hand over the report and trace?
- options: A you run it / B an agent runs it once
- built: nothing; task 3.1 is blocked, 3.4 and 3.7 wait for its numbers
- decision: user, B, 2026-11-15. An agent runs it once, on this machine, with VERIFIER_TOKEN read from backend/.env into the process env, never printed, logged or committed. Exactly one paid run; a failed run is reported and not retried without asking.
- landed: tasks.md 3.1 (run 1 done, see D31)

## D12 Command module layout
- class: cheap
- source: spec-writer
- status: resolved
- question: Where does the orchestrate command live, given tests_tracker can't use Postgres?
- options: A `backend/tracker/orchestrate.py` with a DB-free `orchestrate()` and DB code in `main()` via function-local `app` imports / B a separate `app/orchestrate.py`
- decision: spec-writer, A, 2026-11-15: matches D2's `python -m tracker.orchestrate` and the requested layout; importing `tracker` still never needs DATABASE_URL.
- landed: design.md#Decisions; tasks.md 2.4

## D13 Generalize the verifier client instead of a second client
- class: cheap
- source: spec-writer
- status: resolved
- decision: spec-writer, 2026-11-15: `verifying.Client` gets `path`, `worker`, `response_model`, `caller` fields whose defaults keep today's behaviour; `_fits`/`_charge` become public. Follows D2 ("reuse ... rather than duplicating").
- landed: design.md#Decisions; tasks.md 2.1

## D14 Researcher settings model and where it is checked
- class: cheap
- source: spec-writer
- status: resolved
- decision: spec-writer, 2026-11-15: `options.researcher` reuses `VerifierSettings` (its `max_requests` ignored). The daily run's `validate()` ignores it; the orchestrate command checks researcher share + verifier allocation against `limits` and exits 1 on overflow.
- landed: specs/run-orchestration/spec.md#Settings and secrets, #One budget split between the workers; tasks.md 2.2, 2.4

## D15 /research contract bounds
- class: expensive
- source: spec-writer
- status: resolved
- question: The brief fixes the fields; the bounds are mine. Confirm: `topic` 1-200 chars, `k` 1-20, development `id` 1-100, `title` 1-300, `summary` 0-2000, 1-20 claims per development (one /verify request each), claim_ids unique across the response, at most k developments.
- options: A as written / B other bounds
- built: A (written into the spec so groups 1 and 2 can start; mirrors VerifyPayload's limits)
- decision: orchestrator, A, 2026-11-15: mirrors the verifier's limits; nothing later depends on other values.
- landed: specs/researcher-service/spec.md#Research request, #Research response; specs/run-orchestration/spec.md#Responses are validated; tasks.md 1.1

## D16 Mapping developments into internship_offers
- class: cheap
- source: spec-writer
- status: resolved
- decision: spec-writer, 2026-11-15: no schema change (D4). `opportunity_id` = rank, `section` `top_k`, `company` "", `url` = first claim's source_url, role_type/term/remote/status `unknown`, locations [], verified false, claims `field` = claim_id after the first `:`. A researcher-down run writes no offers, so "last top K" = newest earlier run with top-K offers, no flag column. Local DB only.
- landed: specs/run-orchestration/spec.md#Report, trace and run history, #Failed workers; design.md#Decisions

## D17 Run outcome rules
- class: cheap
- source: spec-writer
- status: resolved
- decision: spec-writer, 2026-11-15: a worker `partial` 200 counts as that worker failed (as the daily Verify stage does). Researcher partial with 0 developments = researcher down (stale). Developments left unverified for `max_requests` or budget: partial, stop reason `verifier.max_requests`, no worker named. Exit 0 complete, 2 partial, 1 refused to start; never 3.
- landed: specs/run-orchestration/spec.md#Failed workers, #Orchestrate command

## D18 Stub delay and time budget
- class: cheap
- source: spec-writer
- status: resolved
- decision: spec-writer, 2026-11-15: `RESEARCHER_DELAY_MS` (default 100) per development; stop before a development whose delay would pass `time_budget_ms`. Gives the tiny-budget and duplicate-while-running checks something real. `topic` does not filter the file.
- landed: specs/researcher-service/spec.md#Researcher time budget, #Developments file; tasks.md 1.4

## D19 Refuse to start on missing settings or a non-local database
- class: cheap
- source: spec-writer
- status: resolved
- decision: spec-writer, 2026-11-15: missing RESEARCHER_URL/TOKEN or VERIFIER_URL/TOKEN, or a DATABASE_URL host other than localhost/127.0.0.1/::1, exits 1 before any request (enforces D4 and D5 in code). Testing "worker down" uses a dead local port instead.
- landed: specs/run-orchestration/spec.md#Orchestrate command, #Settings and secrets; tasks.md 2.4, 2.6, 2.9

## D20 Stub data source and ids
- class: cheap
- source: spec-writer
- status: resolved
- decision: spec-writer, 2026-11-15: built by hand from the top K of report 20261115T093900Z-8e97 (newest D7 artifact): ids `d<rank>`, claim_ids `d<rank>:<field>`, claim text copied from the report's "Claims checked (top K)", URLs checked with curl at build time, no fit reasons.
- landed: specs/researcher-service/spec.md#Developments file; tasks.md 1.2

## D21 CI job for the researcher
- class: cheap
- source: spec-writer
- status: resolved
- decision: spec-writer, 2026-11-15: add a `researcher` job to ci.yml copied from the `verifier` job. No trigger change.
- landed: tasks.md 1.6

## D22 Report and trace paths, run id
- class: cheap
- source: spec-writer
- status: resolved
- decision: spec-writer, 2026-11-15: `reports/orchestrate-<run_id>.md`, `traces/orchestrate-<run_id>.jsonl` (gitignored); the wire `run_id` UUID is also the `tracker_runs.id`; trace `service` is `orchestrator`.
- landed: specs/run-orchestration/spec.md#Report, trace and run history

## D23 No verdict reuse between orchestrate runs
- class: cheap
- source: spec-writer
- status: resolved
- decision: spec-writer, 2026-11-15: every run sends all claims of up to `max_requests` developments; spend stays within the existing cap (D5). Reuse would need verdict storage outside the daily tracker's SQLite state.
- landed: design.md#Goals / Non-Goals

## D24 Q5 random sample
- class: cheap
- source: spec-writer
- status: resolved
- decision: spec-writer, 2026-11-15: the 10 supported verdicts are drawn with `random.Random(2630).sample` from all supported verdicts in the D7 runs and local runs; ORCHESTRATION.md states the seed.
- landed: tasks.md 3.7

## D26 Q5 counts over one set of claims
- class: cheap
- source: reviewer
- status: resolved
- question: D25 counts from Neon "latest per claim" (2 unsupported, 43 supported); task 3.7 and D24 count and sample from the D7 artifacts plus local runs. Which set?
- options: A D25's Neon figures plus local runs / B D7 artifacts only
- decision: orchestrator, A, 2026-11-15. Counts come from D25's Neon figures plus local orchestrate runs. The check covers D25's 2 unsupported claims, any unsupported from local runs, and 10 supported drawn with random.Random(2630).sample from the same set. This overrides D24's set and task 3.7's wording.

## D27 Following one request across all three logs (brief §13)
- class: cheap
- source: reviewer
- status: resolved
- decision: orchestrator, 2026-11-15. In 3.1, start the researcher with stdout piped through `tee` to a scratchpad file. In 3.4, pull the verifier's lines for run 1 from Vercel runtime logs (read-only: `vercel logs --project mobile-systems-verifier --since 1h --json` from services/verifier). ORCHESTRATION.md then shows one request_id in the orchestrator trace, the researcher log and the verifier log.

## D28 Reviewer should-fixes for group 2
- class: cheap
- source: reviewer
- status: resolved
- decision: orchestrator, 2026-11-15. (a) The split check compares against what `fits()` really allows: the token total minus `reserve_tokens` (backend/tracker/budget.py:83-90). (b) The generalized `Client` takes its 401 message and endpoint from its worker fields, so a researcher 401 never reads "verifier" (verifying.py:29, :233). (c) Add tests for the "Missing researcher URL" (2.6) and "Invalid file" (1.5) scenarios. (d) Group 2 updates the TrackerRun docstring (backend/app/models.py:81) together with publish_report.py's. (e) Drop RESEARCHER_DELAY_MS as an env var and use a module constant `DELAY_MS`, which tests patch. Skip 2.5(e)/(f) if the existing client tests already cover them.
- landed: (e) services/researcher/main.py `DELAY_MS = 100`. Wording fixed by the group 3 implementer: design.md#Decisions (Stub timing), specs/researcher-service/spec.md#Researcher time budget, tasks.md 1.3-1.5.

## D29 Stale offers keep their URL; small report wording
- class: cheap
- source: implementer, task 2.4
- status: resolved
- decision: implementer, 2026-11-15. The last-top-K lookup also returns each offer's `url`, so stale claims show a source URL like fresh ones (claims rows store no `source_url`; the spec's claim shape is unchanged). Report: `- Time: <start> to <end>`, `- Status: partial (<stop reason>)`, no-new-results sentence "The researcher gave no developments in this run."
- landed: backend/tracker/orchestrate.py (`find_last_top_k`, `_report`)

## D30 The researcher's D10 share leaves no room for a retry after a timeout
- class: mine
- source: implementer, task 2.8
- status: decided
- question: D10's split passes the check exactly (tokens 170,000 + 5 x 12,000 = 230,000 = 235,000 - 5,000 reserve). But the client charges a full share for each attempt that times out or gets a 5xx, and retries only if another full share fits: after one such researcher attempt only 60,000 tokens are left, so `max_attempts` 4 is effectively 1 for timeouts and 5xx (refused connections, never charged, are still retried 4 times). The run then reports the researcher down. Keep it?
- options: A keep (one try on a timeout; the stub never times out in practice) / B lower the researcher's max_tokens so a retry fits (e.g. 80,000: 2 x 80,000 + 60,000 = 220,000) / C don't charge the researcher's failed attempts (it spends nothing), a code change in the client
- built: A (config.yaml as D10 says; nothing else depends on it)
- decision: user, A (keep one try on a researcher timeout or 5xx), 2026-11-15. ORCHESTRATION.md Q3 may discuss the trade-off.
- landed: config.yaml options.researcher (comment states it)

## D41 The local-database check can be bypassed with a `host=` query parameter
- class: cheap
- source: reviewer (security)
- status: resolved
- question: `main()` checks only `make_url(...).host` (backend/tracker/orchestrate.py, the LOCAL_HOSTS check). SQLAlchemy's psycopg dialect lets `?host=` replace the host (`?hostaddr=` and `?service=` also go straight to libpq), so `postgresql://u:p@localhost/db?host=ep-x.neon.tech` passes and writes to Neon, breaking D4/D19. Only someone who hand-edits backend/.env can do this.
- options: A after connecting, check `db.connection().connection.info.host` is in LOCAL_HOSTS or a Unix socket path starting with "/", else exit 1 before orchestrate() / B also refuse host, hostaddr or service keys in url.query / C keep as is
- built: C
- decision: orchestrator, A, 2026-11-15, plus a test with `DATABASE_URL=postgresql://u:p@localhost/db?host=ep-x.neon.tech` in backend/tests/test_orchestrate_history.py.
- landed: backend/tracker/orchestrate.py main() (driver_connection.info.host after connecting); backend/tests/test_orchestrate_history.py::test_host_override_in_the_url_refuses_to_start (uses `?host=0.0.0.0` on the local test database instead of ep-x.neon.tech, so the test needs no network and never reaches Neon)

## D31 Invalid worker answers leak into the report
- class: cheap
- source: reviewer
- status: resolved
- question: On an invalid 200, the client's failure detail is str(ValidationError)[:300], which quotes the worker's input values (pydantic's input_value=...). orchestrate.py (around :128/:156) puts it in "Failed workers" in the report and in tracker_runs.report_markdown, against brief §5 and the spec's "Responses are validated". Fix how?
- options: A in orchestrate.py, record only "invalid_response" (no detail) for that reason / B in verifying.py, build the detail from err.errors(include_input=False) (also changes the daily tracker's failure text) / C set hide_input_in_errors on agentkit _Strict
- built: neither (detail is passed through)
- decision: orchestrator, A, 2026-11-15, so the daily tracker's output is unchanged. Add a test: a /research 200 with an extra field holding a marker string, and assert the marker is in neither outcome.markdown nor the trace. Note for a later fix branch (not this one): the daily tracker's verifier path may have the same leak.
- landed: backend/tracker/orchestrate.py _failure(); backend/tests_tracker/test_orchestrate.py::test_invalid_answer_detail_stays_out_of_report_and_trace

## D32 run-orchestration spec's over-allocation cap
- class: cheap
- source: reviewer
- status: resolved
- decision: orchestrator, 2026-11-15. Update the run-orchestration spec's over-allocation message to say the cap is the limit minus reserve_tokens, matching the code (D28a; orchestrate.py:66; test "more than 59,000").
- landed: specs/run-orchestration/spec.md (Requirement: One budget split between the workers)

## D33 How run 1 and the Q5 check were done
- class: cheap
- source: implementer, tasks 3.1 and 3.7
- status: resolved
- decision: implementer, 2026-11-15. (a) backend/.env has VERIFIER_TOKEN but no VERIFIER_URL; run 1 used the production alias https://mobile-systems-verifier.vercel.app (its /healthz answered 200 just before), a fresh random RESEARCHER_TOKEN for that process only, and the local DATABASE_URL. One paid run, complete, exit 0. (b) The implementer may not query Neon, so the Q5 claim set came from the 13 D7 reports' "Claims checked (top K)" sections, latest verdict per (opportunity, field). They give exactly D25's numbers (322/7/4/0 rows; 43 supported, 2 unsupported latest), so they are the same set. (c) Sample order for random.Random(2630).sample: the 45 latest daily claims sorted by (company, title, field), then run 1's 26 in report order; supported only, 68. (d) coinbase.com answered 403 to the agent's curl, so that posting was read from Greenhouse's public job API for the same job id. Result: 0 of 13 verdicts wrong.
- landed: ORCHESTRATION.md (intro, Q2, Q5)

## D34 Stale line numbers in ORCHESTRATION.md Q2/Q3
- class: cheap
- source: reviewer
- status: resolved
- question: Every `verifying.py:` line number is 5 short (e4b1a0d moved the code), and three Q2 references were already stale on master. Fix to: 169→174, 172→177, 179→184, 206-207→211-212, 214-225→219-230, 227-229→232-234 (twice, Q2 and Q3), 237→243, 239-240→244-245, 335-336→340-341. Also `tracker.yml:30`→`:70`, `tracker.yml:74-75`→`:114-115`, and `wiring.py:820-821`→`backend/tracker/usecases/internships/wiring.py:824`.
- options: A fix the numbers / B drop the line numbers
- decision: orchestrator, A, 2026-11-15. Re-verify every file:line in ORCHESTRATION.md against the current HEAD (a9fdc42 touched orchestrate.py after the doc was written), not just the list above.
- landed: ORCHESTRATION.md Q1-Q4 (all file:line references re-checked against HEAD; only the listed ones plus `verifying.py:48-59` (was 49-60, class starts at 48) changed)

## D35 Two numbers in ORCHESTRATION.md don't match their source
- class: cheap
- source: reviewer
- status: resolved
- decision: orchestrator, 2026-11-15. (a) The intro's date range becomes 2026-11-02 to 2026-11-15, noting there's no 11-06 run. (b) Q2's page-fetch range becomes 0.04 to 0.51 s (the Vercel log's fetch for 96ca49e3 attempt 2 took 36 ms). (c) The 2.01 s pre-run /healthz is in no log file: say it was measured by hand with curl and not logged.
- landed: ORCHESTRATION.md intro (daily runs), Q2 (page fetch range, /healthz note)

## D36 Possibly wrong supported verdict outside the Q5 sample
- class: cheap
- source: reviewer
- status: resolved
- decision: orchestrator, 2026-11-15. Genius AI's location claim "NYC or San Francisco or Remote" is marked supported with only "Location: NYC" as evidence. Q5 adds one sentence: noticed outside the random sample, the evidence covers only part of the claim, and it's not counted in the 13. That shows the limit of excerpt-contains checking. No code change.
- landed: ORCHESTRATION.md Q5, after the two notes
