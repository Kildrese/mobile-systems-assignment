"""Settings from environment variables, loaded from `backend/.env` if present."""

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import ValidationError, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

    database_url: str
    # The direct (unpooled) URL, used by migrations when set. Neon's pooled
    # endpoint runs PgBouncer in transaction mode, which DDL shouldn't go through.
    database_url_unpooled: str | None = None
    # Comma-separated in the environment, e.g. `http://localhost:5173,https://app.example`.
    cors_origins: Annotated[list[str], NoDecode] = []
    session_ttl_days: int = 7
    # The daily tracker dispatch (`app/routers/internal.py`). Vercel Cron sends
    # `CRON_SECRET` as a bearer token; unset, the route answers 404 to everyone.
    cron_secret: str | None = None
    # A fine-grained GitHub token: this repository only, Actions read and write.
    github_dispatch_token: str | None = None

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip().rstrip("/") for origin in value.split(",") if origin.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    try:
        return Settings()
    except ValidationError as err:
        missing = [str(e["loc"][0]).upper() for e in err.errors() if e["type"] == "missing"]
        if missing:
            raise SystemExit(
                f"{', '.join(missing)} is missing. Copy backend/.env.example to backend/.env "
                "or set it in the environment."
            ) from None
        raise
