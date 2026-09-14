"""Database session dependency (one unit of work per request)."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy.orm import Session

from app.infrastructure.persistence.database import open_session


def get_session() -> Iterator[Session]:
    yield from open_session()
