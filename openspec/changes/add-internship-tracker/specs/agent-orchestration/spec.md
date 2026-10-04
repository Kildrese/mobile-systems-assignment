# Spec Delta

## MODIFIED Requirements

### Requirement: Stage and run outcomes
Each stage SHALL end as `complete`, `partial` (stopped by a budget, or ended early with work left over), `skipped` (disabled, or skipped after a terminal failure), or `failed`. After a terminal failure, later agent stages that need what failed SHALL be skipped: for a daily quota from the stage's own model provider, the stages using that same model, because providers such as Groq count daily quotas per model; for any other terminal failure (bad key, payment, a rejected request, unreachable), every stage using that provider. The run SHALL be:
- `failed` when a stage marked `required` failed;
- `partial` when any stage is partial, failed without being marked `required`, or was skipped after a terminal failure;
- `complete` otherwise.

The run's stop reason SHALL be that of the first stage with a terminal failure, if any, and otherwise that of the first stage that was not complete. Exit codes SHALL follow the core: `0` complete, `2` partial, `3` failed. A report SHALL be written in every outcome.

#### Scenario: Daily quota mid-run
- **WHEN** an agent stage gets a daily-quota failure from its model provider
- **THEN** that stage is partial, later agent stages using the same model are `skipped` with reason `terminal:quota`, stages using another model of that provider still run, later code stages still run, the report is written, and the command exits `2`

#### Scenario: Rejected key mid-run
- **WHEN** an agent stage gets an authentication failure from its model provider
- **THEN** later agent stages using that provider are `skipped` with reason `terminal:auth`, whatever their model

#### Scenario: Required stage fails
- **WHEN** a code stage marked `required` raises a terminal error
- **THEN** the run is `failed`, a report naming the stage and error is written, and the command exits `3`
