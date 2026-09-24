"""The database engine (one pool per process) and the per-request session."""

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings


def sqlalchemy_url(url: str) -> str:
    """Point `postgres://` and `postgresql://` URLs at the psycopg 3 driver."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url.removeprefix(prefix)
    return url


@lru_cache
def get_engine() -> Engine:
    return create_engine(
        sqlalchemy_url(get_settings().database_url),
        # Neon's pooled endpoint (PgBouncer, transaction mode) can't keep
        # server-side prepared statements across transactions.
        connect_args={"prepare_threshold": None},
        pool_size=5,
        pool_pre_ping=True,
    )


@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def get_db() -> Iterator[Session]:
    with get_sessionmaker()() as db:
        yield db
