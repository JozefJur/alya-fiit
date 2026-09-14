"""Admin inventory & sales report.

Composes the sales and inventory reports and merges them per variant.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.application.commands.commands import ReportQuery
from app.application.services.reports import (
    InventoryReportService,
    SalesReportService,
)


def money(value: Decimal) -> str:
    """Report money as a plain 2-decimal string (JSON and CSV share this format)."""
    return f"{value:.2f}"


class InventorySalesReport:
    def __init__(self, sales: SalesReportService, inventory: InventoryReportService) -> None:
        self._sales = sales
        self._inventory = inventory

    def build(self, query: ReportQuery) -> dict[str, Any]:
        sales = self._sales.build(query)
        inventory = self._inventory.build(category_id=query.category_id)

        stock_by_variant = {row.variant_id: row for row in inventory.variants}
        sold_by_variant = {row.variant_id: row for row in sales.variant_sales}

        rows: list[dict[str, Any]] = []
        for stock in inventory.variants:
            sold = sold_by_variant.get(stock.variant_id)
            rows.append(
                {
                    "variant_id": stock.variant_id,
                    "sku": stock.sku,
                    "product_id": stock.product_id,
                    "product_name": stock.product_name,
                    "quantity_sold": sold.quantity_sold if sold else 0,
                    "revenue": money(sold.revenue) if sold else "0.00",
                    "discount": money(sold.discount) if sold else "0.00",
                    "on_hand": stock.on_hand,
                    "reserved": stock.reserved,
                    "available": stock.available,
                    "low_stock_threshold": stock.low_stock_threshold,
                    "is_low_stock": stock.is_low_stock,
                }
            )
        # Sold variants that no longer appear in the (filtered) stock listing.
        for sold in sales.variant_sales:
            if sold.variant_id not in stock_by_variant:
                rows.append(
                    {
                        "variant_id": sold.variant_id,
                        "sku": sold.sku,
                        "product_id": sold.product_id,
                        "product_name": sold.product_name,
                        "quantity_sold": sold.quantity_sold,
                        "revenue": money(sold.revenue),
                        "discount": money(sold.discount),
                        "on_hand": 0,
                        "reserved": 0,
                        "available": 0,
                        "low_stock_threshold": 0,
                        "is_low_stock": False,
                    }
                )
        rows.sort(key=lambda row: (-row["quantity_sold"], row["sku"]))

        return {
            "period": {"from": sales.date_from, "to": sales.date_to},
            "summary": {
                "orders_total": sales.orders_total,
                "orders_revenue": sales.orders_revenue,
                "orders_cancelled": sales.orders_cancelled,
                "orders_refunded": sales.orders_refunded,
                "revenue": money(sales.revenue),
                "discount_total": money(sales.discount_total),
                "average_order_value": money(sales.average_order_value),
                "total_on_hand": inventory.total_on_hand,
                "total_reserved": inventory.total_reserved,
                "total_available": inventory.total_available,
            },
            "variants": rows,
            "low_stock": [
                {
                    "variant_id": row.variant_id,
                    "sku": row.sku,
                    "product_name": row.product_name,
                    "available": row.available,
                    "low_stock_threshold": row.low_stock_threshold,
                }
                for row in inventory.low_stock
            ],
            "top_products": [
                {**entry, "revenue": money(entry["revenue"])} for entry in sales.top_products
            ],
            "high_cancellation_products": sales.high_cancellation_products,
        }

    def csv_rows(self, report: dict[str, Any]) -> tuple[list[str], list[list[Any]]]:
        headers = [
            "sku",
            "product_name",
            "quantity_sold",
            "revenue",
            "discount",
            "on_hand",
            "reserved",
            "available",
            "is_low_stock",
        ]
        rows = [
            [
                row["sku"],
                row["product_name"],
                row["quantity_sold"],
                row["revenue"],
                row["discount"],
                row["on_hand"],
                row["reserved"],
                row["available"],
                "yes" if row["is_low_stock"] else "no",
            ]
            for row in report["variants"]
        ]
        return headers, rows
