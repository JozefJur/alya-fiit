"""Coupon eligibility and validity rules."""

from datetime import datetime
from decimal import Decimal

import pytest

from app.domain.errors import CouponNotEligibleError
from app.domain.policies.coupons import CouponEligibilityPolicy, CouponValidator
from app.tests.fixtures.doubles import FakeCoupon, line

NOW = datetime(2026, 6, 15, 12, 0, 0)


class TestCouponEligibilityPolicy:
    def test_unrestricted_coupon_covers_every_line(self):
        policy = CouponEligibilityPolicy()
        lines = [line(category_id=1, sku="A"), line(category_id=2, sku="B")]
        assert len(policy.eligible_lines(FakeCoupon(), lines)) == 2

    def test_category_restriction_filters_lines(self):
        policy = CouponEligibilityPolicy()
        lines = [line(category_id=1, sku="A"), line(category_id=2, sku="B")]
        eligible = policy.eligible_lines(FakeCoupon(category_id=2), lines)
        assert [item.sku for item in eligible] == ["B"]

    def test_eligible_subtotal_of_empty_cart_is_zero(self):
        assert CouponEligibilityPolicy().eligible_subtotal(FakeCoupon(), []).is_zero


class TestCouponValidator:
    def test_valid_coupon_passes(self):
        CouponValidator().validate(FakeCoupon(), [line()], NOW)

    def test_inactive_coupon_is_rejected(self):
        with pytest.raises(CouponNotEligibleError) as error:
            CouponValidator().validate(FakeCoupon(is_active=False), [line()], NOW)
        assert error.value.reason == "inactive"

    def test_coupon_before_its_validity_window(self):
        coupon = FakeCoupon(valid_from=datetime(2026, 7, 1))
        with pytest.raises(CouponNotEligibleError) as error:
            CouponValidator().validate(coupon, [line()], NOW)
        assert error.value.reason == "not_started"

    def test_expired_coupon(self):
        coupon = FakeCoupon(valid_until=datetime(2026, 6, 1))
        with pytest.raises(CouponNotEligibleError) as error:
            CouponValidator().validate(coupon, [line()], NOW)
        assert error.value.reason == "expired"

    def test_exhausted_coupon(self):
        coupon = FakeCoupon(max_uses=3, used_count=3)
        with pytest.raises(CouponNotEligibleError) as error:
            CouponValidator().validate(coupon, [line()], NOW)
        assert error.value.reason == "exhausted"

    def test_last_remaining_use_is_still_valid(self):
        CouponValidator().validate(FakeCoupon(max_uses=3, used_count=2), [line()], NOW)

    def test_minimum_compares_against_eligible_lines_only(self):
        coupon = FakeCoupon(category_id=1, min_cart_total=Decimal("100.00"))
        lines = [line(unit_price="50.00", category_id=1), line(unit_price="500.00", category_id=2)]
        with pytest.raises(CouponNotEligibleError) as error:
            CouponValidator().validate(coupon, lines, NOW)
        assert error.value.reason == "below_minimum"

    def test_minimum_exactly_met_is_accepted(self):
        coupon = FakeCoupon(min_cart_total=Decimal("100.00"))
        CouponValidator().validate(coupon, [line(unit_price="100.00")], NOW)

    def test_no_eligible_items_is_reported_separately(self):
        coupon = FakeCoupon(category_id=99)
        with pytest.raises(CouponNotEligibleError) as error:
            CouponValidator().validate(coupon, [line(category_id=1)], NOW)
        assert error.value.reason == "no_eligible_items"

    def test_validity_boundaries_are_inclusive(self):
        coupon = FakeCoupon(valid_from=NOW, valid_until=NOW)
        CouponValidator().validate(coupon, [line()], NOW)
