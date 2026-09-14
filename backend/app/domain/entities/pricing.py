"""Pure pricing data structures passed between services (no ORM, no I/O)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.domain.value_objects.money import Money


@dataclass(frozen=True)
class PricingLineInput:
    """One cart/order line as the pricing pipeline sees it."""

    variant_id: int
    product_id: int
    category_id: int
    product_name: str
    sku: str
    unit_price: Money  # net effective price (base price + variant delta)
    vat_rate: Decimal  # fraction, e.g. Decimal("0.23")
    quantity: int

    @property
    def line_net(self) -> Money:
        return self.unit_price.times(self.quantity)


@dataclass(frozen=True)
class PricedLine:
    source: PricingLineInput
    discount: Money  # this line's allocated share of the coupon discount
    vat: Money  # VAT on (line_net - discount)
    line_total: Money  # line_net - discount + vat (gross)

    @property
    def line_net(self) -> Money:
        return self.source.line_net


@dataclass(frozen=True)
class PriceBreakdown:
    lines: tuple[PricedLine, ...]
    subtotal: Money  # Σ line_net (before discount, net)
    discount_total: Money
    vat_total: Money
    grand_total: Money  # subtotal - discount + vat
    coupon_code: str | None = None
