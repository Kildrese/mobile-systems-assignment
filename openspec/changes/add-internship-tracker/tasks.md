# Tasks

Tasks marked **[parallel]** depend only on the merged core and can be built now. Tasks marked **[after orchestration]** need `add-agent-orchestration` implemented and merged into this branch. Design D12 describes the boundary between the two.

## 1. Internship schema (all opportunity capabilities)

- [x] 1.1 [parallel] Add the internship schema (`sources`, `raw_postings`, `opportunities`, `opportunity_links`, `ranks`, `summaries`, `http_cache`; design D6), versioned in its own `component_versions` row, and `OpportunityStore` over the core state connection. Verify with unit tests: a core-only state file upgrades in place, `(source_id, external_id)` is unique, pending postings survive across runs

## 2. Sources and collectors (opportunity-sources)

- [x] 2.1 [parallel] Implement watchlist loading into state, with board-identifier validation. Verify with unit tests: entries are seeded with `added_by: config`, an invalid identifier is rejected before any URL is built
- [x] 2.2 [parallel] Implement the `BoardHttp` seam over the core fetch path, and the Greenhouse, Lever and Ashby collectors with pydantic response models and HTML-to-text (design D5). Verify with respx tests using JSON fixtures for each board type, including a 503 source marked `unreadable` while the others succeed
- [x] 2.3 [parallel] Implement conditional requests with `http_cache` (ETag/Last-Modified; a `304` reuses postings). Verify with a respx test: the second read sends `If-None-Match`, gets `304`, and the trace shows `not_modified`
- [x] 2.4 [parallel] Implement the title and location pre-filter with traced counts. Verify with a unit test: a senior role is filtered out, an intern role with no location is kept
- [x] 2.5 [parallel] Implement the `propose_source` domain function (known kind, identifier format, evidence URL seen this run, not a duplicate, per-run cap). Verify with unit tests for `unseen_evidence`, a duplicate, the cap, and acceptance

## 3. Curation (opportunity-curation)

- [ ] 3.1 [parallel] Implement quote normalization and verification (design D7). Verify with unit tests: curly quotes and whitespace still match, an invented quote fails with `quote_not_found` naming the field
- [ ] 3.2 [parallel] Implement the Curator's domain functions (`get_posting`, `fetch_posting_detail` with a host list, `save_record`, `mark_same` with the company check, `flag_unclear`). Verify with unit tests per spec scenario, including `host_not_allowed` and `company_mismatch`
- [ ] 3.3 [parallel] Implement code-side matching (same job id or canonical URL is linked by code) and candidate generation. Verify with unit tests: an exact match is linked without the model, a similar title from the same company becomes a candidate, another company's never does

## 4. Lifecycle (opportunity-lifecycle)

- [ ] 4.1 [parallel] Implement board-based liveness (absent from a board that was read → closed; unreadable → unchanged) and reopening. Verify with unit tests for each spec scenario
- [ ] 4.2 [parallel] Implement page-based liveness (conditional request; 404, 410 or closing wording → closed; other failures → unknown). Verify with respx tests: closing wording, 410, timeout → `unknown`

## 5. Ranking, Editor checks and report (opportunity-report)

- [ ] 5.1 [parallel] Implement scoring and ranking with stored ranks (design D8). Verify with unit tests: the same input gives the same order, work-authorization text does not change the score
- [ ] 5.2 [parallel] Implement the Editor's domain functions (`get_opportunities`, summary validation per design D9, storing summaries). Verify with unit tests: an added salary is rejected, an unknown id is rejected, a valid summary is stored
- [ ] 5.3 [parallel] Implement the cumulative report renderer (core header plus per-stage outcomes, then New, Still open with top K marked and unverified notes, then Closed). Verify with a unit test over a two-run fixture matching the spec's second-day scenario, with no opportunity listed twice

## 6. Wiring (internship-pipeline)

- [ ] 6.1 [after orchestration] Merge the implemented orchestration into this branch and run the full `tests_tracker` suite. Verify it passes before the use case is wired in
- [ ] 6.2 [after orchestration] Add `wiring.py`: register a ToolSpec and CLI command for every tool, build the stage list (Collect, Rank and Report required), add `internships` to the known-use-case map, and require the `scout`, `curator` and `editor` profiles. Verify with unit tests: a missing profile is named, the stage order matches the spec, each tool runs through `python -m tracker.tools`
- [ ] 6.3 [after orchestration] Implement the Curate stage driver (batches, fresh conversation per batch, two failures → `flag_unclear` by code, leftovers stay pending). Verify with a scripted fake model: a batch fully processed, a malformed call recovered, budget exhaustion leaves postings pending
- [ ] 6.4 [after orchestration] Write the task prompts for the Scout, Curate and Edit stages and wire them up. Verify with a scripted end-to-end test over fake providers and fixture boards: complete run exits 0; Groq daily-quota during Curate exits 2 with Liveness, Rank and Report done; network cut with empty state exits 3 and the report says no source could be read; Scout disabled starts at Collect
- [ ] 6.5 [after orchestration] Add an injection test: a fixture posting and a fetched page contain instructions. The scripted Scout and Curator "obey" them (propose an internal URL, `mark_same` across companies, fetch an off-list host). Verify every action is refused, records are unchanged, and the trace shows `injection_suspected`

## 7. Policy, docs and CI

- [ ] 7.1 [parallel] Research and check a watchlist of about 15 NYC startups with public Greenhouse, Lever or Ashby boards, kept as data in `usecases/internships/watchlist.yaml`. Verify a test checks every entry's identifier format
- [ ] 7.2 [after orchestration] Write the internship `config.yaml` (design D10) using that watchlist. Verify the committed config loads
- [ ] 7.3 [after orchestration] Add an internship section to `docs/tracker.md` (stages, agents and their privileges, budget split, lifecycle, report layout, hosts to allowlist) and update the README run instructions. Verify the documented offline commands run as written
- [ ] 7.4 [parallel] Keep ruff and the full `tests_tracker` suite green in CI throughout. Verify the CI job passes on the branch

## 8. Integration check

- [ ] 8.1 [after orchestration] With real keys on a machine that can reach Groq, Tavily and the board APIs, run twice at least a day apart. Verify run 2's report has New, Still open and Closed sections, no opportunity is listed twice, most boards returned `304`, and per-agent usage is in the trace summary
