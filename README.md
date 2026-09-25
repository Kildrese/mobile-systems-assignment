# mobile-systems-assignment

User accounts for the Mobile Systems coursework at NYU: register, log in with a username, and manage your account.

- **`backend/`**: JSON API in Python (FastAPI, SQLAlchemy, Alembic, PostgreSQL)
- **`frontend/`**: single-page app (Vite, React, Tailwind CSS, shadcn/ui) that calls the backend over HTTP

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

## Documentation

| Doc | Contents |
| --- | --- |
| [docs/development.md](docs/development.md) | Individual scripts, running without the scripts, configuration, checks, changing the schema or the API, project layout, OpenSpec |
| [docs/api.md](docs/api.md) | Endpoints, request/response conventions, error format, web UI routes |
| [docs/architecture.md](docs/architecture.md) | Two-origin setup, CORS, token handling, CSP, and the security decisions |
| [docs/deployment.md](docs/deployment.md) | Production on Vercel and Neon, production migrations, CI |

This project uses [OpenSpec](https://github.com/Fission-AI/OpenSpec) for spec-driven development: approved specs are in `openspec/specs/`, proposed changes in `openspec/changes/`.
