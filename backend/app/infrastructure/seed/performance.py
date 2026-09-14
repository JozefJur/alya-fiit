"""seed-performance: the large dataset for the profiling / benchmark lab.

Full size (scale 1.0):

    1 000 products · 2 500 variants · 20 000 customers
    50 000 orders · ~150 000 order items
    plus stock levels, movements, reservations, payments and audit events

Everything is written with bulk inserts (``executemany`` through
``Connection.execute`` with a list of parameter dicts), which keeps the whole
load in the seconds range instead of the tens of minutes an ORM-per-row insert
would take.

A fixed RNG seed makes the dataset identical on every machine, so measurements
taken against it are comparable.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete, insert
from sqlalchemy.engine import Engine

from app.application.services.auth import hash_password
from app.domain.entities.enums import (
    CartStatus,
    MovementType,
    OrderStatus,
    PaymentStatus,
    ReservationStatus,
    UserRole,
)
from app.infrastructure.adapters.payment_gateway import TOKEN_SUCCESS
from app.infrastructure.persistence.models import (
    AuditLogEntry,
    Cart,
    Category,
    Order,
    OrderItem,
    OrderStatusHistory,
    Payment,
    Product,
    ProductVariant,
    StockLevel,
    StockMovement,
    StockReservation,
    User,
)
from app.infrastructure.seed.accounts import SEED_ACCOUNTS

RANDOM_SEED = 20260101

#: Full-size targets; ``scale`` multiplies all of them.
FULL_PRODUCTS = 1_000
FULL_VARIANTS = 2_500
FULL_CUSTOMERS = 20_000
FULL_ORDERS = 50_000
FULL_ORDER_ITEMS = 150_000  # average 3 lines per order

CHUNK = 5_000  # rows per executemany batch

CATEGORY_NAMES = [
    "Laptops",
    "Monitors",
    "Keyboards",
    "Mice",
    "Headphones",
    "Cables & Adapters",
    "Storage",
    "Smartphones",
    "Networking",
    "Accessories",
]

BRANDS = [
    "Voltex",
    "Nordica",
    "PixelForge",
    "ClickPro",
    "AeroSound",
    "LinkUp",
    "DataVault",
    "Astra",
    "Corelith",
    "Zenka",
]

MODEL_WORDS = ["Pro", "Air", "Max", "Lite", "Studio", "Edge", "Core", "Prime", "Nova", "Flex"]

VARIANT_NAMES = ["Standard", "Black", "White", "16 GB", "32 GB", "512 GB", "1 TB", "2 TB"]

#: Order status distribution — mostly delivered, with a realistic tail.
STATUS_WEIGHTS: list[tuple[OrderStatus, int]] = [
    (OrderStatus.DELIVERED, 55),
    (OrderStatus.SHIPPED, 12),
    (OrderStatus.PAID, 10),
    (OrderStatus.PICKING, 5),
    (OrderStatus.READY_TO_SHIP, 4),
    (OrderStatus.CANCELLED, 6),
    (OrderStatus.PAYMENT_FAILED, 4),
    (OrderStatus.RETURNED, 2),
    (OrderStatus.REFUNDED, 2),
]

REVENUE_STATUSES = {
    OrderStatus.PAID,
    OrderStatus.PICKING,
    OrderStatus.READY_TO_SHIP,
    OrderStatus.SHIPPED,
    OrderStatus.DELIVERED,
    OrderStatus.RETURNED,
}


def _bulk_insert(engine: Engine, table: Any, rows: list[dict]) -> None:
    """Insert ``rows`` with executemany, in chunks, in a single transaction."""
    if not rows:
        return
    with engine.begin() as connection:
        for start in range(0, len(rows), CHUNK):
            connection.execute(insert(table), rows[start : start + CHUNK])


def _scaled(value: int, scale: float) -> int:
    return max(1, int(round(value * scale)))


def _payment_status_for(order_status: OrderStatus) -> PaymentStatus:
    if order_status == OrderStatus.PAYMENT_FAILED:
        return PaymentStatus.DECLINED
    if order_status == OrderStatus.REFUNDED:
        return PaymentStatus.REFUNDED
    return PaymentStatus.AUTHORIZED


def seed_performance(engine: Engine, *, scale: float = 1.0) -> dict[str, int]:
    """Populate an empty database with the performance dataset."""
    if scale <= 0:
        raise ValueError("scale must be positive")

    rng = random.Random(RANDOM_SEED)  # nosec B311 # reproducible test data, not crypto
    now = datetime(2026, 9, 1, 12, 0, 0)

    products_total = _scaled(FULL_PRODUCTS, scale)
    variants_total = _scaled(FULL_VARIANTS, scale)
    customers_total = _scaled(FULL_CUSTOMERS, scale)
    orders_total = _scaled(FULL_ORDERS, scale)
    items_target = _scaled(FULL_ORDER_ITEMS, scale)

    # ---- categories --------------------------------------------------
    categories = [
        {
            "id": index + 1,
            "name": name,
            "slug": name.lower().replace(" & ", "-").replace(" ", "-"),
            "description": f"{name} for the Alya-FIIT performance dataset",
            "is_active": True,
        }
        for index, name in enumerate(CATEGORY_NAMES)
    ]
    _bulk_insert(engine, Category.__table__, categories)

    # ---- users: fixed accounts first, then generated customers --------
    shared_hash = hash_password("Customer123!")  # hashing once keeps seeding fast
    users: list[dict] = []
    for index, (email, password, full_name, role) in enumerate(SEED_ACCOUNTS, start=1):
        users.append(
            {
                "id": index,
                "email": email,
                "password_hash": hash_password(password),
                "full_name": full_name,
                "role": role,
                "is_active": True,
                "created_at": now - timedelta(days=400),
            }
        )
    first_generated_id = len(users) + 1
    for offset in range(customers_total):
        user_id = first_generated_id + offset
        users.append(
            {
                "id": user_id,
                "email": f"customer{offset + 1:05d}@perf.alya.test",
                "password_hash": shared_hash,
                "full_name": f"Perf Customer {offset + 1:05d}",
                "role": UserRole.CUSTOMER,
                "is_active": True,
                "created_at": now - timedelta(days=rng.randint(1, 400)),
            }
        )
    _bulk_insert(engine, User.__table__, users)
    customer_ids = [first_generated_id + offset for offset in range(customers_total)]

    # ---- products and variants ---------------------------------------
    products: list[dict] = []
    for product_id in range(1, products_total + 1):
        brand = BRANDS[product_id % len(BRANDS)]
        word = MODEL_WORDS[product_id % len(MODEL_WORDS)]
        name = f"{brand} {word} {product_id}"
        products.append(
            {
                "id": product_id,
                "category_id": (product_id % len(CATEGORY_NAMES)) + 1,
                "name": name,
                "slug": f"{brand.lower()}-{word.lower()}-{product_id}",
                "description": f"Performance dataset product #{product_id}.",
                "brand": brand,
                "base_price": rng.choice(
                    ["9.90", "19.90", "49.00", "99.00", "199.00", "349.00", "899.00", "1299.00"]
                ),
                "vat_rate": "0.23",
                "is_active": product_id % 50 != 0,  # a few inactive products
                "created_at": now - timedelta(days=rng.randint(30, 400)),
                "updated_at": now,
            }
        )
    _bulk_insert(engine, Product.__table__, products)

    variants: list[dict] = []
    stock_levels: list[dict] = []
    for variant_id in range(1, variants_total + 1):
        product_id = ((variant_id - 1) % products_total) + 1
        variant_name = VARIANT_NAMES[variant_id % len(VARIANT_NAMES)]
        on_hand = rng.randint(0, 200)
        variants.append(
            {
                "id": variant_id,
                "product_id": product_id,
                "sku": f"PERF-{variant_id:06d}",
                "name": variant_name,
                "attributes_json": {"variant": variant_name},
                "price_delta": rng.choice(["0.00", "10.00", "25.00", "50.00", "-5.00"]),
                "is_active": variant_id % 40 != 0,
            }
        )
        stock_levels.append(
            {
                "variant_id": variant_id,
                "on_hand": on_hand,
                "reserved": 0,
                "low_stock_threshold": rng.choice([None, 3, 5, 10]),
            }
        )
    _bulk_insert(engine, ProductVariant.__table__, variants)
    _bulk_insert(engine, StockLevel.__table__, stock_levels)

    variant_price = {
        variant["id"]: (
            float(products[variant["product_id"] - 1]["base_price"]) + float(variant["price_delta"])
        )
        for variant in variants
    }

    # ---- orders, items, history, payments, reservations ---------------
    statuses: list[OrderStatus] = []
    for status, weight in STATUS_WEIGHTS:
        statuses.extend([status] * weight)

    orders: list[dict] = []
    order_items: list[dict] = []
    history: list[dict] = []
    payments: list[dict] = []
    reservations: list[dict] = []
    movements: list[dict] = []
    audit: list[dict] = []
    carts: list[dict] = []

    item_id = 0
    history_id = 0
    movement_id = 0
    reservation_id = 0
    audit_id = 0
    average_items = max(1, round(items_target / orders_total))

    for order_id in range(1, orders_total + 1):
        customer_id = customer_ids[rng.randrange(len(customer_ids))]
        status = statuses[rng.randrange(len(statuses))]
        created = now - timedelta(
            days=rng.randint(0, 365), hours=rng.randint(0, 23), minutes=rng.randint(0, 59)
        )
        # round(), not int(): truncation would bias the average downwards and
        # the dataset would end up well below the documented item count.
        line_count = max(1, min(6, round(rng.gauss(average_items, 1))))

        subtotal = 0.0
        vat_total = 0.0
        discount_total = 0.0
        has_discount = rng.random() < 0.25

        for _ in range(line_count):
            variant_id = rng.randint(1, variants_total)
            quantity = rng.randint(1, 3)
            unit_price = variant_price[variant_id]
            line_net = round(unit_price * quantity, 2)
            line_discount = round(line_net * 0.1, 2) if has_discount else 0.0
            line_vat = round((line_net - line_discount) * 0.23, 2)
            item_id += 1
            order_items.append(
                {
                    "id": item_id,
                    "order_id": order_id,
                    "variant_id": variant_id,
                    "product_name": f"Perf product for variant {variant_id}",
                    "sku": f"PERF-{variant_id:06d}",
                    "unit_price": f"{unit_price:.2f}",
                    "vat_rate": "0.23",
                    "quantity": quantity,
                    "discount_amount": f"{line_discount:.2f}",
                    "vat_amount": f"{line_vat:.2f}",
                    "line_total": f"{line_net - line_discount + line_vat:.2f}",
                }
            )
            subtotal += line_net
            discount_total += line_discount
            vat_total += line_vat

            # Orders still in fulfillment hold an active reservation.
            if status in (OrderStatus.PAID, OrderStatus.PICKING, OrderStatus.READY_TO_SHIP):
                reservation_id += 1
                reservations.append(
                    {
                        "id": reservation_id,
                        "order_id": order_id,
                        "variant_id": variant_id,
                        "quantity": quantity,
                        "status": ReservationStatus.ACTIVE,
                        "created_at": created,
                        "released_at": None,
                    }
                )
            if status in (OrderStatus.SHIPPED, OrderStatus.DELIVERED):
                movement_id += 1
                movements.append(
                    {
                        "id": movement_id,
                        "variant_id": variant_id,
                        "movement_type": MovementType.SHIPMENT,
                        "quantity": -quantity,
                        "reason": "Order shipped",
                        "reference": f"AF-PERF-{order_id:06d}",
                        "actor_user_id": 2,
                        "created_at": created + timedelta(days=1),
                    }
                )

        grand_total = subtotal - discount_total + vat_total
        shipped_at = (
            created + timedelta(days=1)
            if status in (OrderStatus.SHIPPED, OrderStatus.DELIVERED)
            else None
        )
        delivered_at = created + timedelta(days=3) if status == OrderStatus.DELIVERED else None
        orders.append(
            {
                "id": order_id,
                "order_number": f"AF-PERF-{order_id:06d}",
                "customer_id": customer_id,
                "status": status,
                "subtotal": f"{subtotal:.2f}",
                "discount_total": f"{discount_total:.2f}",
                "vat_total": f"{vat_total:.2f}",
                "grand_total": f"{grand_total:.2f}",
                "coupon_code": "PERF10" if has_discount else None,
                "ship_to_name": f"Perf Customer {customer_id}",
                "ship_street": "Ilkovičova 2",
                "ship_city": "Bratislava",
                "ship_zip": "84216",
                "ship_country": "SK",
                "created_at": created,
                "updated_at": created,
                "shipped_at": shipped_at,
                "delivered_at": delivered_at,
            }
        )

        history_id += 1
        history.append(
            {
                "id": history_id,
                "order_id": order_id,
                "from_status": OrderStatus.PENDING_PAYMENT,
                "to_status": status,
                "event": "seeded",
                "actor_user_id": None,
                "note": "performance dataset",
                "created_at": created,
            }
        )

        payments.append(
            {
                "id": order_id,
                "order_id": order_id,
                "amount": f"{grand_total:.2f}",
                "status": _payment_status_for(status),
                "payment_token": TOKEN_SUCCESS,
                "idempotency_key": f"AF-PERF-{order_id:06d}-p1",
                "gateway_reference": f"sim-perf-{order_id:06d}",
                "created_at": created,
                "updated_at": created,
            }
        )

        audit_id += 1
        audit.append(
            {
                "id": audit_id,
                "actor_user_id": customer_id,
                "action": "order.created",
                "entity_type": "order",
                "entity_id": str(order_id),
                "details_json": {"grand_total": f"{grand_total:.2f}", "status": status.value},
                "created_at": created,
            }
        )

    # Reserved quantities must match the reservations we just created.
    reserved_per_variant: dict[int, int] = {}
    for reservation in reservations:
        variant = reservation["variant_id"]
        reserved_per_variant[variant] = (
            reserved_per_variant.get(variant, 0) + reservation["quantity"]
        )
    for level in stock_levels:
        reserved = reserved_per_variant.get(level["variant_id"], 0)
        level["reserved"] = reserved
        # Keep the invariant available >= 0 (on_hand >= reserved).
        if level["on_hand"] < reserved:
            level["on_hand"] = reserved + rng.randint(0, 20)

    # One active cart per fixed seed customer keeps the app usable afterwards.
    for index, (_email, _password, _name, role) in enumerate(SEED_ACCOUNTS, start=1):
        if role == UserRole.CUSTOMER:
            carts.append(
                {
                    "id": len(carts) + 1,
                    "customer_id": index,
                    "status": CartStatus.ACTIVE,
                    "coupon_code": None,
                    "created_at": now,
                    "updated_at": now,
                }
            )

    _bulk_insert(engine, Order.__table__, orders)
    _bulk_insert(engine, OrderItem.__table__, order_items)
    _bulk_insert(engine, OrderStatusHistory.__table__, history)
    _bulk_insert(engine, Payment.__table__, payments)
    _bulk_insert(engine, StockReservation.__table__, reservations)
    _bulk_insert(engine, StockMovement.__table__, movements)
    _bulk_insert(engine, AuditLogEntry.__table__, audit)
    _bulk_insert(engine, Cart.__table__, carts)

    # stock levels were mutated after their first insert → rewrite them
    with engine.begin() as connection:
        connection.execute(delete(StockLevel))
    _bulk_insert(engine, StockLevel.__table__, stock_levels)

    return {
        "categories": len(categories),
        "products": len(products),
        "variants": len(variants),
        "users": len(users),
        "orders": len(orders),
        "order_items": len(order_items),
        "payments": len(payments),
        "reservations": len(reservations),
        "stock_movements": len(movements),
        "audit_entries": len(audit),
        "revenue_orders": sum(1 for order in orders if order["status"] in REVENUE_STATUSES),
    }
