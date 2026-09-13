"""Engine and session management.

Synchronous SQLAlchemy on purpose. The workload is ingestion batches and
dashboard reads, both of which are short and Postgres-bound; async would buy
nothing here and costs a materially harder debugging story. FastAPI runs sync
endpoints in a threadpool, which is the right trade at this scale.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from bsa.core.config import get_settings


@lru_cache
def get_engine(database_url: str | None = None) -> Engine:
    settings = get_settings()
    return create_engine(
        database_url or settings.database_url,
        echo=settings.db_echo,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        future=True,
    )


@lru_cache
def get_session_factory(database_url: str | None = None) -> sessionmaker[Session]:
    return sessionmaker(
        bind=get_engine(database_url),
        expire_on_commit=False,
        autoflush=False,
        future=True,
    )


@contextmanager
def session_scope(database_url: str | None = None) -> Iterator[Session]:
    """Transaction boundary for scripts and background jobs.

    Commits on success, rolls back on any exception. Ingestion relies on this:
    a failed import must leave no half-written session behind.
    """
    session = get_session_factory(database_url)()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Iterator[Session]:
    """FastAPI dependency. Read path -- routes do not commit implicitly."""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()
