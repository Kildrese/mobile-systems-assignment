# Tasks

## 1. Use-case wiring (internship-pipeline)

- [ ] 1.1 Merge the implemented `feat/agent-orchestration` into this branch and run the full `tests_tracker` suite. Verify it passes before any use-case code lands
- [ ] 1.2 Add `usecases/internships/` with its registration (tools, stage list with Collect, Rank and Report marked required) and `internships` in the known-use-case map, plus validation that `scout`, `curator` and `editor` profiles exist. Verify with unit tests: a missing profile is named, the stage order matches the spec

## 2. State migration 2 (all opportunity capabilities)

- [ ] 2.1 Add migration 2 (`sources`, `raw_postings`, `opportunities`, `opportunity_links`, `ranks`, `summaries`, `http_cache`; design D6) with store methods. Verify with unit tests: a core-only state file upgrades in place, uniqueness on `(source_id, external_id)`, and pending postings survive across runs

## 3. Sources and collectors (opportunity-sources)

- [ ] 3.1 Implement watchlist loading from config into state, with board-identifier validation. Verify with unit tests: seeded with `added_by: config`, an invalid identifier is rejected before any URL is built
- [ ] 3.2 Implement the Greenhouse, Lever and Ashby collectors over the core fetch path, with pydantic response models and HTML-to-text for descriptions (design D5). Verify with respx tests using recorded JSON fixtures for each board type, including a 503 source marked `unreadable` while the others succeed
- [ ] 3.3 Implement conditional requests with `http_cache` (ETag/Last-Modified, `304` reuses postings). Verify with a respx test: the second run sends `If-None-Match`, gets `304`, and the trace shows `not_modified`
- [ ] 3.4 Implement the title and location pre-filter with traced counts. Verify with a unit test: a senior role is filtered, an intern role with no location is kept
- [ ] 3.5 Implement `propose_source` with code validation (known kind, identifier format, evidence URL seen this run, not a duplicate, per-run cap) and its CLI command. Verify with unit tests for `unseen_evidence`, a duplicate, the cap, and acceptance

## 4. Curation (opportunity-curation)

- [ ] 4.1 Implement quote normalization and verification (design D7). Verify with unit tests: curly quotes and whitespace match, an invented quote fails with `quote_not_found` naming the field
- [ ] 4.2 Implement the Curator tools (`get_posting`, `fetch_posting_detail` with `fetch_hosts`, `save_record`, `mark_same` with the company check, `flag_unclear`) and their CLI commands. Verify with unit tests per spec scenario, including `host_not_allowed` and `company_mismatch`
- [ ] 4.3 Implement code-side matching (same job id or canonical URL linked by code) and candidate generation for the Curator. Verify with unit tests: an exact match is linked without the model, a similar title from the same company becomes a candidate, another company never does
- [ ] 4.4 Implement the Curate stage driver (batches, conversation reset per batch, two failures lead to `flag_unclear` by code, leftovers stay pending). Verify with a scripted fake model: a batch fully processed, a malformed call recovered, budget exhaustion leaves postings pending

## 5. Lifecycle (opportunity-lifecycle)

- [ ] 5.1 Implement board-based liveness (absent from a read board → closed; unreadable → unchanged) and reopening. Verify with unit tests for each spec scenario
- [ ] 5.2 Implement page-based liveness (conditional request; 404/410/closing patterns → closed; failures → unknown). Verify with respx tests: closing wording, 410, timeout → `unknown`

## 6. Ranking, Editor and report (opportunity-report)

- [ ] 6.1 Implement scoring and ranking with stored ranks (design D8). Verify with unit tests: the same input gives the same order, and work-authorization text does not change the score
- [ ] 6.2 Implement the Editor tools (`get_opportunities`, the summaries `finish`) and summary checks (design D9). Verify with unit tests: an added salary is rejected, an unknown id is rejected, a valid summary is stored
- [ ] 6.3 Implement the cumulative report renderer (core header plus per-stage outcomes, then New, Still open with top K marked and unverified notes, then Closed). Verify with a unit test over a two-run fixture that matches the spec's second-day scenario, with no opportunity listed twice

## 7. Pipeline end to end (internship-pipeline)

- [ ] 7.1 Write the task prompts for each agent stage and wire the stages to the conductor. Verify with a scripted end-to-end test over fake providers and fixture boards: complete run exits 0; Groq daily-quota during Curate exits 2 with Liveness, Rank and Report done; network cut with empty state exits 3 and the report says no source could be read; Scout disabled starts at Collect
- [ ] 7.2 Add an injection test: a fixture posting and a fetched page contain instructions. The scripted Scout and Curator "obey" them (propose an internal URL, `mark_same` across companies, fetch an off-list host). Verify every action is refused, records are unchanged, and the trace shows `injection_suspected`

## 8. Policy, docs and CI

- [ ] 8.1 Write the internship `config.yaml` (design D10) with a watchlist of about 15 public NYC startup boards, each identifier checked by hand. Verify the committed config loads and a test validates every watchlist entry's format
- [ ] 8.2 Add an internship section to `docs/tracker.md` (stages, agents and their privileges, budget split, lifecycle, report layout, hosts to allowlist) and update the README run instructions. Verify the documented offline commands run as written
- [ ] 8.3 Run ruff and the full `tests_tracker` suite in CI. Verify the CI job passes on the branch

## 9. Integration check

- [ ] 9.1 With real keys on a machine that can reach Groq, Tavily and the board APIs, run twice at least a day apart. Verify run 2's report has New, Still open and Closed sections, no opportunity is listed twice, most boards returned `304`, and per-agent usage is in the trace summary
