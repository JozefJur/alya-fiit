"""Coupon eligibility and validity rules (server-side source of truth)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from app.domain.entities.interfaces import CouponLike
from app.domain.entities.pricing import PricingLineInput
from app.domain.errors import CouponNotEligibleError
from app.domain.value_objects.money import Money


class CouponEligibilityPolicy:
    """Which cart lines a coupon applies to (category restriction)."""

    def eligible_lines(
        self, coupon: CouponLike, lines: list[PricingLineInput]
    ) -> list[PricingLineInput]:
        if coupon.category_id is None:
            return list(lines)
        return [line for line in lines if line.category_id == coupon.category_id]

    def eligible_subtotal(self, coupon: CouponLike, lines: list[PricingLineInput]) -> Money:
        eligible = self.eligible_lines(coupon, lines)
        total = Money.zero()
        for line in eligible:
            total = total + line.line_net + line.line_net.percentage(line.vat_rate)
        return total


class CouponValidator:
    """Full validity check; raises ``CouponNotEligibleError`` with a reason code.

    Reason codes: ``inactive``, ``not_started``, ``expired``, ``exhausted``,
    ``below_minimum``, ``no_eligible_items``.
    """

    def __init__(self, eligibility: CouponEligibilityPolicy | None = None) -> None:
        self.eligibility = eligibility or CouponEligibilityPolicy()

    def validate(self, coupon: CouponLike, lines: list[PricingLineInput], now: datetime) -> None:
        if not coupon.is_active:
            raise CouponNotEligibleError("This coupon is not active.", reason="inactive")
        if now < coupon.valid_from:
            raise CouponNotEligibleError("This coupon is not valid yet.", reason="not_started")
        if now > coupon.valid_until:
            raise CouponNotEligibleError("This coupon has expired.", reason="expired")
        if coupon.max_uses is not None and coupon.used_count >= coupon.max_uses:
            raise CouponNotEligibleError(
                "This coupon has reached its usage limit.", reason="exhausted"
            )

        eligible_subtotal = self.eligibility.eligible_subtotal(coupon, lines)
        if eligible_subtotal.is_zero:
            raise CouponNotEligibleError(
                "No items in the cart are eligible for this coupon.",
                reason="no_eligible_items",
            )
        min_total = coupon.min_cart_total
        if min_total is not None and eligible_subtotal < Money(Decimal(min_total)):
            raise CouponNotEligibleError(
                f"Eligible cart value must be at least {Money(Decimal(min_total))}.",
                reason="below_minimum",
                details={
                    "min_cart_total": str(min_total),
                    "eligible_subtotal": str(eligible_subtotal.amount),
                },
            )
