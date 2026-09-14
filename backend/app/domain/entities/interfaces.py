"""Structural typing for domain rules.

Policies and calculators accept anything with these attributes (ORM models,
test doubles, plain dataclasses) — the domain layer never imports SQLAlchemy.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Protocol

from app.domain.entities.enums import DiscountType, OrderStatus


class CategoryLike(Protocol):
    id: int
    is_active: bool


class ProductLike(Protocol):
    id: int
    category_id: int
    is_active: bool
    base_price: Decimal
    vat_rate: Decimal


class VariantLike(Protocol):
    id: int
    product_id: int
    is_active: bool
    price_delta: Decimal
    sku: str


class StockLevelLike(Protocol):
    variant_id: int
    on_hand: int
    reserved: int
    low_stock_threshold: int | None


class CouponLike(Protocol):
    code: str
    discount_type: DiscountType
    value: Decimal  # percent value (10 == 10 %) or fixed net amount in EUR
    valid_from: datetime
    valid_until: datetime
    min_cart_total: Decimal | None
    max_uses: int | None
    used_count: int
    category_id: int | None
    is_active: bool


class OrderLike(Protocol):
    id: int
    customer_id: int
    status: OrderStatus
    delivered_at: datetime | None
