"""Engine, session factory, and schema lifecycle."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def _configure_sqlite(dbapi_connection: Any, _record: Any) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


def build_engine(database_url: str | None = None) -> Engine:
    url = database_url or get_settings().database_url
    if url.startswith("sqlite:///"):
        db_path = Path(url.removeprefix("sqlite:///"))
        if not db_path.is_absolute():
            raise ValueError(
                "Use an absolute path in ALYA_DATABASE_URL; relative sqlite paths "
                "break when the working directory changes."
            )
        db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url, connect_args={"check_same_thread": False})
    event.listen(engine, "connect", _configure_sqlite)
    return engine


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = build_engine()
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)
    return _session_factory


def open_session() -> Iterator[Session]:
    """FastAPI dependency: one session (= one unit of work) per request.

    Commits on success, rolls back on any exception — this is what makes each
    use case atomic (see docs/architecture.md, section 5).
    """
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def create_schema(engine: Engine | None = None) -> None:
    from app.infrastructure.persistence import models

    models.Base.metadata.create_all(engine or get_engine())


def drop_schema(engine: Engine | None = None) -> None:
    from app.infrastructure.persistence import models

    models.Base.metadata.drop_all(engine or get_engine())


def reset_state_for_tests() -> None:
    """Forget the cached engine/factory (used when tests swap the database URL)."""
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None
