"""Database engine and session factory."""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    return create_engine(settings.database_url, echo=settings.sql_echo, pool_pre_ping=True)


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def session_factory_dependency() -> sessionmaker[Session]:
    """Background jobs open their own sessions (the request's session closes when the response is sent).
    A dependency so tests can swap in their own database."""
    return get_session_factory()


def get_db() -> Iterator[Session]:
    """One session per request (used as a FastAPI dependency later)."""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()
