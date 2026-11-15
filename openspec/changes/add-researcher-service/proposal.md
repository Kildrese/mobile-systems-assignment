## Why

Assignment 2 asks for three services that talk only over HTTP: an orchestrator, a researcher and a verifier. Today only the verifier is its own service (`services/verifier`); the tracker is both the orchestrator and the in-process researcher. This change closes that gap tonight with a stub researcher and a plain-code orchestrate command, and completes `ORCHESTRATION.md` (decisions D1-D9).

## What Changes

- New service `services/researcher`: `GET /healthz`, `POST /research {topic, k}`. It returns developments from a JSON file built from a real tracker report's top K, every claim citing one real posting URL. Same envelope, token check, idempotency, time budget and JSON-lines log as the verifier, through `packages/agentkit` (`serve`, `contract`, `wire_log`). Its own `RESEARCHER_TOKEN`. Runs as a local uvicorn process on port 8101. No model calls, no fetches.
- `packages/agentkit/contract.py` gains the `/research` request and response models.
- New command `uv run python -m tracker.orchestrate` (in `backend/`): splits the `config.yaml` budget between the two workers, `POST /research`, validates, `POST /verify` per development, validates, then writes a Markdown report, a JSONL trace and run history (`tracker_runs`, `internship_offers`) to the database `DATABASE_URL` points at, which must be local. Researcher down: no new results, last run's top K shown stale. Verifier down: claims `unverified`. Either way the run is partial and names the failed worker.
- The verifier client in `backend/tracker/usecases/internships/verifying.py` is generalized (path, worker name, response model, caller name) so the orchestrate command reuses its retry, backoff, `Retry-After`, deadline and charging logic for both workers. The daily tracker's behaviour does not change.
- `config.yaml` gains `options.researcher` (the researcher's share). Its values are the user's (D10, open).
- `ORCHESTRATION.md`: intro and Q2/Q3 cover three services; Q1, Q4, Q5 written; Q2 placeholders filled from D6, the Actions artifacts (D7) and the first local orchestrate run; the extra normalisation in `agentkit/text.py` stated.
- CI gets a `researcher` job like the `verifier` job.

Not changed: the daily cron tracker, its workflow, the deployed verifier, Vercel projects, secrets, Neon.

## Capabilities

### New Capabilities
- `researcher-service`: the stub researcher's contract, auth, idempotency, time budget, data file and log.
- `run-orchestration`: the local orchestrate command: budget split, calls, validation, failure handling, report, trace and run history.

### Modified Capabilities
None. `claim-verification` and `internship-pipeline` keep their requirements; the client refactor is internal.

## Impact

- New: `services/researcher/` (`main.py`, `developments.json`, `pyproject.toml`, `uv.lock`, `.env.example`, `tests/`), `backend/tracker/orchestrate.py`, `backend/tests_tracker/test_orchestrate.py`, `backend/tests/test_orchestrate_history.py`.
- Changed: `packages/agentkit/src/agentkit/contract.py`, `backend/tracker/usecases/internships/verifying.py`, `backend/tracker/usecases/internships/wiring.py` (`InternshipOptions.researcher`), `backend/tracker/config.py` (`TrackerSecrets.researcher_url/token`), `backend/.env.example`, `config.yaml` (blocked on D10), `.github/workflows/ci.yml` (one job), `ORCHESTRATION.md`, `backend/app/publish_report.py` docstring.
- Dependencies: none new. The researcher's `pyproject.toml` lists the same packages and versions as the verifier's.
- Paid calls: each orchestrate run makes up to `options.verifier.max_requests` `/verify` calls to the deployed verifier, which call Groq. Only someone with `VERIFIER_TOKEN` running the command locally can trigger it (D5). No API route, no cron. The researcher makes no paid calls.
- Database: no migration. Writes go to local Postgres only.
