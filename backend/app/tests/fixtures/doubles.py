"""Hand-written test doubles for unit tests (no ORM, no database, no I/O)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from app.domain.entities.enums import DiscountType, OrderStatus
from app.domain.entities.pricing import PricingLineInput
from app.domain.value_objects.money import Money


@dataclass
class FakeCategory:
    id: int = 1
    is_active: bool = True


@dataclass
class FakeProduct:
    id: int = 1
    category_id: int = 1
    is_active: bool = True
    base_price: Decimal = Decimal("100.00")
    vat_rate: Decimal = Decimal("0.23")


@dataclass
class FakeVariant:
    id: int = 10
    product_id: int = 1
    is_active: bool = True
    price_delta: Decimal = Decimal("0.00")
    sku: str = "SKU-1"


@dataclass
class FakeStockLevel:
    variant_id: int = 10
    on_hand: int = 10
    reserved: int = 0
    low_stock_threshold: int | None = None


@dataclass
class FakeCoupon:
    code: str = "SAVE10"
    discount_type: DiscountType = DiscountType.PERCENT
    value: Decimal = Decimal("10")
    valid_from: datetime = datetime(2026, 1, 1)
    valid_until: datetime = datetime(2026, 12, 31)
    min_cart_total: Decimal | None = None
    max_uses: int | None = None
    used_count: int = 0
    category_id: int | None = None
    is_active: bool = True


@dataclass
class FakeOrder:
    id: int = 100
    customer_id: int = 7
    status: OrderStatus = OrderStatus.PAID
    delivered_at: datetime | None = None


@dataclass
class RecordedAudit:
    actor_user_id: int | None
    action: str
    entity_type: str
    entity_id: str
    details: dict


class FakeAuditLog:
    """Stands in for ``AuditLogService`` and remembers what was recorded."""

    def __init__(self) -> None:
        self.entries: list[RecordedAudit] = []

    def record(
        self,
        *,
        actor_user_id: int | None,
        action: str,
        entity_type: str,
        entity_id: int | str,
        details: dict | None = None,
    ) -> RecordedAudit:
        entry = RecordedAudit(
            actor_user_id=actor_user_id,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id),
            details=details or {},
        )
        self.entries.append(entry)
        return entry

    def actions(self) -> list[str]:
        return [entry.action for entry in self.entries]


@dataclass
class FakeClock:
    instant: datetime = field(default_factory=lambda: datetime(2026, 6, 15, 12, 0, 0))

    def now(self) -> datetime:
        return self.instant


def line(
    *,
    unit_price: str = "100.00",
    quantity: int = 1,
    vat_rate: str = "0.23",
    category_id: int = 1,
    variant_id: int = 10,
    sku: str = "SKU-1",
) -> PricingLineInput:
    """Convenience builder for pricing tests."""
    return PricingLineInput(
        variant_id=variant_id,
        product_id=1,
        category_id=category_id,
        product_name=f"Product {sku}",
        sku=sku,
        unit_price=Money.of(unit_price),
        vat_rate=Decimal(vat_rate),
        quantity=quantity,
    )
