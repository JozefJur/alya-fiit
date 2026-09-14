"""Shared pytest fixtures.

Unit tests use in-memory fakes only. Integration tests get a real, isolated
SQLite database per test (a temporary file, created and dropped around the
test) plus a FastAPI TestClient wired to it — so tests are order-independent
and never touch the development database.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import pytest

# The application reads its settings at import time, so the test database URL
# must be in the environment before any app module is imported.
os.environ.setdefault("ALYA_JWT_SECRET", "test-secret-long-enough-for-hs256-hmac-keys")


@pytest.fixture
def fixed_now() -> datetime:
    """A stable "current time" for tests that exercise date-dependent rules."""
    return datetime(2026, 6, 15, 12, 0, 0)


@pytest.fixture
def database_url(tmp_path: Path) -> str:
    return f"sqlite:///{tmp_path / 'integration.db'}"


@pytest.fixture
def session(database_url: str) -> Iterator:
    """A SQLAlchemy session against a fresh, empty schema."""
    from sqlalchemy.orm import sessionmaker

    from app.infrastructure.persistence.database import (
        build_engine,
        create_schema,
    )

    engine = build_engine(database_url)
    create_schema(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    db_session = factory()
    try:
        yield db_session
    finally:
        db_session.close()
        engine.dispose()


@pytest.fixture
def services(session):  # noqa: ANN001 - fixture chaining
    """A fully wired service container on the test session."""
    from app.api.dependencies.container import Services
    from app.config import Settings

    return Services(session, Settings())


@pytest.fixture
def seeded_services(services):  # noqa: ANN001
    """Service container with the seed dataset loaded and committed."""
    from app.infrastructure.seed.small import seed_small

    seed_small(services.session)
    services.session.commit()
    return services


@pytest.fixture
def app_environment(database_url: str) -> Iterator[dict]:
    """Isolated database with seed-small data, plus a session factory for it."""
    from sqlalchemy.orm import sessionmaker

    from app.infrastructure.persistence.database import build_engine, create_schema
    from app.infrastructure.seed.small import seed_small

    engine = build_engine(database_url)
    create_schema(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    setup_session = factory()
    try:
        seed_small(setup_session)
        setup_session.commit()
    finally:
        setup_session.close()

    try:
        yield {"engine": engine, "factory": factory}
    finally:
        engine.dispose()


@pytest.fixture
def session_factory(app_environment: dict):  # noqa: ANN201
    """Open a session on the same database the TestClient uses.

    Sessions are context managers, so tests read/verify state with:
    ``with session_factory() as session: ...``
    """
    return app_environment["factory"]


@pytest.fixture
def client(app_environment: dict) -> Iterator:
    """TestClient bound to an isolated database with seed-small data."""
    from fastapi.testclient import TestClient

    from app.api.dependencies.db import get_session
    from app.main import create_app

    factory = app_environment["factory"]

    def override_session() -> Iterator:
        db_session = factory()
        try:
            yield db_session
            db_session.commit()
        except Exception:
            db_session.rollback()
            raise
        finally:
            db_session.close()

    app = create_app(init_schema=False)
    app.dependency_overrides[get_session] = override_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Authentication helpers for API tests
# ---------------------------------------------------------------------------

SEED_PASSWORDS = {
    "admin@alya.test": "Admin123!",
    "warehouse@alya.test": "Warehouse123!",
    "support@alya.test": "Support123!",
    "customer1@alya.test": "Customer123!",
    "customer2@alya.test": "Customer123!",
}


@pytest.fixture
def auth_headers(client):  # noqa: ANN001
    """``auth_headers("customer1@alya.test")`` → bearer header for that account."""

    def factory(email: str) -> dict[str, str]:
        response = client.post(
            "/api/auth/login", json={"email": email, "password": SEED_PASSWORDS[email]}
        )
        assert response.status_code == 200, response.text
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    return factory
