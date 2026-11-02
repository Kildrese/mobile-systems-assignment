# Tasks

## 1. Profile rules as data (design D5)

- [x] 1.1 Write `private/applicant/checks.yaml` from `rules.md` and `cv_structure.md`: `banned_words`, `scope_words`, `client_names`, `never_on_cv`, `never_cut`, `bullet_bounds`, `cut_order`, `role_types`. Show Kilian every line taken from an "[advised]" or "[unknown]" rule before it's used
- [x] 1.2 Commit a fictional profile under `services/drafter/tests/fixtures/` (a CV with the same layout as the master, a small fact bank, rules, checks), so tests and CI never need the real files

## 2. Shared contract

- [x] 2.1 Add `DraftPayload`, `DraftRequest`, `DraftResult`, `DraftResponse` and `CheckRecord` to `agentkit/contract.py`, with size limits (CV ≤ 2 MB base64, text files ≤ 200 KB). Tests for the limits and a valid round trip

## 3. Drafter service (application-drafter)

- [x] 3.1 Scaffold `services/drafter/` like the verifier (FastAPI, `pyproject.toml` with `agentkit`, `anthropic`, `python-docx`, `pyyaml`; a CI job). Move the verifier's token check, request store and log wrapper into `agentkit/service.py` so both services use the same code. Tests: 401 before 400, same request twice, 409, 503 while running
- [x] 3.2 `agentkit/cv/layout.py`: parse the master into its blocks (design D3), normalize row r5, clone and replace bullets, move sub-project groups and sections, rewrite the skills lines, and serialize. Tests on the fixture: rebuilding the master's own plan gives the same text in every paragraph, and fonts, margins, hyperlinks and `customXml` are unchanged
- [x] 3.3 `budget.py`: `lines(doc)` and the cut order (design D4). Tests: "Master fits" (the master's count is pinned), "Two long bullets", the never-cut ids survive, and `does_not_fit`
- [x] 3.4 `agentkit/cv/profile.py` (fact-bank and `checks.yaml` parsing) and `services/drafter/checks.py`: bullet and letter checks (design D7). Table tests: "Scope upgrade", "Invented number", "Unapproved bullet", "Never on a CV", banned word, em dash, merging two items, "Visa in the letter", letter word count
- [x] 3.5 `plan.py`: the Anthropic call (forced tool use, the cached profile prefix, the posting as untrusted data), the letter call and its one retry, mapping 429/401/budget errors to 503/500. Tests with a scripted client: "ML role", "Unknown role type", "Posting asks for the CV to change", "CV only", "Anthropic rate limit"
- [x] 3.6 `main.py`: `/healthz` and `/draft` wired to fetch → plan → checks → layout → budget, with budgets, a partial result on `posting_unreachable` and `does_not_fit`, and log lines. An end-to-end test on the fixture with a scripted model

## 4. Backend (applicant-profile, application-drafts)

- [ ] 4.1 An Alembic migration for `applicant_profiles` and `application_drafts` (design D8), plus models and schemas
- [ ] 4.2 `DRAFTING_USERS` and the daily cap as one dependency used by upload, `POST /api/drafts` and `draft_new`. Tests: "Not allowlisted", "Daily cap", "Unset allowlist"
- [ ] 4.3 `/api/profile`: upload (multipart, all four files or nothing), validation with `agentkit.cv` (the same parsers the drafter uses), and `GET` for the owner. Tests: "First upload", "Partial upload", "Duplicate fact id", "Unknown CV layout", "Another user"
- [ ] 4.4 `app/drafts.py`: the drafter client (retries like the verifier client) and `POST /api/drafts`, `GET /api/drafts`, the three downloads. Tests with a fake drafter: "Draft again", "No profile", a concurrent click gets 409, "Owner downloads", "Stranger", "nyugrader reads a draft", "Not shared"
- [ ] 4.5 `python -m app.draft_new` (reads the published run and the tracker state's posting text) and `python -m app.share_drafts`. Tests: "New top-K offer", "Past deadline", "Drafter down", and the cover-letter trigger
- [ ] 4.6 Regenerate `openapi/openapi.json`

## 5. Frontend

- [ ] 5.1 A profile section on `/account`: four file pickers, upload, and the stored files' names, sizes and time
- [ ] 5.2 The offer card: the draft status, downloads, "Copy letter text", "Checks", "Draft application"/"Draft again" with "Include cover letter", "Deadline passed" and "made with an older profile". Regenerate the client

## 6. Workflow, docs, deploy

- [ ] 6.1 `tracker.yml`: a `draft_new` step after publishing, with `continue-on-error`, and `DRAFTER_URL` and `DRAFTER_TOKEN` passed in. Add every new variable to `.env.example`
- [ ] 6.2 Docs: `docs/architecture.md` (the drafter, where personal data lives, sharing), `docs/api.md` (profile and drafts routes, tables), `docs/deployment.md` (the drafter project and secrets), `docs/agent-loop.md` (a drafter node in the flowchart), `README.md`
- [ ] 6.3 Deploy: create `mobile-systems-drafter` (root `services/drafter`, connected to git), set `DRAFTER_TOKEN` and `ANTHROPIC_API_KEY` (Kilian adds the key himself), set `DRAFTER_URL`, `DRAFTER_TOKEN` and `DRAFTING_USERS=kiliandresse` on the backend project and `DRAFTER_URL`, `DRAFTER_TOKEN` and `DRAFTING_USERS` in GitHub, and run the migration on Neon
- [ ] 6.4 Kilian uploads his profile, run `python -m app.share_drafts kiliandresse nyugrader` against production, draft one real offer, and check the `.docx` in Word: one page, layout unchanged
