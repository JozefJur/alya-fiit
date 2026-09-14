"""Tax, discount and cart-price calculation."""

from decimal import Decimal

import pytest

from app.application.services.pricing import (
    CartPriceCalculator,
    DiscountCalculator,
    PricingService,
    TaxCalculator,
)
from app.domain.entities.enums import DiscountType
from app.domain.errors import ValidationError
from app.domain.value_objects.money import Money
from app.tests.fixtures.doubles import FakeCoupon, FakeProduct, FakeVariant, line


class TestTaxCalculator:
    def test_vat_of_net_amount(self):
        assert TaxCalculator().vat_of(Money.of("100.00"), Decimal("0.23")).amount == Decimal(
            "23.00"
        )

    def test_gross_is_net_plus_vat(self):
        assert TaxCalculator().gross_of(Money.of("100.00"), Decimal("0.20")).amount == Decimal(
            "120.00"
        )

    def test_zero_rate_is_allowed(self):
        assert TaxCalculator().vat_of(Money.of("50.00"), Decimal("0")).is_zero

    @pytest.mark.parametrize("rate", ["-0.01", "1", "1.5"])
    def test_rate_outside_range_is_rejected(self, rate: str):
        with pytest.raises(ValidationError):
            TaxCalculator().validate_rate(Decimal(rate))

    def test_non_decimal_rate_is_rejected(self):
        with pytest.raises(ValidationError):
            TaxCalculator().validate_rate(0.23)  # type: ignore[arg-type]


class TestDiscountCalculator:
    def test_percent_discount(self):
        calculator = DiscountCalculator()
        assert calculator.percent_discount(Money.of("200.00"), Decimal("15")).amount == Decimal(
            "30.00"
        )

    @pytest.mark.parametrize("percent", ["0", "-5", "101"])
    def test_percent_outside_range_is_rejected(self, percent: str):
        with pytest.raises(ValidationError):
            DiscountCalculator().percent_discount(Money.of("100.00"), Decimal(percent))

    def test_fixed_discount_is_capped_at_the_eligible_subtotal(self):
        calculator = DiscountCalculator()
        assert calculator.fixed_discount(Money.of("20.00"), Decimal("50.00")).amount == Decimal(
            "20.00"
        )

    def test_fixed_discount_must_be_positive(self):
        with pytest.raises(ValidationError):
            DiscountCalculator().fixed_discount(Money.of("10.00"), Decimal("0"))

    def test_allocation_never_loses_a_cent(self):
        calculator = DiscountCalculator()
        parts = calculator.allocate_over_lines(
            Money.of("10.00"), [Money.of("33.33"), Money.of("33.33"), Money.of("33.34")]
        )
        assert sum(part.cents for part in parts) == 1000

    def test_zero_discount_allocates_zeros(self):
        parts = DiscountCalculator().allocate_over_lines(
            Money.zero(), [Money.of("10.00"), Money.of("5.00")]
        )
        assert all(part.is_zero for part in parts)

    def test_negative_discount_is_rejected(self):
        with pytest.raises(ValidationError):
            DiscountCalculator().allocate_over_lines(Money.of("-1.00"), [Money.of("10.00")])


class TestPricingService:
    def test_effective_price_adds_variant_delta(self):
        service = PricingService()
        product = FakeProduct(base_price=Decimal("100.00"))
        variant = FakeVariant(price_delta=Decimal("25.50"))
        assert service.effective_unit_price(product, variant).amount == Decimal("125.50")

    def test_negative_delta_reduces_the_price(self):
        service = PricingService()
        product = FakeProduct(base_price=Decimal("100.00"))
        variant = FakeVariant(price_delta=Decimal("-40.00"))
        assert service.effective_unit_price(product, variant).amount == Decimal("60.00")

    def test_non_positive_effective_price_is_rejected(self):
        service = PricingService()
        product = FakeProduct(base_price=Decimal("100.00"))
        variant = FakeVariant(price_delta=Decimal("-100.00"))
        with pytest.raises(ValidationError):
            service.effective_unit_price(product, variant)

    def test_build_line_carries_snapshot_data(self):
        built = PricingService().build_line(
            product=FakeProduct(),
            variant=FakeVariant(sku="ABC"),
            category_id=3,
            product_name="Thing — Big",
            quantity=2,
        )
        assert built.sku == "ABC"
        assert built.category_id == 3
        assert built.quantity == 2
        assert built.line_net.amount == Decimal("200.00")


