"""Role-gated fulfillment, audited stock changes and CSV import."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.domain.entities.enums import MovementType, OrderStatus
from app.infrastructure.persistence.models import StockLevel, StockMovement
from app.tests.integration.test_checkout_scenarios import (
    availability,
    checkout,
    variant_by_sku,
)


@pytest.fixture
def customer(auth_headers):  # noqa: ANN001
    return auth_headers("customer1@alya.test")


@pytest.fixture
def warehouse(auth_headers):  # noqa: ANN001
    return auth_headers("warehouse@alya.test")


@pytest.fixture
def admin(auth_headers):  # noqa: ANN001
    return auth_headers("admin@alya.test")


@pytest.fixture
def support(auth_headers):  # noqa: ANN001
    return auth_headers("support@alya.test")


@pytest.fixture
def paid_order(client, customer):  # noqa: ANN001
    variant = variant_by_sku(client, "CPM-TKL-BLUE")
    client.post(
        "/api/cart/items", json={"variant_id": variant["id"], "quantity": 2}, headers=customer
    )
    return checkout(client, customer).json()


class TestScenario6RoleGatedTransitions:
    def test_warehouse_walks_the_pipeline(self, client, warehouse, paid_order):
        order_id = paid_order["id"]

        picking = client.post(f"/api/warehouse/orders/{order_id}/start-picking", headers=warehouse)
        assert picking.status_code == 200
        assert picking.json()["status"] == OrderStatus.PICKING.value

        ready = client.post(f"/api/warehouse/orders/{order_id}/mark-ready", headers=warehouse)
        assert ready.json()["status"] == OrderStatus.READY_TO_SHIP.value

        shipped = client.post(f"/api/warehouse/orders/{order_id}/ship", headers=warehouse)
        assert shipped.json()["status"] == OrderStatus.SHIPPED.value
        assert shipped.json()["expected_delivery"] is not None

    def test_customer_cannot_trigger_fulfillment(self, client, customer, paid_order):
        response = client.post(
            f"/api/warehouse/orders/{paid_order['id']}/start-picking", headers=customer
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "not_authorized"

    def test_anonymous_request_is_unauthenticated(self, client, paid_order):
        response = client.post(f"/api/warehouse/orders/{paid_order['id']}/start-picking")
        assert response.status_code == 401

    def test_skipping_a_step_is_rejected(self, client, warehouse, paid_order):
        response = client.post(f"/api/warehouse/orders/{paid_order['id']}/ship", headers=warehouse)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "invalid_state_transition"

    def test_shipping_consumes_the_reservation(self, client, warehouse, customer, paid_order):
        before = availability(client, "CPM-TKL-BLUE")
        for step in ("start-picking", "mark-ready", "ship"):
            client.post(f"/api/warehouse/orders/{paid_order['id']}/{step}", headers=warehouse)
        # Reservation became a real outflow: availability unchanged, on_hand down.
        assert availability(client, "CPM-TKL-BLUE") == before
        inventory = client.get("/api/warehouse/inventory", headers=warehouse).json()
        row = next(item for item in inventory if item["sku"] == "CPM-TKL-BLUE")
        assert row["reserved"] == 0

    def test_every_transition_is_recorded_in_history(self, client, warehouse, customer, paid_order):
        for step in ("start-picking", "mark-ready", "ship"):
            client.post(f"/api/warehouse/orders/{paid_order['id']}/{step}", headers=warehouse)
        detail = client.get(f"/api/orders/{paid_order['id']}", headers=customer).json()
        events = [entry["event"] for entry in detail["status_history"]]
        assert events[-3:] == ["start_picking", "mark_ready", "ship"]
        assert all(entry["actor_user_id"] is not None for entry in detail["status_history"][-3:])

    def test_customer_sees_only_own_orders(self, client, auth_headers, paid_order):
        other = auth_headers("customer2@alya.test")
        listing = client.get("/api/orders", headers=other).json()
        assert all(row["id"] != paid_order["id"] for row in listing)
        assert client.get(f"/api/orders/{paid_order['id']}", headers=other).status_code == 404

    def test_support_may_read_any_order(self, client, support, paid_order):
        assert (
            client.get(f"/api/support/orders/{paid_order['id']}", headers=support).status_code
            == 200
        )

    def test_support_cannot_adjust_stock(self, client, support):
        response = client.post(
            "/api/warehouse/inventory/adjust",
            json={"variant_id": 1, "quantity_change": 5, "reason": "nope"},
            headers=support,
        )
        assert response.status_code == 403

    def test_warehouse_cannot_change_prices(self, client, warehouse):
        response = client.patch(
            "/api/admin/products/1", json={"base_price": "1.00"}, headers=warehouse
        )
        assert response.status_code == 403


class TestScenario7AuditedStockAdjustment:
    def test_adjustment_creates_movement_and_audit_entry(self, client, admin, session_factory):
        variant = variant_by_sku(client, "LU-USBC-1M")
        before = variant["available"]

        response = client.post(
            "/api/warehouse/inventory/adjust",
            json={
                "variant_id": variant["id"],
                "quantity_change": -5,
                "reason": "Damaged in transit",
            },
            headers=admin,
        )
        assert response.status_code == 200
        assert response.json()["available"] == before - 5

        with session_factory() as session:
            movement = session.scalars(
                select(StockMovement)
                .where(
                    StockMovement.variant_id == variant["id"],
                    StockMovement.movement_type == MovementType.ADJUSTMENT,
                )
                .order_by(StockMovement.id.desc())
            ).first()
            assert movement is not None
            assert movement.quantity == -5
            assert movement.reason == "Damaged in transit"
            assert movement.actor_user_id is not None

        audit = client.get(
            "/api/admin/audit-log",
            headers=admin,
            params={"entity_type": "variant", "entity_id": str(variant["id"])},
        ).json()
        assert any(entry["action"] == "stock.adjusted" for entry in audit)

    def test_adjustment_requires_a_reason(self, client, admin):
        variant = variant_by_sku(client, "LU-USBC-1M")
        response = client.post(
            "/api/warehouse/inventory/adjust",
            json={"variant_id": variant["id"], "quantity_change": 1, "reason": "   "},
            headers=admin,
        )
        assert response.status_code == 422

    def test_adjustment_cannot_break_stock_invariants(self, client, admin, warehouse, customer):
        variant = variant_by_sku(client, "NES-ERGO")
        client.post(
            "/api/cart/items", json={"variant_id": variant["id"], "quantity": 2}, headers=customer
        )
        checkout(client, customer)

        # 2 units are reserved; dropping on_hand below that must fail.
        response = client.post(
            "/api/warehouse/inventory/adjust",
            json={"variant_id": variant["id"], "quantity_change": -3, "reason": "stocktake"},
            headers=admin,
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "conflict"

    def test_threshold_change_is_audited(self, client, admin):
        variant = variant_by_sku(client, "LU-HDMI21-2M")
        raised = variant["available"] + 1  # guarantees the variant becomes low-stock
        response = client.post(
            "/api/warehouse/inventory/threshold",
            json={"variant_id": variant["id"], "low_stock_threshold": raised},
            headers=admin,
        )
        assert response.status_code == 200
        assert response.json()["is_low_stock"] is True
        audit = client.get(
            "/api/admin/audit-log",
            headers=admin,
            params={"entity_type": "variant", "entity_id": str(variant["id"])},
        ).json()
        assert any(entry["action"] == "stock.threshold_changed" for entry in audit)


class TestScenario8CsvImport:
    def _upload(self, client, admin, body: str):
        return client.post(
            "/api/admin/inventory/import",
            files={"file": ("stock.csv", body, "text/csv")},
            headers=admin,
        )

    def test_valid_file_is_applied(self, client, admin, session_factory):
        body = "sku,on_hand\nLU-HUB8,100\nLU-USBC-1M,120\n"
        response = self._upload(client, admin, body)
        assert response.status_code == 200, response.text
        assert response.json() == {"applied": 2, "unchanged": 0, "movements": 2}

        with session_factory() as session:
            levels = {
                level.variant.sku: level.on_hand
                for level in session.scalars(select(StockLevel)).all()
                if level.variant.sku in {"LU-HUB8", "LU-USBC-1M"}
            }
        assert levels == {"LU-HUB8": 100, "LU-USBC-1M": 120}

    def test_unchanged_rows_create_no_movement(self, client, admin):
        current = variant_by_sku(client, "LU-HUB8")["available"]
        response = self._upload(client, admin, f"sku,on_hand\nLU-HUB8,{current}\n")
        assert response.json() == {"applied": 0, "unchanged": 1, "movements": 0}

    def test_optional_threshold_column_is_accepted(self, client, admin):
        response = self._upload(client, admin, "sku,on_hand,low_stock_threshold\nLU-HUB8,42,7\n")
        assert response.status_code == 200
        inventory = client.get("/api/warehouse/inventory", headers=admin).json()
        row = next(item for item in inventory if item["sku"] == "LU-HUB8")
        assert row["on_hand"] == 42
        assert row["low_stock_threshold"] == 7

    def test_one_invalid_row_rejects_the_whole_file(self, client, admin, session_factory):
        with session_factory() as session:
            before = {
                level.variant.sku: level.on_hand
                for level in session.scalars(select(StockLevel)).all()
            }

        body = "sku,on_hand\nLU-HUB8,10\nNOPE-404,5\nLU-USBC-1M,abc\n"
        response = self._upload(client, admin, body)
        assert response.status_code == 422
        error = response.json()["error"]
        assert error["code"] == "csv_import_error"
        rows = error["details"]["row_errors"]
        assert {row["line"] for row in rows} == {3, 4}
        assert error["details"]["valid_rows"] == 1

        with session_factory() as session:
            after = {
                level.variant.sku: level.on_hand
                for level in session.scalars(select(StockLevel)).all()
            }
        assert after == before, "a rejected import must not change any stock"

    def test_duplicate_sku_is_reported(self, client, admin):
        response = self._upload(client, admin, "sku,on_hand\nLU-HUB8,10\nLU-HUB8,12\n")
        assert response.status_code == 422
        rows = response.json()["error"]["details"]["row_errors"]
        assert any("Duplicate" in row["message"] for row in rows)

    def test_import_below_reserved_quantity_is_rejected(self, client, admin, customer):
        variant = variant_by_sku(client, "VET-TB")
        client.post(
            "/api/cart/items", json={"variant_id": variant["id"], "quantity": 3}, headers=customer
        )
        checkout(client, customer)

        response = self._upload(client, admin, "sku,on_hand\nVET-TB,1\n")
        assert response.status_code == 422
        message = response.json()["error"]["details"]["row_errors"][0]["message"]
        assert "reserved" in message

    def test_missing_required_column_is_rejected(self, client, admin):
        response = self._upload(client, admin, "sku\nLU-HUB8\n")
        assert response.status_code == 422
        assert "on_hand" in response.json()["error"]["message"]

    def test_unknown_column_is_rejected(self, client, admin):
        response = self._upload(client, admin, "sku,on_hand,price\nLU-HUB8,5,10\n")
        assert response.status_code == 422
        assert "price" in response.json()["error"]["message"]

    def test_non_admin_cannot_import(self, client, warehouse):
        response = client.post(
            "/api/admin/inventory/import",
            files={"file": ("stock.csv", "sku,on_hand\nLU-HUB8,1\n", "text/csv")},
            headers=warehouse,
        )
        assert response.status_code == 403

    def test_export_round_trips_through_import(self, client, admin):
        exported = client.get("/api/admin/inventory/export.csv", headers=admin)
        assert exported.status_code == 200
        assert exported.headers["content-type"].startswith("text/csv")
        header, *rows = exported.text.strip().splitlines()
        assert header == "sku,on_hand,reserved,available,low_stock_threshold"
        assert len(rows) == 28  # one per seeded variant

        reduced = "sku,on_hand\n" + "\n".join(
            f"{row.split(',')[0]},{row.split(',')[1]}" for row in rows
        )
        again = self._upload(client, admin, reduced + "\n")
        assert again.status_code == 200
        assert again.json()["applied"] == 0  # nothing changed
