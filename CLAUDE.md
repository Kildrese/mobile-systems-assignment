# CLAUDE.md

FastAPI backend (`backend/app`), agentic tracker (`backend/tracker`), verifier and CV/cover-letter drafter services (`services/verifier`, `services/drafter`), Vite/React frontend (`frontend`). Deployed on Vercel with Neon Postgres. Setup and layout: [docs/development.md](docs/development.md). The tracker's design: [AGENT.md](AGENT.md).

## Commands (the same ones CI runs, see `.github/workflows/ci.yml`)

```bash
# backend/ and services/*/
uv run ruff check && uv run ruff format --check
uv run pytest                     # backend: needs Postgres (./scripts/db-up.sh); services: none
uv run pytest tests_tracker       # backend/: tracker, no Postgres, no network
uv run python -m app.openapi --check
uv run alembic check              # needs Postgres
# frontend/
npm run api:check && npm run typecheck && npm test && npm run lint
```

## Workflow

1. Features start as an OpenSpec change (`/opsx:propose`) after a grilling round; no code before it's reviewed. Small fixes skip this.
2. Work on a feature branch (or worktree), never on `master`. PR against `master`; titles say what changed in plain words ("Read the SimplifyJobs list as an internship source").
3. Before the PR: the `checker` agent runs CI's commands, then the `reviewer` (correctness vs. the OpenSpec change, plus over-engineering) and, when the diff touches auth, prompts, fetching, secrets or paid API calls, the `security-reviewer`.
4. Shipping is `/ship <PR>` in the main session, never a subagent: migration order, secrets, merge, post-deploy checks. Production migrations, GitHub secrets and the merge are the user's steps.
5. After it's live: `/opsx:archive`.

## Gotchas

- The repo is **public**. Never commit `private/`, `.env*` (except `.env.example`), or anything from them. A hook blocks it.
- After changing `backend/app/schemas.py` or `backend/app/routers/`: `uv run python -m app.openapi` in `backend/`, then `npm run api:generate` in `frontend/`. Never edit `frontend/src/api/` by hand.
- Model change = a new Alembic migration (`uv run alembic revision --autogenerate`). Never edit a migration that has run in production.
- `reports/` and `traces/` are ignored except run1/run2. Production runs reach the database only via the daily cron, never via an API a user can call.
- Anything that spends on a paid API (Groq, Tavily, Anthropic) must say who can trigger it.
- CI tests fake every provider; tests must not need network or secrets.
