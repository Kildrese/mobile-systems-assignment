# Tasks

## 1. Scout outcome (internship-pipeline, agent-orchestration)

- [ ] 1.1 Let a use case's agent stage return `complete` after a budget stop with its own reason (design D3). Verify with an orchestration test: a toy stage that defines its budget stop as done is `complete` and the run is `complete`; one that doesn't stays `partial`
- [ ] 1.2 Classify the Scout's stop: `searches_spent` after all searches are used, `partial` with searches left, on a wall-clock stop or after a terminal failure (design D1). Verify with tests for each scenario, using a faked model
- [ ] 1.3 End the Scout's stage when the `max_new_sources`-th proposal is accepted, without another model call (design D2). Verify with a test: the fake model is called no more after the cap, and the stage is `complete` with reason `max_new_sources`
- [ ] 1.4 Show the reason in the report's stage table and the trace summary. Verify with a report test

## 2. Wall time (report-publishing)

- [ ] 2.1 Set `limits.max_wall_seconds: 1500` in `config.yaml` (design D4). Verify that the policy loads and the budget sum checks still pass
- [ ] 2.2 Add a test that reads `.github/workflows/tracker.yml` and `config.yaml` and checks `timeout-minutes * 60 >= max_wall_seconds + 300`

## 3. Docs

- [ ] 3.1 Update `docs/tracker.md`: when the Scout is complete, the new wall time

## 4. Check in production

- [ ] 4.1 After merging, check the next two scheduled runs: the Scout ends `complete`, and note Curate's outcome and the "Waiting for review" count to decide on making Curate cheaper per posting
