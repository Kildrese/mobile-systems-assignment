# Tasks

## 1. Shared package (design D3)

- [x] 1.1 Create `packages/agentkit/` (uv package) and move `fetch.py`, `guard.py`, `untrusted.py`, `FetchSettings` (to `settings.py`), `parse_retry_after`, and `normalize`/`quote_found` from `curation.py` into `agentkit/text.py`. Add `agentkit` to `backend/pyproject.toml` as a path dependency, update every import, and leave no re-export shims behind. Tests stay in `tests_tracker/` so CI keeps running them. The tracker's test suite must pass unchanged
- [x] 1.2 Add `html.unescape` as the first step of `normalize`; evidence uses `quote_found`. Test "Entity and whitespace differences", and that every existing quote test still passes
- [x] 1.3 Add `agentkit/contract.py`: pydantic models for the request envelope, the claims payload, the response envelope, verdicts, usage, error and `ModelVerdicts`, with `extra="forbid"` and the limits from the "Request envelope" requirement, plus `body_hash()` (SHA-256 of sorted-key, compact JSON). Tests: reordered keys give the same hash, and duplicate claim ids are rejected
- [x] 1.4 Add `agentkit/wire_log.py`: `log_line(**fields)` returns the cross-service JSON object with the 11 fields and drops any `authorization`/`token` key. Test that a secret value never appears

## 2. Verifier service (claim-verification)

- [x] 2.1 Create `services/verifier/` (FastAPI, `pyproject.toml` depending on `agentkit`, `vercel.json`) with `GET /healthz`, and a bearer check that runs before body parsing and fails at startup without `VERIFIER_TOKEN`. Tests: "Health check", "No token", "Wrong token"
- [x] 2.2 Validate requests with `contract` and return `400` with field names. Tests: "Missing claims", "Duplicate claim ids"
- [x] 2.3 Fetch each distinct URL once through `agentkit.fetch` with `allowed_hosts: ["*"]`; a blocked URL or a failed fetch makes its claims `unreachable`. Tests with a fake resolver/transport: "Metadata address", "Localhost", "Redirect to a private address", "Shared URL"
- [x] 2.4 Make one Groq JSON-mode call per URL (page text wrapped as untrusted, claims as untrusted data), with one retry on unparseable output, then the code checks in design D6. Tests with a scripted model: "Excerpt not on the page", "Excerpt too long", "Instruction in a claim", and that the model can't return `unreachable`
- [x] 2.5 Enforce the budget and deadline: stop before the next fetch or call that would exceed it, return `partial` with `error`, and report actual `usage`. Test "Tiny time budget"
- [x] 2.6 Map provider failures: per-minute 429 → `503` with `Retry-After`; 401 or daily quota → `500` `failed`. Tests "Groq per-minute limit", "Bad model key"
- [x] 2.7 Add the in-memory idempotency store (design D7). Tests: "Same request twice" (assert zero new fetches and model calls), "Same id, reordered keys", "Same id, different body", "Duplicate while running" (a blocked first request in a thread)
- [x] 2.8 Write a log line to stdout for each request in and each fetch or model call out. Tests "Following a request" and "Token never logged"

## 3. Verify stage in the tracker (internship-pipeline, trace-log)

- [x] 3.1 Settle the Ashby open question: fetch one live posting each from Greenhouse, Lever and Ashby with `agentkit.fetch.extract`. Ashby came back empty, so `extract` now keeps a JSON-LD `JobPosting` description (results in `design.md`)
- [x] 3.2 Add the `verifier` config section (design D9) as `options.verifier` in `config.yaml`, with the check that `max_requests × budget` fits the run's totals. Add `VERIFIER_URL` and `VERIFIER_TOKEN` to `.env.example` and the trace's redaction list
- [x] 3.3 Add the `claim_verdicts` table and the run's failed services to the store as the next migration, with `put_verdicts()`, `verdicts(opportunity_id, record_hash)` and `needs_verify(top_k)`. Test that `unreachable` is retried and that a changed record hash is re-sent
- [x] 3.4 Write `usecases/internships/verifying.py`: `claim_text(field, opp)` templates and `claims_for(opp)`. Tests "Unknown pay", "Quote stays home"
- [x] 3.5 Write the client: a single serialized body, timeout `time_budget_ms + cold_start_ms`, retries per design D8, response validation that includes claim ids, `service` trace events, and budget charging. Tests with `httpx.MockTransport`: "Timeout then stored copy", "Unknown claim id", "Unauthorized", "Never answered", "Retry after cold start"
- [x] 3.6 Add `VerifyStage` to `wiring.py` after Rank; it stores verdicts, re-ranks, and marks the run partial with `verifier` failed when needed. Tests "No verifier configured" and "Verifier down" (exits `2`), plus a pipeline test where the second run sends no requests for unchanged records ("Unchanged record")

## 4. Ranking and report (opportunity-report)

- [x] 4.1 In `ranking.score()`, count an `unsupported` field as unknown. Tests "Unsupported term", "Unreachable page", and that scores are unchanged with no verdicts
- [x] 4.2 In `report.py`, list claims with labels and quoted evidence for top-K entries, and name the failed service in the header. Tests "Supported claim", "Verifier down"

## 5. Publishing and page (report-publishing, internship-report-view)

- [x] 5.1 Add an Alembic migration for `internship_offers.claims` (JSONB, default `[]`) and `tracker_runs.failed_services` (`text[]`, default `{}`), and update `models.py`, `schemas.py` and `publish_report.py`. Tests "Claims published", "Verifier failed", "Runs published before this change"
- [x] 5.2 Regenerate `openapi/openapi.json` and the frontend client
- [x] 5.3 Show claim labels and evidence (as text) on top-K cards in `components/internships/report.tsx`. The frontend has no component-test setup, so "Claims shown" and "Markup in evidence" are checked by hand; React renders both as text, with no `dangerouslySetInnerHTML`
- [x] 5.4 Show Partial and the failed services in `components/internships/history.tsx`. Test "Verifier failed"

## 6. Docs and diagrams

- [x] 6.1 `docs/agent-loop.md`: add Verify to the run flowchart, with a dashed HTTP edge to a "Verifier (Vercel)" node and the `unverified` fallback edge
- [x] 6.2 `AGENT.md`: update the pipeline line and the "Decided by the model / by code" table (the verifier proposes verdicts; code decides supported, unreachable, ranking impact and retries)
- [x] 6.3 `docs/architecture.md` (services, `agentkit`, per-service tokens), `docs/deployment.md` (the second Vercel project, its environment and the GitHub secrets), `docs/api.md` (`/verify`, offer `claims`, run `failed_services`), `docs/tracker.md` (Verify stage and config), `README.md`

## 7. Deploy and rollout

- [x] 7.1 Create the verifier's Vercel project (root `services/verifier`), set `VERIFIER_TOKEN` and `GROQ_API_KEY`, deploy, and check `/healthz` plus the A2 test table against the deployed URL (401, 400, duplicate, 409, 503, metadata URL, tiny budget)
- [x] 7.2 Add the `VERIFIER_URL` and `VERIFIER_TOKEN` GitHub Actions secrets and pass them in `tracker.yml`
- [x] 7.3 Before merging, apply the migration to production with `./scripts/db-migrate-neon.sh`
