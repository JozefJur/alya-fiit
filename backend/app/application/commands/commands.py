"""Input DTOs for use cases (plain dataclasses, independent of FastAPI schemas)."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(frozen=True)
class ShippingAddress:
    name: str
    street: str
    city: str
    zip_code: str
    country: str = "SK"


@dataclass(frozen=True)
class CheckoutCommand:
    customer_id: int
    payment_token: str
    address: ShippingAddress
    coupon_code: str | None = None


@dataclass(frozen=True)
class PaymentCallbackCommand:
    """Replay of a gateway callback (or the first processing of one)."""

    idempotency_key: str
    status: str  # authorized | declined | timeout
    gateway_reference: str | None = None
    message: str = ""


@dataclass(frozen=True)
class StockAdjustmentCommand:
    variant_id: int
    quantity_change: int  # signed delta applied to on_hand
    reason: str
    actor_user_id: int


@dataclass(frozen=True)
class InventoryImportRow:
    line_number: int
    sku: str
    on_hand: str  # raw CSV values; validated by the import service
    low_stock_threshold: str = ""


@dataclass(frozen=True)
class ProductImportRow:
    line_number: int
    category_slug: str
    name: str
    brand: str
    base_price: str
    vat_rate: str = ""
    description: str = ""


@dataclass(frozen=True)
class CatalogQuery:
    search: str | None = None
    category_id: int | None = None
    brand: str | None = None
    price_min: Decimal | None = None
    price_max: Decimal | None = None
    in_stock_only: bool = False
    include_inactive: bool = False  # admin listings only
    sort: str = "name"
    page: int = 1
    page_size: int = 12


@dataclass(frozen=True)
class ReportQuery:
    date_from: str  # ISO date (inclusive)
    date_to: str  # ISO date (inclusive)
    category_id: int | None = None
    low_stock_only: bool = False
    top_limit: int = 10
    extras: dict[str, str] = field(default_factory=dict)
