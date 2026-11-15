## Context

Today a run is one process. Vercel Cron calls `/api/internal/tracker-dispatch`, which starts `tracker.yml` on GitHub Actions. That runs `python -m tracker run` (500–1,000 s, mostly spent waiting on Groq's per-minute limit) and publishes the result to Postgres. Every check on the Curator's work (`save_record` → `unverified_fields`) runs in that same process, against text the Curator fetched.

What already exists and gets reused:
- `tracker/fetch.py` + `tracker/guard.py`: scheme, host and address checks, `getaddrinfo` resolution with the connection pinned to the checked address, redirects followed by hand and re-checked on every hop, timeouts and size caps.
- `curation.normalize` / `quote_found`: NFKC, ASCII quotes and dashes, lowercase, collapsed whitespace.
- `tracker/llm.py`: the Groq client, with 429 and `retry-after` handling.
- `tracker/untrusted.py`: the untrusted-data wrapper.

The constraints: it runs on Groq's free tier (8,000 tokens per minute per model), Vercel functions are limited to 300 s, the run lives on GitHub Actions, and the A2 deadline is 2026-11-08.

## Goals / Non-Goals

**Goals:**
- An independent second agent that sees only claim text and a URL, deployed separately and reached over authenticated HTTP.
- The model proposes a verdict, but code decides whether a claim is supported.
- The run survives a verifier that is slow, cold, down, duplicated or malformed.
- One shared package, so the guardrails and the normalizer aren't copied.

**Non-Goals:**
- Making the researcher (the pipeline) an HTTP service. A run takes longer than Vercel's function limit, so that needs an async design and is a later change.
- Splitting the Curator off into its own service.
- A shared idempotency store (Redis).
- Verifying the Editor's summaries, or opportunities outside the top K.

## Decisions

**1. The verifier is its own Vercel project at `services/verifier/`, not a route in `backend/`.** Both options use HTTP, but a backend route would share the process, the environment and the database URL. A separate project only has `VERIFIER_TOKEN` and `GROQ_API_KEY`, so a bug or an injected page can't reach any state. It's a FastAPI app, like the backend, so we keep one framework.

**2. The orchestrator is the existing GitHub Actions run, and Verify is a stage in `conductor.py`.** The tracker's run already owns state, budget and the report. Verify slots in after Rank as `verifying.py` in `usecases/internships/`, the same pattern as `assessing.py`. Afterwards Rank's scoring function is called again, which is cheap code. *Alternative:* a separate orchestrator process. Rejected, because it would have to duplicate the conductor's state and budget handling for no gain.

**3. A shared package, `packages/agentkit/`, as a uv path dependency.** These move out of `backend/tracker/`: `fetch.py`, `guard.py`, `untrusted.py`, `FetchSettings` (to `settings.py`), `parse_retry_after`, and `normalize`/`quote_found` (to `text.py`). `llm.py` stays in the tracker: it is built on the tracker's policy, retry and trace types, and the verifier needs one JSON-mode call, which it makes with `httpx` directly. The tracker's imports are updated, with no re-export shims left behind. Two new modules: `contract.py` (pydantic models for the request and response envelopes, shared by the client and the server) and `wire_log.py` (the cross-service JSON line). `trace.py` stays in the tracker: the verifier logs to stdout in the wire format. *Alternative:* copy the files into the verifier. Rejected, because two guardrail copies would drift apart.

**4. One request per opportunity, and one model call per request.** All of an opportunity's claims cite the same posting URL, so a request means one fetch (plus redirects) and one Groq call with the page text, truncated to `max_chars_for_model`, and up to 8 claims. That's at most K = 5 requests a day, each well under 60 s when there's no 429 to wait out. The model answers in JSON mode (`response_format: json_object`), and the answer is parsed with `contract.ModelVerdicts`. If it doesn't parse, one more call is made (`max_steps: 2`). If that fails too, those claims are left out and the response is `partial` with `model_output_invalid`.

**5. Claim text comes from templates in code, never from a model.** `verifying.claim_text(field, opportunity)` uses a fixed sentence per field. The quote stays at home on purpose: if the verifier got the Curator's quote, it could just search for it, and it would be re-checking the Curator's reading of the page rather than the claim.

**6. Verdict checks.** `verdict == "supported"` needs `len(evidence) <= 300` and `agentkit.text.found(evidence, page_text)`. `normalize` gains `html.unescape` as its first step. The tracker's quote checks benefit from that too, and they can't get stricter because of it. The normalization we add on top of the four required steps (ASCII quotes, dashes and no-break space) is documented in `docs/` and `ORCHESTRATION.md`. Evidence is matched against the extracted page text (`fetch.extract`), not the raw HTML. So an excerpt hidden in a script or a comment can't count, and HTML entities in the text are decoded once.

**7. Idempotency in memory.** The stored responses are a dict `request_id → (body_hash, state, response)`, with `state ∈ {running, done}`, behind a `threading.Lock`. A first copy marks the id `running` before any work starts. A duplicate with the same hash gets `503 Retry-After: 5` while it runs and the stored response once it's done. A different hash gets `409`. Failures (`503` and `500`) remove the entry, so a retry can run. Vercel Fluid Compute often reuses an instance, but that isn't guaranteed. A retry that lands on a new instance re-verifies, which costs one fetch and one call and is otherwise safe, because the tracker stores verdicts per `request_id` only once. The entries are capped (LRU, 1,000), with the ceiling marked as a `ponytail:` comment.

**8. Client retries.** `httpx` with `timeout = time_budget_ms + cold_start_ms` (15 s by default; a Vercel Python cold start is a few seconds, and the cap leaves room). Up to `max_attempts: 4`, with backoff `min(2^attempt, 30) s ± 20 %` or `Retry-After` if it's longer. The body is serialized once and resent byte for byte. A `401` stops the stage for the rest of the run, because every later request would fail too.

**9. Budget.** `config.yaml` gains:
```yaml
verifier:
  url_env: VERIFIER_URL
  max_requests: 5
  time_budget_ms: 60000
  budget: { max_steps: 2, max_fetches: 6, max_tokens: 12000 }
  cold_start_ms: 15000
  max_attempts: 4
```
Policy validation checks that `max_requests × budget` fits within the run's remaining totals. A request with no valid answer is charged its full share, and a stored copy is counted once, keyed by `request_id`.

**10. Storage.** In the tracker's SQLite state: `claim_verdicts(opportunity_id, field, record_hash, verdict, evidence, run_id, request_id, checked_at)`, with primary key `(opportunity_id, field, record_hash)`. The run's failed services go on the run row. Postgres gets `internship_offers.claims` (JSONB) and `tracker_runs.failed_services` (`text[]`). A JSON column per offer is enough, because claims are only ever read together with their offer. *Alternative:* an `offer_claims` table. Rejected, because nothing queries claims on their own.

**11. Docs and diagrams.** `docs/agent-loop.md` (the run flowchart gains Verify and a dashed HTTP edge to the "Verifier (Vercel)" node, with the `unverified` fallback), the pipeline line and decision table in `AGENT.md`, `docs/architecture.md` (services, the shared package, tokens), `docs/deployment.md` (the second Vercel project and secrets), `docs/api.md` (`/verify` and offer claims), `docs/tracker.md`, `README.md` and `.env.example`.

## Risks / Trade-offs

- **[A posting page renders its text with JavaScript, as Ashby pages do]** → Checked on 2026-11-01: `extract` got 31 characters from an Ashby page (just the title), against 7,359 from Greenhouse and 4,905 from Lever. But Ashby pages embed the posting as a schema.org `JobPosting` JSON-LD block, so `extract` now appends a `JobPosting` description (and nothing else from scripts): 4,210 characters on the same page. Every source keeps citing its real posting URL, and the evidence is still text from the fetched page.
- **[Vercel can't install the `../../packages/agentkit` path dependency]** → Mitigation: Vercel's "Include files outside the root directory" setting, which is on by default for monorepos. If that fails, a build step copies `agentkit` into `services/verifier/` before install.
- **[Groq per-minute limits shared with the Curator]** → Verify runs after Curate, so the 20b window has usually recovered by then. A `503` from the verifier carries Groq's `retry-after`, and the client honors it.
- **[Stored responses lost when an instance changes]** → Accepted. The cost is one repeated fetch and call. It's documented in `ORCHESTRATION.md`.
- **[A false `unsupported` costs a real opportunity points]** → It only turns one criterion into `unknown` (0.5), never removes the opportunity, and the report shows the claim so a person can see it.
- **[Injected page text]** → A page can't make a claim `supported` without an excerpt that is really on that page. It can still push the model toward `unsupported`. The only effect is a 0.5 on one criterion, which is visible in the report.

## Migration Plan

1. Land `agentkit` with the tracker's imports moved over. The tests must pass unchanged.
2. Deploy `services/verifier` as a new Vercel project. Set `VERIFIER_TOKEN` and `GROQ_API_KEY` there, and `VERIFIER_URL` and `VERIFIER_TOKEN` as GitHub Actions secrets.
3. Run the Alembic migration. Existing rows get `claims = []` and `failed_services = []`.
4. Enable `verifier` in `config.yaml`.

Rollback: remove `options.verifier` from `config.yaml`. Ranking and the report behave as before, and claims show `unverified`.

## Open Questions

None. The Ashby question is settled (see Risks).
