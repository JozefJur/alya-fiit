"""Catalog activation, availability, cart-item and low-stock rules."""

import pytest

from app.domain.errors import (
    InsufficientStockError,
    InvalidQuantityError,
    ProductNotAvailableError,
)
from app.domain.policies.cart import CartItemPolicy, QuantityValidator
from app.domain.policies.catalog import ProductActivationPolicy, VariantAvailabilityPolicy
from app.domain.policies.inventory import LowStockPolicy
from app.tests.fixtures.doubles import (
    FakeCategory,
    FakeProduct,
    FakeStockLevel,
    FakeVariant,
)


class TestProductActivationPolicy:
    def test_all_active_is_orderable(self):
        policy = ProductActivationPolicy()
        assert policy.is_orderable(FakeCategory(), FakeProduct(), FakeVariant())
        assert policy.inactive_reason(FakeCategory(), FakeProduct(), FakeVariant()) is None

    @pytest.mark.parametrize(
        ("category", "product", "variant", "reason"),
        [
            (FakeCategory(is_active=False), FakeProduct(), FakeVariant(), "category_inactive"),
            (FakeCategory(), FakeProduct(is_active=False), FakeVariant(), "product_inactive"),
            (FakeCategory(), FakeProduct(), FakeVariant(is_active=False), "variant_inactive"),
        ],
    )
    def test_inactive_reason_names_the_first_problem(self, category, product, variant, reason):
        assert ProductActivationPolicy().inactive_reason(category, product, variant) == reason

    def test_ensure_orderable_raises_with_the_reason(self):
        policy = ProductActivationPolicy()
        with pytest.raises(ProductNotAvailableError) as error:
            policy.ensure_orderable(FakeCategory(), FakeProduct(is_active=False), FakeVariant())
        assert error.value.details["reason"] == "product_inactive"

    def test_category_precedes_product_in_the_reported_reason(self):
        reason = ProductActivationPolicy().inactive_reason(
            FakeCategory(is_active=False), FakeProduct(is_active=False), FakeVariant()
        )
        assert reason == "category_inactive"


class TestVariantAvailabilityPolicy:
    def test_available_is_on_hand_minus_reserved(self):
        policy = VariantAvailabilityPolicy()
        assert policy.available(FakeStockLevel(on_hand=10, reserved=4)) == 6

    def test_requested_quantity_within_availability(self):
        policy = VariantAvailabilityPolicy()
        assert policy.is_available(FakeStockLevel(on_hand=5, reserved=0), 5)

    def test_requested_quantity_above_availability(self):
        policy = VariantAvailabilityPolicy()
        assert not policy.is_available(FakeStockLevel(on_hand=5, reserved=1), 5)

    def test_zero_or_negative_request_is_not_available(self):
        policy = VariantAvailabilityPolicy()
        assert not policy.is_available(FakeStockLevel(), 0)
        assert not policy.is_available(FakeStockLevel(), -1)

    def test_ensure_available_reports_what_is_left(self):
        policy = VariantAvailabilityPolicy()
        with pytest.raises(InsufficientStockError) as error:
            policy.ensure_available(FakeStockLevel(on_hand=3, reserved=1), 3)
        assert error.value.details == {"variant_id": 10, "requested": 3, "available": 2}


class TestQuantityValidator:
    def test_valid_quantity_passes(self):
        QuantityValidator(10).validate(1)
        QuantityValidator(10).validate(10)

    @pytest.mark.parametrize("quantity", [0, -1])
    def test_non_positive_quantity_is_rejected(self, quantity: int):
        with pytest.raises(InvalidQuantityError):
            QuantityValidator(10).validate(quantity)

    def test_above_limit_is_rejected_with_the_limit(self):
        with pytest.raises(InvalidQuantityError) as error:
            QuantityValidator(10).validate(11)
        assert error.value.details["max_per_line"] == 10

    def test_non_integer_quantity_is_rejected(self):
        with pytest.raises(InvalidQuantityError):
            QuantityValidator(10).validate(2.5)  # type: ignore[arg-type]

    def test_bool_is_not_accepted_as_a_quantity(self):
        # bool is an int subclass in Python — the validator rejects it explicitly.
        with pytest.raises(InvalidQuantityError):
            QuantityValidator(10).validate(True)

    def test_limit_below_one_is_a_programming_error(self):
        with pytest.raises(ValueError):
            QuantityValidator(0)


class TestCartItemPolicy:
    def _policy(self) -> CartItemPolicy:
        return CartItemPolicy(QuantityValidator(10))

    def test_valid_line_passes_every_rule(self):
        self._policy().validate_line(
            category=FakeCategory(),
            product=FakeProduct(),
            variant=FakeVariant(),
            stock=FakeStockLevel(on_hand=5),
            quantity=2,
        )

    def test_quantity_rule_runs_before_availability(self):
        with pytest.raises(InvalidQuantityError):
            self._policy().validate_line(
                category=FakeCategory(),
                product=FakeProduct(),
                variant=FakeVariant(),
                stock=FakeStockLevel(on_hand=0),
                quantity=99,
            )

    def test_inactive_product_is_rejected_before_stock(self):
        with pytest.raises(ProductNotAvailableError):
            self._policy().validate_line(
                category=FakeCategory(),
                product=FakeProduct(is_active=False),
                variant=FakeVariant(),
                stock=FakeStockLevel(on_hand=0),
                quantity=1,
            )

    def test_insufficient_stock_is_rejected(self):
        with pytest.raises(InsufficientStockError):
            self._policy().validate_line(
                category=FakeCategory(),
                product=FakeProduct(),
                variant=FakeVariant(),
                stock=FakeStockLevel(on_hand=2, reserved=1),
                quantity=2,
            )


class TestLowStockPolicy:
    def test_variant_threshold_overrides_the_default(self):
        policy = LowStockPolicy(default_threshold=5)
        assert policy.threshold_for(FakeStockLevel(low_stock_threshold=1)) == 1

    def test_default_threshold_is_used_when_unset(self):
        policy = LowStockPolicy(default_threshold=5)
        assert policy.threshold_for(FakeStockLevel(low_stock_threshold=None)) == 5

    def test_not_low_above_threshold(self):
        policy = LowStockPolicy(default_threshold=5)
        assert not policy.is_low(FakeStockLevel(on_hand=6, reserved=0))

    def test_negative_default_threshold_is_a_programming_error(self):
        with pytest.raises(ValueError):
            LowStockPolicy(default_threshold=-1)
