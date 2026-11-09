# Proposal

## Why

The tracker checks its own work, but only from the inside. `save_record` rejects a field whose quote isn't in the posting, but the check runs inside the Curator's pipeline, against text the Curator fetched, in the same process that holds every table. A page that fools the Curator, or a bug in how a posting's text is stored, goes through unchecked. A second agent that gets only the claim and its URL, fetches the page itself and is checked by code catches that. It is also the first time two of our agents talk over a network, so timeouts, retries, duplicates and a worker that's down all have to be handled for real (Assignment 2).

## What Changes

- **A verifier service**, deployed as its own Vercel project. `POST /verify` takes claims (`claim_id`, `text`, `source_url`) in a request envelope (`request_id`, `run_id`, `time_budget_ms`, `budget`). It fetches each source itself, asks a model for an excerpt that supports each claim, and returns `supported`, `unsupported` or `unreachable` for each one. Code, not the model, confirms that the excerpt is on the fetched page. Requests need `Authorization: Bearer $VERIFIER_TOKEN`. The service is idempotent by `request_id`, returns `409` for a reused id with a different body and `503` with `Retry-After` while the same id is still in progress, and stops with a partial result when its budget runs out. It has no database.
- **A shared package, `packages/agentkit`**, holds what both sides use: the envelope and contract schemas, the fetch guardrails (`fetch.py`, `guard.py`), the quote normalizer, the Groq client and the cross-service log line. The tracker and the verifier both depend on it, so neither imports the other's code.
- **A Verify stage in the tracker**, after Rank. The tracker's run, still on GitHub Actions, acts as orchestrator. It turns each known field of a top-K opportunity into one claim sentence, citing the posting URL. It sends one `/verify` request per opportunity, with retries and backoff that honor `Retry-After`, and charges the verifier's usage against the run budget. Verdicts are stored per opportunity and reused until the record changes. Then Rank scores again.
- **Verdicts change the score a little.** An `unsupported` field counts as `unknown` in ranking. `unreachable` and `unverified` (the verifier was down or out of budget) change nothing.
- **A verifier that's down never fails the run.** Its claims show as `unverified`, and the run is marked partial and names the verifier.
- **The report, the published rows and `/internships`** show each claim's label (supported, unsupported, unreachable or unverified) and, for supported claims, the evidence excerpt as plain text. Run history shows which service failed.
- **Docs and diagrams**: the run flowchart in `docs/agent-loop.md`, the pipeline line and decision table in `AGENT.md`, plus `docs/architecture.md`, `docs/deployment.md`, `docs/api.md` and `docs/tracker.md`.

## Capabilities

### New Capabilities
- `claim-verification`: the verifier service's contract, auth, request and response validation, idempotency, budget and deadline, how verdicts are reached and checked by code, its fetch rules and its log lines.

### Modified Capabilities
- `internship-pipeline`: the stage order gains Verify, and a verifier failure becomes a degraded run, not a failed one.
- `opportunity-report`: "Ranking in code" counts unsupported fields as unknown, and the report shows verdicts and evidence.
- `report-publishing`: each published offer carries its claims and verdicts, and each run carries the services that failed.
- `internship-report-view`: the page shows claim labels and evidence, and run history shows the failed service.
- `trace-log`: cross-service calls are logged with `request_id`, `attempt`, `direction` and caller-side latency, so a request can be followed across both services.

## Impact

- **New code:** `packages/agentkit/` (moved from `backend/tracker/`: `fetch.py`, `guard.py`, `llm.py`, and the normalizer from `curation.py`; plus a new `contract.py` and `wire_log.py`). `services/verifier/` (a FastAPI app, its tests and its `vercel.json`).
- **Tracker:** a new `usecases/internships/verifying.py` (claims, client, stage), `store.py` (a `claim_verdicts` table and a migration), `ranking.py`, `report.py`, `wiring.py`, `config.py`/`config.yaml` (a `verifier` section with URL, budget share and timeouts). Imports of the moved modules change.
- **Backend:** an Alembic migration (`internship_offers.claims` JSONB, `tracker_runs.failed_services`), `models.py`, `schemas.py`, `publish_report.py`, the regenerated OpenAPI document.
- **Frontend:** the offer card and run history, and the regenerated client.
- **Deploy:** a second Vercel project for `services/verifier` with `VERIFIER_TOKEN` and `GROQ_API_KEY`. `VERIFIER_URL` and `VERIFIER_TOKEN` become GitHub Actions secrets. Every new variable goes in `.env.example`.
- **Cost:** about one Groq `gpt-oss-20b` call and one page fetch per top-K opportunity whose record changed. On most days that's 0–5 calls.
- **Out of scope:** making the researcher (the pipeline) an HTTP service, splitting the Curator into its own service, a shared idempotency store such as Redis, and the CV drafter.
