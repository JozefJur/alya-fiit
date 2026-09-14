"""Server-side pricing pipeline: VAT, discounts, and full cart/order breakdowns.

The server is the single source of truth — the frontend only displays what
these classes compute (BG-03).
"""

from __future__ import annotations

from decimal import Decimal

from app.domain.entities.interfaces import CouponLike, ProductLike, VariantLike
from app.domain.entities.pricing import PriceBreakdown, PricedLine, PricingLineInput
from app.domain.errors import ValidationError
from app.domain.policies.coupons import CouponEligibilityPolicy
from app.domain.value_objects.money import Money

_MAX_RATE = Decimal("1")


class TaxCalculator:
    """VAT arithmetic on net amounts (rate is a fraction, e.g. 0.23)."""

    def validate_rate(self, rate: Decimal) -> None:
        if not isinstance(rate, Decimal):
            raise ValidationError("VAT rate must be a decimal fraction.")
        if rate < 0 or rate >= _MAX_RATE:
            raise ValidationError("VAT rate must be within <0, 1).", details={"rate": str(rate)})

    def vat_of(self, net: Money, rate: Decimal) -> Money:
        self.validate_rate(rate)
        return net.percentage(rate)

    def gross_of(self, net: Money, rate: Decimal) -> Money:
        return net + self.vat_of(net, rate)


class DiscountCalculator:
    """Computes coupon discount amounts and allocates them across lines."""

    def percent_discount(self, eligible_subtotal: Money, percent_value: Decimal) -> Money:
        if percent_value <= 0 or percent_value > 100:
            raise ValidationError(
                "Percent discount must be within (0, 100>.",
                details={"value": str(percent_value)},
            )
        return eligible_subtotal.percentage(percent_value / 100)

    def fixed_discount(self, eligible_subtotal: Money, amount: Decimal) -> Money:
        if amount <= 0:
            raise ValidationError(
                "Fixed discount must be positive.", details={"value": str(amount)}
            )
        return Money(amount).min(eligible_subtotal)

    def allocate_over_lines(self, discount: Money, line_nets: list[Money]) -> list[Money]:
        """Split a discount across lines proportionally to their net value.

        Uses largest-remainder allocation so the parts sum exactly to the
        discount (no lost cents)."""
        if discount.is_negative:
            raise ValidationError("Discount cannot be negative.")
        if discount.is_zero or not line_nets:
            return [Money.zero() for _ in line_nets]
        weights = [net.cents for net in line_nets]
        return discount.allocate(weights)


class PricingService:
    """Effective prices and pricing-line construction from catalog objects."""

    def effective_unit_price(self, product: ProductLike, variant: VariantLike) -> Money:
        price = Money(product.base_price) + Money(variant.price_delta)
        if price.is_zero or price.is_negative:
            raise ValidationError(
                "Effective price must be positive.",
                details={"sku": variant.sku, "price": str(price.amount)},
            )
        return price

    def build_line(
        self,
        *,
        product: ProductLike,
        variant: VariantLike,
        category_id: int,
        product_name: str,
        quantity: int,
    ) -> PricingLineInput:
        return PricingLineInput(
            variant_id=variant.id,
            product_id=product.id,
            category_id=category_id,
            product_name=product_name,
            sku=variant.sku,
            unit_price=self.effective_unit_price(product, variant),
            vat_rate=product.vat_rate,
            quantity=quantity,
        )


class CartPriceCalculator:
    """Full breakdown: subtotal → discount → per-line VAT → grand total.

    Assumes the coupon (when present) has already passed ``CouponValidator``;
    eligibility filtering is still applied here to discount the right lines.
    """

    def __init__(
        self,
        tax_calculator: TaxCalculator | None = None,
        discount_calculator: DiscountCalculator | None = None,
        eligibility: CouponEligibilityPolicy | None = None,
    ) -> None:
        self.tax = tax_calculator or TaxCalculator()
        self.discounts = discount_calculator or DiscountCalculator()
        self.eligibility = eligibility or CouponEligibilityPolicy()

    def price(
        self, lines: list[PricingLineInput], coupon: CouponLike | None = None
    ) -> PriceBreakdown:
        subtotal = Money.zero()
        for line in lines:
            subtotal = subtotal + line.line_net

        line_discounts = [Money.zero() for _ in lines]
        discount_total = Money.zero()
        coupon_code: str | None = None

        if coupon is not None and lines:
            coupon_code = coupon.code
            eligible_indexes = [
                index
                for index, line in enumerate(lines)
                if coupon.category_id is None or line.category_id == coupon.category_id
            ]
            eligible_nets = [lines[i].line_net for i in eligible_indexes]
            eligible_subtotal = Money.zero()
            for net in eligible_nets:
                eligible_subtotal = eligible_subtotal + net

            if eligible_indexes and not eligible_subtotal.is_zero:
                if coupon.discount_type.value == "percent":
                    discount_total = self.discounts.percent_discount(
                        eligible_subtotal, coupon.value
                    )
                else:
                    discount_total = self.discounts.fixed_discount(eligible_subtotal, coupon.value)
                allocated = self.discounts.allocate_over_lines(discount_total, eligible_nets)
                for position, index in enumerate(eligible_indexes):
                    line_discounts[index] = allocated[position]

        priced_lines: list[PricedLine] = []
        vat_total = Money.zero()
        for line, discount in zip(lines, line_discounts, strict=True):
            taxable = line.line_net - discount
            vat = self.tax.vat_of(taxable, line.vat_rate)
            priced_lines.append(
                PricedLine(
                    source=line,
                    discount=discount,
                    vat=vat,
                    line_total=taxable + vat,
                )
            )
            vat_total = vat_total + vat

        grand_total = subtotal - discount_total + vat_total
        return PriceBreakdown(
            lines=tuple(priced_lines),
            subtotal=subtotal,
            discount_total=discount_total,
            vat_total=vat_total,
            grand_total=grand_total,
            coupon_code=coupon_code,
        )
