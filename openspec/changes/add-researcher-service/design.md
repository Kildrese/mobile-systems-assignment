## Context

The verifier (`services/verifier`) already shows the pattern: `agentkit.service.serve` does token, schema, idempotency and the `in` log line; the service supplies only `work`. The tracker's Verify stage already has a client with retries, backoff, `Retry-After`, a wall-time deadline and per-attempt charging (`verifying.Client`). Run history lives in `tracker_runs` / `internship_offers`, written by `app.publish_report.publish`. Deadline: implemented, checked and reviewed by 23:00 ET on 2026-11-15.

## Goals / Non-Goals

**Goals:** a stub researcher that follows the contract, idempotency and failure rules (D1); a plain-code orchestrate command that calls both workers over HTTP and writes report, trace and run history locally (D2, D4); `ORCHESTRATION.md` complete (D9).

**Non-Goals:** a real researcher (the tracker behind `/research`); changing the daily cron tracker or its workflow; deploying the researcher; any new dependency, table, column or migration; storing verdicts between orchestrate runs (every run verifies its developments again).

## Decisions

- **Reuse the client, don't copy it.** `verifying.Client` gets four fields with defaults that keep today's behaviour: `path="/verify"`, `worker="verifier"`, `response_model=VerifyResponse`, `caller="tracker"`. The trace's `endpoint_or_tool` becomes `f"{worker}:{path}"` and its `service` becomes `caller`. `_fits` and `_charge` become public (`fits`, `charge`). The researcher's settings use the same `VerifierSettings` model under `options.researcher`. Alternative (a second client) rejected: D2 asks for reuse.
- **Command in `backend/tracker/orchestrate.py`** (D2's `python -m tracker.orchestrate`). The run logic is one function `orchestrate(policy, secrets, last_top_k, transport=None, sleep=..., clock=...) -> Outcome` with no database access, so `tests_tracker/` can test it with `httpx.MockTransport` and no Postgres. `main()` does the database part with function-local imports of `app.config`, `app.db`, `app.models` and `app.publish_report.publish`, so importing `tracker` still never needs `DATABASE_URL`. Tested in `backend/tests/` against Postgres.
- **Run history in the existing tables** (D4). One `tracker_runs` row plus one `internship_offers` row per development, with the contract's fields mapped as the spec lists and the rest `unknown`/empty. No schema change. The run id is the wire `run_id` UUID, so one id follows a request across all three logs and the database.
- **Stale = newest earlier run with top-K offers.** A researcher-down run writes no offers, so the next lookup skips it without a flag column.
- **Stub timing.** `RESEARCHER_DELAY_MS` (default 100) per development gives the time-budget and duplicate-while-running cases something real to cut and overlap.
- **Local only.** The command refuses a non-local `DATABASE_URL`, enforcing D4 in code rather than by habit.

## Risks / Trade-offs

- [The researcher's share in `config.yaml` is the user's (D10, open)] → code and tests read `options.researcher` with test fixtures; only the `config.yaml` edit waits. Until then the command exits `1` on the real config.
- [Each run spends Groq through the deployed verifier, up to `max_requests` = 5 calls] → owner-only, local, `VERIFIER_TOKEN` required (D5). Whether an agent may run it for Q2/Q5 is D11 (open).
- [Posting URLs in `developments.json` can close] → checked at build time; a closed one shows up as `unreachable`, which is still a valid verdict.
- [`publish_report` docstring says it is the only writer of the tables] → the orchestrate command calls its `publish()`; the docstring is updated to name both callers.