class TestCartPriceCalculator:
    def test_totals_without_a_coupon(self):
        breakdown = CartPriceCalculator().price([line(unit_price="99.00", quantity=2)])
        assert breakdown.subtotal.amount == Decimal("198.00")
        assert breakdown.discount_total.is_zero
        assert breakdown.vat_total.amount == Decimal("45.54")
        assert breakdown.grand_total.amount == Decimal("243.54")

    def test_percent_coupon_reduces_taxable_base(self):
        breakdown = CartPriceCalculator().price(
            [line(unit_price="99.00", quantity=2)], FakeCoupon(value=Decimal("10"))
        )
        # net 198.00 − 19.80 = 178.20; VAT 23 % = 40.99; total = 219.19
        assert breakdown.discount_total.amount == Decimal("19.80")
        assert breakdown.vat_total.amount == Decimal("40.99")
        assert breakdown.grand_total.amount == Decimal("219.19")

    def test_fixed_coupon_is_allocated_across_lines(self):
        breakdown = CartPriceCalculator().price(
            [line(unit_price="60.00", sku="A"), line(unit_price="40.00", sku="B")],
            FakeCoupon(discount_type=DiscountType.FIXED, value=Decimal("10.00")),
        )
        discounts = [priced.discount.amount for priced in breakdown.lines]
        assert discounts == [Decimal("6.00"), Decimal("4.00")]
        assert breakdown.discount_total.amount == Decimal("10.00")

    def test_category_coupon_only_discounts_eligible_lines(self):
        breakdown = CartPriceCalculator().price(
            [
                line(unit_price="100.00", category_id=1, sku="IN"),
                line(unit_price="100.00", category_id=2, sku="OUT"),
            ],
            FakeCoupon(value=Decimal("10"), category_id=1),
        )
        by_sku = {priced.source.sku: priced for priced in breakdown.lines}
        assert by_sku["IN"].discount.amount == Decimal("10.00")
        assert by_sku["OUT"].discount.is_zero
        assert breakdown.discount_total.amount == Decimal("10.00")

    def test_coupon_matching_no_line_leaves_totals_untouched(self):
        breakdown = CartPriceCalculator().price(
            [line(unit_price="100.00", category_id=2)],
            FakeCoupon(value=Decimal("50"), category_id=99),
        )
        assert breakdown.discount_total.is_zero
        assert breakdown.grand_total.amount == Decimal("123.00")

    def test_fixed_coupon_cannot_exceed_the_cart(self):
        breakdown = CartPriceCalculator().price(
            [line(unit_price="20.00")],
            FakeCoupon(discount_type=DiscountType.FIXED, value=Decimal("100.00")),
        )
        assert breakdown.discount_total.amount == Decimal("20.00")
        assert breakdown.grand_total.is_zero

    def test_empty_cart_prices_to_zero(self):
        breakdown = CartPriceCalculator().price([])
        assert breakdown.subtotal.is_zero
        assert breakdown.grand_total.is_zero
        assert breakdown.lines == ()

    def test_mixed_vat_rates_are_summed_per_line(self):
        breakdown = CartPriceCalculator().price(
            [
                line(unit_price="100.00", vat_rate="0.23", sku="HIGH"),
                line(unit_price="100.00", vat_rate="0.05", sku="LOW"),
            ]
        )
        assert breakdown.vat_total.amount == Decimal("28.00")

    def test_line_totals_add_up_to_the_grand_total(self):
        breakdown = CartPriceCalculator().price(
            [line(unit_price="33.33", quantity=3, sku="A"), line(unit_price="9.99", sku="B")],
            FakeCoupon(discount_type=DiscountType.FIXED, value=Decimal("7.77")),
        )
        summed = sum(priced.line_total.cents for priced in breakdown.lines)
        assert summed == breakdown.grand_total.cents
