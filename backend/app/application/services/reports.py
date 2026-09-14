"""Sales and inventory reporting."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal

from app.application.commands.commands import ReportQuery
from app.domain.entities.enums import OrderStatus
from app.domain.errors import ValidationError
from app.domain.policies.inventory import LowStockPolicy
from app.infrastructure.repositories.catalog import ProductRepository, VariantRepository
from app.infrastructure.repositories.inventory import StockLevelRepository
from app.infrastructure.repositories.orders import OrderRepository

#: Order states whose money counts as captured revenue.
REVENUE_STATUSES = frozenset(
    {
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
)

CANCELLED_STATUSES = frozenset({OrderStatus.CANCELLED})
REFUNDED_STATUSES = frozenset({OrderStatus.REFUNDED})

#: A product is "cancellation-heavy" above this ratio (with a minimum sample).
HIGH_CANCELLATION_RATIO = Decimal("0.3")
HIGH_CANCELLATION_MIN_ORDERS = 3


@dataclass
class VariantSales:
    variant_id: int
    sku: str
    product_id: int
    product_name: str
    category_id: int
    quantity_sold: int = 0
    revenue: Decimal = Decimal("0")
    discount: Decimal = Decimal("0")


@dataclass
class SalesReportData:
    date_from: str
    date_to: str
    orders_total: int
    orders_revenue: int
    orders_cancelled: int
    orders_refunded: int
    revenue: Decimal
    discount_total: Decimal
    average_order_value: Decimal
    variant_sales: list[VariantSales] = field(default_factory=list)
    top_products: list[dict] = field(default_factory=list)
    high_cancellation_products: list[dict] = field(default_factory=list)


@dataclass
class VariantStock:
    variant_id: int
    sku: str
    product_id: int
    product_name: str
    category_id: int
    on_hand: int
    reserved: int
    available: int
    low_stock_threshold: int
    is_low_stock: bool


@dataclass
class InventoryReportData:
    variants: list[VariantStock]
    total_on_hand: int
    total_reserved: int
    total_available: int
    low_stock: list[VariantStock]


def parse_report_period(query: ReportQuery) -> tuple[datetime, datetime]:
    try:
        start = datetime.fromisoformat(query.date_from)
        end_day = datetime.fromisoformat(query.date_to)
    except ValueError:
        raise ValidationError(
            "Dates must be ISO formatted (YYYY-MM-DD).",
            details={"from": query.date_from, "to": query.date_to},
        ) from None
    if end_day < start:
        raise ValidationError("'to' must not be before 'from'.")
    return start, end_day + timedelta(days=1)


class SalesReportService:
    def __init__(self, orders: OrderRepository, variants: VariantRepository) -> None:
        self._orders = orders
        self._variants = variants

    def build(self, query: ReportQuery) -> SalesReportData:
        start, end = parse_report_period(query)
        orders = self._orders.list_in_period(start, end)

        revenue = Decimal("0")
        discount_total = Decimal("0")
        orders_revenue = 0
        orders_cancelled = 0
        orders_refunded = 0

        variant_rows: dict[int, VariantSales] = {}
        product_orders: dict[int, set[int]] = {}
        product_cancelled: dict[int, set[int]] = {}
        product_names: dict[int, str] = {}

        for order in orders:
            items = self._orders.items_for_order(order.id)
            order_product_ids: set[int] = set()
            for item in items:
                variant = self._variants.get(item.variant_id)
                product = variant.product
                if query.category_id is not None and product.category_id != query.category_id:
                    continue
                order_product_ids.add(product.id)
                product_names[product.id] = product.name
                if order.status in REVENUE_STATUSES:
                    row = variant_rows.get(variant.id)
                    if row is None:
                        row = VariantSales(
                            variant_id=variant.id,
                            sku=variant.sku,
                            product_id=product.id,
                            product_name=product.name,
                            category_id=product.category_id,
                        )
                        variant_rows[variant.id] = row
                    row.quantity_sold += item.quantity
                    row.revenue += item.line_total
                    row.discount += item.discount_amount

            for product_id in order_product_ids:
                product_orders.setdefault(product_id, set()).add(order.id)
                if order.status in CANCELLED_STATUSES:
                    product_cancelled.setdefault(product_id, set()).add(order.id)

            if not order_product_ids and query.category_id is not None:
                continue  # order has nothing in the requested category
            if order.status in REVENUE_STATUSES:
                orders_revenue += 1
                revenue += order.grand_total
                discount_total += order.discount_total
            elif order.status in CANCELLED_STATUSES:
                orders_cancelled += 1
            elif order.status in REFUNDED_STATUSES:
                orders_refunded += 1

        average = (
            (revenue / orders_revenue).quantize(Decimal("0.01")) if orders_revenue else Decimal("0")
        )

        top = self._top_products(variant_rows, query.top_limit)
        heavy = self._high_cancellation(product_orders, product_cancelled, product_names)

        return SalesReportData(
            date_from=query.date_from,
            date_to=query.date_to,
            orders_total=len(orders),
            orders_revenue=orders_revenue,
            orders_cancelled=orders_cancelled,
            orders_refunded=orders_refunded,
            revenue=revenue,
            discount_total=discount_total,
            average_order_value=average,
            variant_sales=sorted(
                variant_rows.values(), key=lambda row: (-row.quantity_sold, row.sku)
            ),
            top_products=top,
            high_cancellation_products=heavy,
        )

    @staticmethod
    def _top_products(variant_rows: dict[int, VariantSales], limit: int) -> list[dict]:
        per_product: dict[int, dict] = {}
        for row in variant_rows.values():
            summary = per_product.get(row.product_id)
            if summary is None:
                summary = {
                    "product_id": row.product_id,
                    "product_name": row.product_name,
                    "quantity_sold": 0,
                    "revenue": Decimal("0"),
                }
                per_product[row.product_id] = summary
            summary["quantity_sold"] += row.quantity_sold
            summary["revenue"] += row.revenue
        ranked = sorted(
            per_product.values(),
            key=lambda entry: (-entry["quantity_sold"], entry["product_name"]),
        )
        return ranked[: max(limit, 0)]

    @staticmethod
    def _high_cancellation(
        product_orders: dict[int, set[int]],
        product_cancelled: dict[int, set[int]],
        product_names: dict[int, str],
    ) -> list[dict]:
        flagged: list[dict] = []
        for product_id, order_ids in product_orders.items():
            cancelled = product_cancelled.get(product_id, set())
            if len(order_ids) < HIGH_CANCELLATION_MIN_ORDERS:
                continue
            ratio = Decimal(len(cancelled)) / Decimal(len(order_ids))
            if ratio >= HIGH_CANCELLATION_RATIO:
                flagged.append(
                    {
                        "product_id": product_id,
                        "product_name": product_names.get(product_id, str(product_id)),
                        "orders": len(order_ids),
                        "cancelled": len(cancelled),
                        "ratio": str(ratio.quantize(Decimal("0.01"))),
                    }
                )
        flagged.sort(key=lambda entry: (-Decimal(entry["ratio"]), entry["product_name"]))
        return flagged


class InventoryReportService:
    def __init__(
        self,
        products: ProductRepository,
        stock_levels: StockLevelRepository,
        low_stock_policy: LowStockPolicy,
    ) -> None:
        self._products = products
        self._stock_levels = stock_levels
        self._low_stock = low_stock_policy

    def build(self, *, category_id: int | None = None) -> InventoryReportData:
        rows: list[VariantStock] = []
        total_on_hand = 0
        total_reserved = 0

        for product in self._products.list_all():
            if category_id is not None and product.category_id != category_id:
                continue
            for variant in product.variants:
                level = self._stock_levels.get_for_variant(variant.id)
                threshold = self._low_stock.threshold_for(level)
                row = VariantStock(
                    variant_id=variant.id,
                    sku=variant.sku,
                    product_id=product.id,
                    product_name=product.name,
                    category_id=product.category_id,
                    on_hand=level.on_hand,
                    reserved=level.reserved,
                    available=level.available,
                    low_stock_threshold=threshold,
                    is_low_stock=self._low_stock.is_low(level),
                )
                rows.append(row)
                total_on_hand += level.on_hand
                total_reserved += level.reserved

        rows.sort(key=lambda entry: entry.sku)
        low = [row for row in rows if row.is_low_stock]
        return InventoryReportData(
            variants=rows,
            total_on_hand=total_on_hand,
            total_reserved=total_reserved,
            total_available=total_on_hand - total_reserved,
            low_stock=low,
        )
