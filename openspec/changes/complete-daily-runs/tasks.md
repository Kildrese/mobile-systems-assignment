# Tasks

## 1. Scout outcome (internship-pipeline, agent-orchestration)

- [x] 1.1 Let a use case's agent stage return `complete` after a budget stop with its own reason (design D3). Stages already build their own `StageOutcome`, so the conductor needed no change. Verified by the Scout pipeline test: the run is `complete` after the Scout's budget stop; stages without a rule keep `StageOutcome.from_stop` and stay `partial`
- [x] 1.2 Classify the Scout's stop: `searches_spent` after all searches are used, `partial` with searches left, on a wall-clock stop or after a terminal failure (design D1). Verified with a table test of `scout_outcome` (finish, cap, steps or tokens with searches spent or left, the run's own budget, wall clock, a provider failure) and a full pipeline run that stops on `scout.max_steps` after both searches
- [x] 1.3 End the Scout's stage when the `max_new_sources`-th proposal is accepted, without another model call (design D2), through the loop's existing `done` check. Verified with a test: the fake model is called no more after the cap, and the stage is `complete` with reason `max_new_sources`
- [x] 1.4 Show the reason in the report's stage table and the trace summary. Verified in the pipeline test: the stage table shows `| scout | complete | searches_spent |`

## 2. Wall time (report-publishing)

- [x] 2.1 Set `limits.max_wall_seconds: 1500` in `config.yaml` (design D4). The committed-config test loads it
- [x] 2.2 Add a test that reads `.github/workflows/tracker.yml` and `config.yaml` and checks `timeout-minutes * 60 >= max_wall_seconds + 300` (fails at 1,800 s, checked)

## 3. Docs

- [x] 3.1 Update `docs/tracker.md`: when the Scout is complete, the new wall time

## 4. Check in production

- [ ] 4.1 After merging, check the next two scheduled runs: the Scout ends `complete`, and note Curate's outcome and the "Waiting for review" count to decide on making Curate cheaper per posting
