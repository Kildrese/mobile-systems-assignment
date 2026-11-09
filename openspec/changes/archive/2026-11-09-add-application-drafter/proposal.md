# Proposal

## Why

The tracker finds and checks internships, but every application still starts with tailoring the CV by hand in Word. The tailoring follows rules Kilian has already written down (`rules.md`), from facts he has already collected (`fact_bank.yaml`), on a CV whose layout doesn't change (`cv.docx`). That is work an agent can do, as long as code makes sure it never invents a fact, changes the layout or runs past one page.

## What Changes

- **Applicant profile in the app.** A signed-in user uploads four files on `/account`: the master `cv.docx`, `fact_bank.yaml`, `rules.md` (prose rules for the model) and `checks.yaml` (the rules code enforces: banned words, scope words, the cut order, the role-type table, ids never used on a CV). They are stored per user in Postgres. Only the owner can read or replace them. Locally, the drafter reads the same files from the git-ignored `private/applicant/`.
- **A drafter service**, `services/drafter`, built like the verifier: its own Vercel project and `DRAFTER_TOKEN`, the same request envelope, idempotency by `request_id`, budgets and partial results. It receives the posting URL and the applicant's files, fetches the posting itself through the shared guardrails, and asks Claude Sonnet 5.5 (Anthropic API) for a structured plan: the role type, the bullets per entry (each citing its fact-bank id, possibly reworded), the skills order, and, when asked, a cover letter. The model never writes the `.docx`: code builds it from a copy of the master.
- **Code checks every draft:**
  - only `approved` fact-bank bullets that are allowed on a CV;
  - a reworded bullet keeps its source's numbers, dates and names, at least 60 % of its words, at most 115 % of its length, and adds no scope word; otherwise the source wording is used;
  - no banned word, Germanism or em dash; no bullet moved to another entry; header rows, Education and the Languages line never change;
  - one page, by a line budget calibrated on the master (a bullet of up to 105 characters is one line, up to 210 two). If it's over, code applies the cut order until it fits;
  - a cover letter mentions no fact outside the fact bank and the posting, and none of visa, CPT, F-1, sponsorship, salary or a client name.
- **Layout moves follow the rules table.** The model picks a role type, and code applies `checks.yaml`'s order of ipt sub-projects, skills and sections for that type; an unknown type gets the SWE order.
- **Drafts are made automatically and on demand.** After each daily publish, each new top-K offer gets a CV for every user with a profile, unless its deadline has passed. The cover letter is drafted only when the posting asks for one. A "Draft application" button on any offer drafts for the signed-in owner, with an option to include a letter. Only the latest draft per user and offer is kept.
- **Only allowlisted users can spend model tokens.** `DRAFTING_USERS=kiliandresse` in the backend's environment decides who may upload a profile or start a draft (anyone else gets `403`), the daily step drafts only for those users, and a cap of 20 drafts per user per UTC day applies before the drafter is called.
- **Downloads and sharing.** Drafts (tailored `.docx`, cover letter as `.docx` and plain text) download from the offer card. An owner can share read-only access to their drafts with another user; `kiliandresse` shares with `nyugrader`. A viewer never sees the master CV, the fact bank or the rules, and can't start a draft.

## Capabilities

### New Capabilities
- `applicant-profile`: uploading, validating, storing and reading the four profile files; owner-only access; sharing drafts read-only.
- `application-drafter`: the drafter service's contract, auth, idempotency, budgets, the model's plan, every code check, the line budget and the cut order, and how the `.docx` is built.
- `application-drafts`: when drafts are made (after publish, and on demand), deadlines, storage of the latest draft, the API, and the offer card's downloads.

### Modified Capabilities
- `report-publishing`: the daily workflow runs the draft step after publishing.

## Impact

- **New code:** `services/drafter/` (FastAPI, `anthropic`, `python-docx`, `pyyaml`; its own `vercel.json`, CI job and Vercel project, connected to git like the verifier). `backend/app/drafts.py` (the client, the after-publish step `python -m app.draft_new`).
- **Backend:** an Alembic migration adding `applicant_profiles` and `application_drafts`; routes under `/api/profile` and `/api/drafts`; `models.py`, `schemas.py`, the regenerated OpenAPI document.
- **Frontend:** a profile section on `/account`; download buttons and "Draft application" on offer cards; the regenerated client.
- **Shared package:** `agentkit.contract` gains the drafter's request and response models.
- **Deploy and secrets:** a `mobile-systems-drafter` Vercel project with `DRAFTER_TOKEN` and `ANTHROPIC_API_KEY`. `DRAFTER_URL` and `DRAFTER_TOKEN` on the backend project and in GitHub Actions. Every new variable goes in `.env.example`.
- **Cost:** about one Sonnet 5.5 call per draft, a handful per day, under the hard spend cap set in the Anthropic console.
- **Privacy:** personal files only in Postgres behind the owner's login, and in the git-ignored `private/` folder. Never in the repo, the trace or a log.
- **Out of scope:** autofilling application forms; any CV layout other than this master's; summary lines on the CV (the rules forbid them).
