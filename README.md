# mobile-systems-assignment

User accounts for the Mobile Systems coursework at NYU: register, log in with a username, and manage your account.

- **`backend/`**: JSON API in Python (FastAPI, SQLAlchemy, Alembic, PostgreSQL)
- **`frontend/`**: single-page app (Vite, React, Tailwind CSS, shadcn/ui) that calls the backend over HTTP
- **`backend/tracker/`**: agentic tracker (Assignment 1B) that finds and ranks the top developments on a topic, with its policy in [`config.yaml`](config.yaml)

## Quick start

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) with Compose v2, **running**
- Python 3.12+ and [uv](https://docs.astral.sh/uv/)
- [Node.js](https://nodejs.org/) 20.19+ (22 or 24 recommended) and npm
- A bash shell (macOS/Linux, or WSL / Git Bash on Windows)

### Run it

```bash
./scripts/start.sh
```

This creates the `.env` files from their examples, installs dependencies, starts Postgres, applies migrations, creates the test account, and starts both apps:

| What | URL |
| --- | --- |
| Frontend | <http://localhost:5173> |
| Backend | <http://localhost:8000> |
| API docs (Swagger UI) | <http://localhost:8000/docs> |

Ctrl-C stops both servers. The database keeps running; stop it with `./scripts/db-down.sh` (add `--reset` to delete its data).

### Test account

| Username | Password |
| --- | --- |
| `NYUgrader` | `Courant2026!` |

### Troubleshooting

- **"Docker is not running"**: start Docker Desktop (or the Docker daemon) and run the script again.
- **Port 5432 is taken** (e.g. by a local Postgres): set `POSTGRES_PORT=5433` in `.env` and the same port in `DATABASE_URL` in `backend/.env`, then `./scripts/db-down.sh && ./scripts/start.sh`.
- **Port 8000 or 5173 is taken**: stop whatever is using it; both dev servers use fixed ports.

## Tracker

Hand-written agents that track Summer 2027 software and ML internships at NYC startups: a Scout finds job boards, code reads them, a Curator turns postings into quote-verified records, code decides what is still open and ranks it, and an Editor writes short summaries. Each run writes a cumulative report (New since last run, Still in top K, Dropped, Also open) to `reports/`, with a trace in `traces/`. It needs only Python, uv and two free API keys, no Docker or Postgres.

```bash
cd backend
uv sync
cp .env.example .env                  # then set GROQ_API_KEY and TAVILY_API_KEY
uv run python -m tracker run          # exit 0 complete, 2 partial, 3 failed
uv run python -m tracker run --config ../examples/single-agent.yaml   # the single-agent tracker
```

Each tool also runs without the model:

```bash
uv run python -m tracker.tools search_web "open-source robotics foundation model"
uv run python -m tracker.tools fetch_article https://example.com/
uv run python -m tracker.tools finish report.json
```

The topic, agents, models, tools, budgets, watchlist and allowed hosts are all in [`config.yaml`](config.yaml). See [docs/tracker.md](docs/tracker.md) for the policy fields, budgets, failure handling, fetch guardrails, state and trace format.

## Documentation

| Doc | Contents |
| --- | --- |
| [docs/development.md](docs/development.md) | Individual scripts, running without the scripts, configuration, checks, changing the schema or the API, project layout, OpenSpec |
| [docs/api.md](docs/api.md) | Endpoints, request/response conventions, error format, web UI routes |
| [docs/architecture.md](docs/architecture.md) | Two-origin setup, CORS, token handling, CSP, and the security decisions |
| [docs/deployment.md](docs/deployment.md) | Production on Vercel and Neon, production migrations, CI |
| [docs/tracker.md](docs/tracker.md) | The agentic tracker: setup, policy, budgets, failure handling, guardrails, state and traces |
| [docs/agent-loop.md](docs/agent-loop.md) | What the tracker does each run, as one flow, then how the agent loop works: model calls, tool dispatch, budgets, finishing and partial reports |

This project uses [OpenSpec](https://github.com/Fission-AI/OpenSpec) for spec-driven development: approved specs are in `openspec/specs/`, proposed changes in `openspec/changes/`.
