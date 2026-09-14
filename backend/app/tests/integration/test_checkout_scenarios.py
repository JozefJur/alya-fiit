"""Checkout, stock, payment outcomes and refunds.

These run against a real isolated SQLite database through the FastAPI
TestClient.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select

from app.domain.entities.enums import (
    MovementType,
    OrderStatus,
    PaymentStatus,
    ReservationStatus,
)
from app.infrastructure.persistence.models import (
    Order,
    Payment,
    StockLevel,
    StockMovement,
    StockReservation,
)

ADDRESS = {
    "name": "Cyril Zákazník",
    "street": "Ilkovičova 2",
    "city": "Bratislava",
    "zip_code": "84216",
    "country": "SK",
}


def variant_by_sku(client, sku: str) -> dict:
    """Look a variant up through the public catalog API."""
    page = client.get("/api/catalog/products", params={"page_size": 60}).json()
    for product in page["items"]:
        for variant in product["variants"]:
            if variant["sku"] == sku:
                return variant
    raise AssertionError(f"variant {sku} not found in the catalog")


def availability(client, sku: str) -> int:
    return variant_by_sku(client, sku)["available"]


def checkout(client, headers: dict, token: str = "tok-success", coupon: str | None = None):
    payload = {"payment_token": token, "address": ADDRESS}
    if coupon is not None:
        payload["coupon_code"] = coupon
    return client.post("/api/orders/checkout", json=payload, headers=headers)


@pytest.fixture
def customer(auth_headers):  # noqa: ANN001
    return auth_headers("customer1@alya.test")


class TestScenario1SuccessfulCheckout:
    """Available variant + valid coupon + successful payment."""

    def test_order_is_paid_and_totals_are_server_computed(self, client, customer):
        variant = variant_by_sku(client, "CPM-TKL-RED")
        before = variant["available"]

        client.post(
            "/api/cart/items", json={"variant_id": variant["id"], "quantity": 2}, headers=customer
        )
        cart = client.post("/api/cart/coupon", json={"code": "WELCOME10"}, headers=customer).json()
        assert Decimal(cart["discount_total"]) > 0

        response = checkout(client, customer)
        assert response.status_code == 201, response.text
        order = response.json()

        assert order["status"] == OrderStatus.PAID.value
        assert order["grand_total"] == cart["grand_total"]
        assert order["coupon_code"] == "WELCOME10"
        assert len(order["items"]) == 1
        assert order["items"][0]["quantity"] == 2
        # Reservation consumed availability, stock not yet shipped.
        assert availability(client, "CPM-TKL-RED") == before - 2

    def test_payment_notification_and_audit_exist(self, client, customer):
        variant = variant_by_sku(client, "ASB-MINI")
        client.post(
            "/api/cart/items", json={"variant_id": variant["id"], "quantity": 1}, headers=customer
        )
        order = checkout(client, customer).json()
        admin = _admin_headers(client)

        notifications = client.get(
            "/api/admin/notifications", headers=admin, params={"limit": 500}
        ).json()
        types = {
            row["notification_type"]
            for row in notifications
            if order["order_number"] in row["subject"]
        }
        assert {"order_created", "payment_confirmed"} <= types

        audit = client.get(
            "/api/admin/audit-log",
            headers=admin,
            params={"entity_type": "order", "entity_id": str(order["id"])},
        ).json()
        actions = [entry["action"] for entry in audit]
        assert "order.created" in actions
        assert "stock.reserved" in actions
        assert actions.count("order.status_changed") >= 2

    def test_order_snapshot_survives_a_later_price_change(self, client, customer):
        variant = variant_by_sku(client, "LU-HUB8")
        client.post(
            "/api/cart/items", json={"variant_id": variant["id"], "quantity": 1}, headers=customer
        )
        order = checkout(client, customer).json()
        original_total = order["grand_total"]
        original_unit_price = order["items"][0]["unit_price"]

        admin = _admin_headers(client)
        products = client.get("/api/admin/products", params={"search": "Hub"}, headers=admin).json()
        client.patch(
            f"/api/admin/products/{products['items'][0]['id']}",
            json={"base_price": "999.00"},
            headers=admin,
        )

        again = client.get(f"/api/orders/{order['id']}", headers=customer).json()
        assert again["grand_total"] == original_total
        assert again["items"][0]["unit_price"] == original_unit_price


class TestScenario2InsufficientStock:
    def test_checkout_above_availability_fails_atomically(self, client, customer, session_factory):
        variant = variant_by_sku(client, "VAL13-16-512")  # seeded with 2 on hand
        assert variant["available"] == 2

        # The cart itself caps the quantity at availability.
        rejected = client.post(
            "/api/cart/items", json={"variant_id": variant["id"], "quantity": 3}, headers=customer
        )
        assert rejected.status_code == 409
        assert rejected.json()["error"]["code"] == "insufficient_stock"

        # Fill the cart to the limit, then drain the stock behind its back.
        client.post(
            "/api/cart/items", json={"variant_id": variant["id"], "quantity": 2}, headers=customer
        )
        with session_factory() as session:
            level = session.scalars(
                select(StockLevel).where(StockLevel.variant_id == variant["id"])
            ).one()
            level.on_hand = 1
            session.commit()

        response = checkout(client, customer)
        assert response.status_code in (409, 422)

        with session_factory() as session:
            orders = session.scalars(select(Order)).all()
            paid = [o for o in orders if o.status == OrderStatus.PAID and o.created_at]
            # No order was created for this failed attempt beyond the seeded ones.
            assert all(
                not any(item.variant_id == variant["id"] for item in order.items)
                for order in paid
                if order.order_number.endswith(("0006", "0007", "0008"))
            )
            # No reservation leaked.
            leaked = session.scalars(
                select(StockReservation).where(
                    StockReservation.variant_id == variant["id"],
                    StockReservation.status == ReservationStatus.ACTIVE,
                )
            ).all()
            assert leaked == []


class TestScenario3FailedPayment:
    @pytest.mark.parametrize(
        ("token", "expected_payment_status"),
        [("tok-declined", PaymentStatus.DECLINED)],
    )
    def test_reservation_is_released_and_order_marked_failed(
        self, client, customer, token, expected_payment_status
    ):
        variant = variant_by_sku(client, "CPX-WHITE")
        before = variant["available"]

        client.post(
            "/api/cart/items", json={"variant_id": variant["id"], "quantity": 2}, headers=customer
        )
        order = checkout(client, customer, token=token).json()

        assert order["status"] == OrderStatus.PAYMENT_FAILED.value
        assert order["payments"][-1]["status"] == expected_payment_status.value
        assert availability(client, "CPX-WHITE") == before

    def test_release_movement_is_recorded(self, client, customer, session_factory):
        variant = variant_by_sku(client, "NV27-QHD")
        client.post(
            "/api/cart/items", json={"variant_id": variant["id"], "quantity": 1}, headers=customer
        )
        order = checkout(client, customer, token="tok-declined").json()

        with session_factory() as session:
            movements = session.scalars(
                select(StockMovement).where(StockMovement.reference == order["order_number"])
            ).all()
            kinds = [movement.movement_type for movement in movements]
            assert MovementType.RESERVATION in kinds
            assert MovementType.RELEASE in kinds

    def test_cart_is_kept_so_the_customer_can_retry(self, client, customer):
        variant = variant_by_sku(client, "DV-PORT-X5")
        client.post(
            "/api/cart/items", json={"variant_id": variant["id"], "quantity": 1}, headers=customer
        )
        checkout(client, customer, token="tok-declined")

        cart = client.get("/api/cart", headers=customer).json()
        assert len(cart["items"]) == 1
        retry = checkout(client, customer, token="tok-success").json()
        assert retry["status"] == OrderStatus.PAID.value


class TestScenario4RepeatedCallback:
    def test_conflicting_callback_is_rejected(self, client, customer):
        variant = variant_by_sku(client, "AN8L-128")
        client.post(
            "/api/cart/items", json={"variant_id": variant["id"], "quantity": 1}, headers=customer
        )
        order = checkout(client, customer).json()
        key = order["payments"][-1]["idempotency_key"]

        response = client.post(
            "/api/payments/callback", json={"idempotency_key": key, "status": "declined"}
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "duplicate_callback_conflict"

        unchanged = client.get(f"/api/orders/{order['id']}", headers=customer).json()
        assert unchanged["status"] == OrderStatus.PAID.value

    def test_unknown_idempotency_key_is_not_found(self, client):
        response = client.post(
            "/api/payments/callback", json={"idempotency_key": "nope", "status": "authorized"}
        )
        assert response.status_code == 404


class TestScenario5CancelPaidOrder:
    def test_cancellation_refunds_and_releases_stock(self, client, customer, session_factory):
        variant = variant_by_sku(client, "DV-NVME-2TB")
        before = variant["available"]
        client.post(
            "/api/cart/items", json={"variant_id": variant["id"], "quantity": 2}, headers=customer
        )
        order = checkout(client, customer).json()
        assert availability(client, "DV-NVME-2TB") == before - 2

        cancelled = client.post(
            f"/api/orders/{order['id']}/cancel",
            json={"reason": "changed my mind"},
            headers=customer,
        )
        assert cancelled.status_code == 200, cancelled.text
        assert cancelled.json()["status"] == OrderStatus.CANCELLED.value

        assert availability(client, "DV-NVME-2TB") == before
        with session_factory() as session:
            payment = session.scalars(select(Payment).where(Payment.order_id == order["id"])).one()
            assert payment.status == PaymentStatus.REFUNDED
            assert len(payment.refunds) == 1

    def test_shipped_order_cannot_be_cancelled(self, client, customer, auth_headers):
        variant = variant_by_sku(client, "CPS-WL-GRY")
        client.post(
            "/api/cart/items", json={"variant_id": variant["id"], "quantity": 1}, headers=customer
        )
        order = checkout(client, customer).json()

        warehouse = auth_headers("warehouse@alya.test")
        for step in ("start-picking", "mark-ready", "ship"):
            assert (
                client.post(
                    f"/api/warehouse/orders/{order['id']}/{step}", headers=warehouse
                ).status_code
                == 200
            )

        response = client.post(
            f"/api/orders/{order['id']}/cancel", json={"reason": "too late"}, headers=customer
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "invalid_state_transition"


def _admin_headers(client) -> dict[str, str]:
    response = client.post(
        "/api/auth/login", json={"email": "admin@alya.test", "password": "Admin123!"}
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}
