# Proposal

## Why

Every run so far has ended `partial`: the first production run (`20261004T173811Z-d334`) and both local runs on 2026-10-04. Two causes account for it, and neither means the run did a bad job:

- **The Scout always stops on a budget.** Its work is open-ended (there is always another page to search), so it rarely calls `finish` before its 12 steps or 50,000 tokens run out. Any stage that stops on a budget makes the whole run partial, so a daily Scout alone makes every run partial.
- **The wall clock is too short for Groq's free tier.** Both local runs stopped at about 870 of 900 seconds. Most of that time is waiting on Groq's per-minute token limits, not work. The Actions job is capped at 30 minutes and Actions minutes are free in this public repository, so a 900-second cap is the binding constraint without saving anything.

`partial` should mean something fell short: a stage was cut off with work left. As it stands, the status reports the Scout's design, so it carries no information. The Scout stays daily.

## What Changes

- **The Scout's stage has a defined end.** It is `complete` when it calls `finish`, when it reaches `max_new_sources` (code ends the stage right away, since nothing more can be accepted), or when a step or token budget stops it after it has used all its searches. A stop with searches left, a wall-clock stop and a provider failure stay `partial`.
- **The orchestration layer allows this.** A use case may define a budget stop as the end of a stage's work. Without such a definition a budget stop is still `partial`, as before.
- **More wall time.** `limits.max_wall_seconds` goes from 900 to 1,500. The workflow's 30-minute job timeout stays, and the publishing spec now requires the timeout to leave room for the full wall-time budget plus setup and publishing.

## Capabilities

### Modified Capabilities
- `internship-pipeline`: when the Scout's stage is complete.
- `agent-orchestration`: a use case may define a budget stop as the end of a stage's work.
- `report-publishing`: the job timeout covers the run's full wall-time budget.

## Impact

- **Code:** `backend/tracker/usecases/internships/wiring.py` (Scout stage outcome, and ending the stage at the proposal cap), possibly a small hook in `conductor.py` or `agents.py` for ending an agent stage from code (design D2). `config.yaml` (`max_wall_seconds`).
- **No change** to budgets other than wall time, to the Scout's tools or privileges, or to Curate and Edit.
- **Docs:** `docs/tracker.md` (Scout outcome, wall time).
- **Not in this change:** making Curate cheaper per posting (code filling title and location from the board JSON). Decide after a few daily runs, once the first-run backlog has drained.
