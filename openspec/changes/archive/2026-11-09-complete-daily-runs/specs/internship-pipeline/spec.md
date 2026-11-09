# Spec Delta

## ADDED Requirements

### Requirement: Scout stage outcome
The Scout's stage SHALL be `complete` when the Scout calls `finish`; when code has accepted `agents.scout.options.max_new_sources` proposals in the run, in which case code SHALL end the stage without another model call (reason `max_new_sources`); or when the Scout's step or token budget stops it after all of its `max_searches` have been used (reason `searches_spent`). It SHALL be `partial` when a step or token budget stops it with searches left, when the run's wall-clock budget stops it, or when a provider fails terminally. The reason SHALL appear in the stage's trace summary and in the report's stage table.

#### Scenario: Searches spent, then out of steps
- **WHEN** the Scout has used all its searches and then reaches `scout.max_steps` while reading results
- **THEN** the Scout's stage is `complete` with reason `searches_spent`, and the proposals it made are kept

#### Scenario: Out of steps with searches left
- **WHEN** the Scout reaches `scout.max_steps` having used 3 of 6 searches
- **THEN** the Scout's stage is `partial` with reason `scout.max_steps`

#### Scenario: Proposal cap reached
- **WHEN** code accepts the Scout's fifth proposal and `max_new_sources` is 5
- **THEN** the stage ends `complete` with reason `max_new_sources`, and no further model call is made for the Scout

#### Scenario: Wall clock
- **WHEN** the run's `max_wall_seconds` stops the Scout, whatever its search count
- **THEN** the Scout's stage is `partial` with reason `max_wall_seconds`

#### Scenario: Complete daily run
- **WHEN** the Scout ends `complete` by any of the rules above and every other stage is `complete`
- **THEN** the run is `complete` and the command exits `0`
