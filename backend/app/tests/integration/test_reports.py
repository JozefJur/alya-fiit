"""Report regression tests.

These pin the numbers the report produces, so the implementation can be changed
without changing the results.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.domain.entities.enums import OrderStatus
from app.infrastructure.persistence.models import Order, utcnow
from app.tests.integration.test_checkout_scenarios import checkout, variant_by_sku

WINDOW = {"from": "2020-01-01", "to": "2035-12-31"}


@pytest.fixture
def admin(auth_headers):  # noqa: ANN001
    return auth_headers("admin@alya.test")


@pytest.fixture
def customer(auth_headers):  # noqa: ANN001
    return auth_headers("customer1@alya.test")


def report(client, admin, **overrides):  # noqa: ANN001
    response = client.get(
        "/api/admin/reports/inventory-sales", headers=admin, params={**WINDOW, **overrides}
    )
    assert response.status_code == 200, response.text
    return response.json()


class TestReportStructure:
    def test_report_contains_every_required_section(self, client, admin):
        data = report(client, admin)
        assert set(data) == {
            "period",
            "summary",
            "variants",
            "low_stock",
            "top_products",
            "high_cancellation_products",
        }
        assert set(data["summary"]) == {
            "orders_total",
            "orders_revenue",
            "orders_cancelled",
            "orders_refunded",
            "revenue",
            "discount_total",
            "average_order_value",
            "total_on_hand",
            "total_reserved",
            "total_available",
        }

    def test_one_row_per_variant(self, client, admin):
        data = report(client, admin)
        assert len(data["variants"]) == 28  # seeded variants
        assert len({row["variant_id"] for row in data["variants"]}) == 28

    def test_money_is_formatted_with_two_decimals(self, client, admin):
        data = report(client, admin)
        assert data["summary"]["revenue"].count(".") == 1
        assert len(data["summary"]["revenue"].split(".")[1]) == 2
        for row in data["variants"][:5]:
            assert len(row["revenue"].split(".")[1]) == 2


class TestReportReconciliation:
    def test_revenue_equals_the_sum_of_counted_orders(self, client, admin, session_factory):
        data = report(client, admin)
        revenue_statuses = {
            OrderStatus.PAID,
            OrderStatus.PICKING,
            OrderStatus.READY_TO_SHIP,
            OrderStatus.SHIPPED,
            OrderStatus.DELIVERED,
            OrderStatus.CANCEL_REQUESTED,
            OrderStatus.RETURN_REQUESTED,
            OrderStatus.RETURN_APPROVED,
            OrderStatus.RETURNED,
        }
        with session_factory() as session:
            orders = session.scalars(select(Order)).all()
            expected = sum(
                (order.grand_total for order in orders if order.status in revenue_statuses),
                Decimal("0"),
            )
            expected_count = sum(1 for order in orders if order.status in revenue_statuses)
        assert Decimal(data["summary"]["revenue"]) == expected
        assert data["summary"]["orders_revenue"] == expected_count

    def test_average_order_value_matches_revenue_over_orders(self, client, admin):
        summary = report(client, admin)["summary"]
        expected = (Decimal(summary["revenue"]) / summary["orders_revenue"]).quantize(
            Decimal("0.01")
        )
        assert Decimal(summary["average_order_value"]) == expected

    def test_sold_quantities_match_the_order_items(self, client, admin, session_factory):
        data = report(client, admin)
        with session_factory() as session:
            orders = session.scalars(select(Order)).all()
            expected: dict[int, int] = {}
            countable = {
                OrderStatus.PAID,
                OrderStatus.PICKING,
                OrderStatus.READY_TO_SHIP,
                OrderStatus.SHIPPED,
                OrderStatus.DELIVERED,
                OrderStatus.RETURNED,
            }
            for order in orders:
                if order.status not in countable:
                    continue
                for item in order.items:
                    expected[item.variant_id] = expected.get(item.variant_id, 0) + item.quantity
        reported = {
            row["variant_id"]: row["quantity_sold"]
            for row in data["variants"]
            if row["quantity_sold"]
        }
        assert reported == expected

    def test_stock_totals_match_the_inventory_view(self, client, admin):
        summary = report(client, admin)["summary"]
        inventory = client.get("/api/warehouse/inventory", headers=admin).json()
        assert summary["total_on_hand"] == sum(row["on_hand"] for row in inventory)
        assert summary["total_reserved"] == sum(row["reserved"] for row in inventory)
        assert summary["total_available"] == summary["total_on_hand"] - summary["total_reserved"]

    def test_low_stock_rows_satisfy_the_threshold_rule(self, client, admin):
        data = report(client, admin)
        assert data["low_stock"], "the seeded dataset contains low-stock variants"
        for row in data["low_stock"]:
            assert row["available"] <= row["low_stock_threshold"]
        flagged = {row["variant_id"] for row in data["variants"] if row["is_low_stock"]}
        assert {row["variant_id"] for row in data["low_stock"]} == flagged

    def test_top_products_are_ranked_by_quantity(self, client, admin):
        top = report(client, admin)["top_products"]
        quantities = [entry["quantity_sold"] for entry in top]
        assert quantities == sorted(quantities, reverse=True)
        assert len(top) <= 10

    def test_top_limit_is_honoured(self, client, admin):
        assert len(report(client, admin, top_limit=2)["top_products"]) <= 2


class TestReportFilters:
    def test_category_filter_restricts_the_rows(self, client, admin):
        categories = client.get("/api/admin/categories", headers=admin).json()
        headphones = next(c for c in categories if c["name"] == "Headphones")
        data = report(client, admin, category_id=headphones["id"])
        skus = {row["sku"] for row in data["variants"]}
        assert "ASQ700-BLK" in skus
        assert "LU-HUB8" not in skus

    def test_empty_period_reports_zero_revenue(self, client, admin):
        data = report(client, admin, **{"from": "2019-01-01", "to": "2019-12-31"})
        assert data["summary"]["orders_total"] == 0
        assert data["summary"]["revenue"] == "0.00"
        assert data["summary"]["average_order_value"] == "0.00"

    def test_reversed_period_is_rejected(self, client, admin):
        response = client.get(
            "/api/admin/reports/inventory-sales",
            headers=admin,
            params={"from": "2026-05-01", "to": "2026-04-01"},
        )
        assert response.status_code == 422

    def test_malformed_date_is_rejected(self, client, admin):
        response = client.get(
            "/api/admin/reports/inventory-sales",
            headers=admin,
            params={"from": "01/05/2026", "to": "2026-06-01"},
        )
        assert response.status_code == 422

    def test_non_admin_cannot_read_the_report(self, client, auth_headers):
        for email in ("customer1@alya.test", "warehouse@alya.test", "support@alya.test"):
            response = client.get(
                "/api/admin/reports/inventory-sales",
                headers=auth_headers(email),
                params=WINDOW,
            )
            assert response.status_code == 403


class TestReportReactsToNewData:
    def test_a_new_order_moves_revenue_and_quantities(self, client, admin, customer):
        before = report(client, admin)
        variant = variant_by_sku(client, "NV27-QHD")
        client.post(
            "/api/cart/items", json={"variant_id": variant["id"], "quantity": 3}, headers=customer
        )
        order = checkout(client, customer).json()

        after = report(client, admin)
        assert Decimal(after["summary"]["revenue"]) == Decimal(
            before["summary"]["revenue"]
        ) + Decimal(order["grand_total"])
        assert after["summary"]["orders_revenue"] == before["summary"]["orders_revenue"] + 1

        sold_before = next(
            row["quantity_sold"] for row in before["variants"] if row["sku"] == "NV27-QHD"
        )
        sold_after = next(
            row["quantity_sold"] for row in after["variants"] if row["sku"] == "NV27-QHD"
        )
        assert sold_after == sold_before + 3

    def test_a_cancelled_order_is_counted_separately(self, client, admin, customer):
        variant = variant_by_sku(client, "CPX-WHITE")
        client.post(
            "/api/cart/items", json={"variant_id": variant["id"], "quantity": 1}, headers=customer
        )
        order = checkout(client, customer).json()
        before = report(client, admin)

        client.post(
            f"/api/orders/{order['id']}/cancel", json={"reason": "not needed"}, headers=customer
        )
        after = report(client, admin)

        assert after["summary"]["orders_cancelled"] == before["summary"]["orders_cancelled"] + 1
        assert Decimal(after["summary"]["revenue"]) == Decimal(
            before["summary"]["revenue"]
        ) - Decimal(order["grand_total"])

    def test_failed_payments_never_count_as_revenue(self, client, admin, customer):
        before = report(client, admin)
        variant = variant_by_sku(client, "AN8-256-BLU")
        client.post(
            "/api/cart/items", json={"variant_id": variant["id"], "quantity": 1}, headers=customer
        )
        checkout(client, customer, token="tok-declined")
        after = report(client, admin)
        assert after["summary"]["revenue"] == before["summary"]["revenue"]

    def test_orders_outside_the_window_are_excluded(self, client, admin, customer, session_factory):
        variant = variant_by_sku(client, "VPB14-16-512")
        client.post(
            "/api/cart/items", json={"variant_id": variant["id"], "quantity": 1}, headers=customer
        )
        order = checkout(client, customer).json()

        # Move the order two years back and narrow the window to "recent".
        with session_factory() as session:
            stored = session.get(Order, order["id"])
            assert stored is not None
            stored.created_at = utcnow() - timedelta(days=730)
            session.commit()

        recent = report(
            client,
            admin,
            **{
                "from": (utcnow() - timedelta(days=7)).date().isoformat(),
                "to": utcnow().date().isoformat(),
            },
        )
        numbers = client.get("/api/support/orders", headers=admin)
        assert numbers.status_code == 200
        assert Decimal(recent["summary"]["revenue"]) < Decimal(
            report(client, admin)["summary"]["revenue"]
        )


class TestReportCsvExport:
    def test_csv_matches_the_json_values(self, client, admin):
        data = report(client, admin)
        response = client.get(
            "/api/admin/reports/inventory-sales.csv", headers=admin, params=WINDOW
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/csv")

        lines = response.text.strip().splitlines()
        assert lines[0] == (
            "sku,product_name,quantity_sold,revenue,discount,on_hand,reserved,available,is_low_stock"
        )
        assert len(lines) - 1 == len(data["variants"])

        first_row = lines[1].split(",")
        first_json = data["variants"][0]
        assert first_row[0] == first_json["sku"]
        assert int(first_row[2]) == first_json["quantity_sold"]
        assert first_row[3] == first_json["revenue"]
        assert first_row[8] == ("yes" if first_json["is_low_stock"] else "no")

    def test_csv_is_admin_only(self, client, auth_headers):
        response = client.get(
            "/api/admin/reports/inventory-sales.csv",
            headers=auth_headers("support@alya.test"),
            params=WINDOW,
        )
        assert response.status_code == 403
