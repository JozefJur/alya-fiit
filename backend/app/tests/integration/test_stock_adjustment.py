"""Integration tests for the administrative stock adjustment.

POST /api/warehouse/inventory/adjust goes through the real FastAPI app, the
service layer and an isolated SQLite database that pytest creates per test.
"""

import pytest
from sqlalchemy import func, select

from app.domain.entities.enums import MovementType
from app.infrastructure.persistence.models import AuditLogEntry, StockLevel, StockMovement
from app.tests.integration.test_checkout_scenarios import checkout, variant_by_sku

ADJUST = "/api/warehouse/inventory/adjust"


@pytest.fixture
def admin(auth_headers):
    return auth_headers("admin@alya.test")


@pytest.fixture
def customer(auth_headers):
    return auth_headers("customer1@alya.test")


@pytest.fixture
def support(auth_headers):
    return auth_headers("support@alya.test")


def on_hand(session_factory, variant_id):
    with session_factory() as session:
        return session.scalar(select(StockLevel.on_hand).where(StockLevel.variant_id == variant_id))


def count(session_factory, model, *conditions):
    with session_factory() as session:
        return session.scalar(select(func.count()).select_from(model).where(*conditions))


# ---------------------------------------------------------------------------
# 1. Only the response
# ---------------------------------------------------------------------------


def test_adjustment_is_accepted(client, admin):
    variant = variant_by_sku(client, "LU-USBC-1M")

    response = client.post(
        ADJUST,
        json={"variant_id": variant["id"], "quantity_change": 5, "reason": "Delivery"},
        headers=admin,
    )

    assert response.status_code == 200


# ---------------------------------------------------------------------------
# 2. What the process left in the database
# ---------------------------------------------------------------------------


def test_adjustment_changes_stock_in_the_database(client, admin, session_factory):
    variant = variant_by_sku(client, "LU-USBC-1M")
    before = on_hand(session_factory, variant["id"])

    client.post(
        ADJUST,
        json={"variant_id": variant["id"], "quantity_change": 5, "reason": "Delivery"},
        headers=admin,
    )

    assert on_hand(session_factory, variant["id"]) == before + 5


def test_adjustment_is_recorded_as_one_movement(client, admin, session_factory):
    variant = variant_by_sku(client, "LU-USBC-1M")
    is_adjustment = (
        StockMovement.variant_id == variant["id"],
        StockMovement.movement_type == MovementType.ADJUSTMENT,
    )
    before = count(session_factory, StockMovement, *is_adjustment)

    client.post(
        ADJUST,
        json={"variant_id": variant["id"], "quantity_change": 5, "reason": "Delivery"},
        headers=admin,
    )

    assert count(session_factory, StockMovement, *is_adjustment) == before + 1


def test_adjustment_is_audited(client, admin, session_factory):
    variant = variant_by_sku(client, "LU-USBC-1M")
    is_audit = (
        AuditLogEntry.action == "stock.adjusted",
        AuditLogEntry.entity_id == str(variant["id"]),
    )
    before = count(session_factory, AuditLogEntry, *is_audit)

    client.post(
        ADJUST,
        json={"variant_id": variant["id"], "quantity_change": 5, "reason": "Delivery"},
        headers=admin,
    )

    assert count(session_factory, AuditLogEntry, *is_audit) == before + 1


# ---------------------------------------------------------------------------
# 3. A rejected request leaves nothing behind
# ---------------------------------------------------------------------------


def test_blank_reason_changes_nothing(client, admin, session_factory):
    variant = variant_by_sku(client, "LU-USBC-1M")
    stock_before = on_hand(session_factory, variant["id"])
    movements_before = count(session_factory, StockMovement)

    response = client.post(
        ADJUST,
        json={"variant_id": variant["id"], "quantity_change": 5, "reason": "   "},
        headers=admin,
    )

    assert response.status_code == 422
    assert on_hand(session_factory, variant["id"]) == stock_before
    assert count(session_factory, StockMovement) == movements_before


def test_stock_cannot_drop_below_what_is_reserved(client, admin, customer, session_factory):
    variant = variant_by_sku(client, "NES-ERGO")
    client.post("/api/cart/items", json={"variant_id": variant["id"], "quantity": 2}, headers=customer)
    checkout(client, customer)
    stock_before = on_hand(session_factory, variant["id"])

    response = client.post(
        ADJUST,
        json={"variant_id": variant["id"], "quantity_change": -3, "reason": "Stocktake"},
        headers=admin,
    )

    assert response.status_code == 409
    assert on_hand(session_factory, variant["id"]) == stock_before


# ---------------------------------------------------------------------------
# 4. Who may call it: 401 and 403 mean different things
# ---------------------------------------------------------------------------


def test_anonymous_caller_is_not_authenticated(client):
    response = client.post(ADJUST, json={"variant_id": 1, "quantity_change": 1, "reason": "x"})
    assert response.status_code == 401


@pytest.mark.parametrize("role", ["customer", "support"])
def test_customer_and_support_are_not_authorized(client, role, request):
    headers = request.getfixturevalue(role)
    response = client.post(
        ADJUST, json={"variant_id": 1, "quantity_change": 1, "reason": "x"}, headers=headers
    )
    assert response.status_code == 403
