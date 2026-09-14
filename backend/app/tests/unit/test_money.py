"""Money value object: rounding, arithmetic, comparisons, allocation."""

from decimal import Decimal

import pytest

from app.domain.value_objects.money import CurrencyMismatchError, Money


class TestMoneyConstruction:
    def test_of_accepts_strings_and_rounds_half_up(self):
        assert Money.of("10.005").amount == Decimal("10.01")
        assert Money.of("10.004").amount == Decimal("10.00")

    def test_rejects_float_amounts(self):
        with pytest.raises(TypeError):
            Money(0.1)  # type: ignore[arg-type]

    def test_from_cents_and_back(self):
        assert Money.from_cents(1234).amount == Decimal("12.34")
        assert Money.of("12.34").cents == 1234

    def test_negative_and_zero_flags(self):
        assert Money.of("-1.00").is_negative
        assert Money.zero().is_zero
        assert not Money.of("0.01").is_zero


class TestMoneyArithmetic:
    def test_add_and_subtract(self):
        assert (Money.of("10.10") + Money.of("0.90")).amount == Decimal("11.00")
        assert (Money.of("10.00") - Money.of("10.01")).amount == Decimal("-0.01")

    def test_times_requires_int(self):
        assert Money.of("3.33").times(3).amount == Decimal("9.99")
        with pytest.raises(TypeError):
            Money.of("1.00").times(2.5)  # type: ignore[arg-type]

    def test_percentage_rounds_half_up(self):
        # 23 % VAT of 178.20 = 40.986 → 40.99
        assert Money.of("178.20").percentage(Decimal("0.23")).amount == Decimal("40.99")

    def test_percentage_requires_decimal_rate(self):
        with pytest.raises(TypeError):
            Money.of("100.00").percentage(0.23)  # type: ignore[arg-type]

    def test_currency_mismatch_is_rejected(self):
        with pytest.raises(CurrencyMismatchError):
            Money.of("1.00", "EUR") + Money.of("1.00", "USD")

    def test_min_returns_smaller_amount(self):
        assert Money.of("5.00").min(Money.of("7.00")).amount == Decimal("5.00")
        assert Money.of("9.00").min(Money.of("7.00")).amount == Decimal("7.00")

    def test_comparisons(self):
        assert Money.of("1.00") < Money.of("1.01")
        assert Money.of("1.00") <= Money.of("1.00")
        assert Money.of("2.00") > Money.of("1.99")
        assert Money.of("2.00") >= Money.of("2.00")


class TestMoneyAllocation:
    def test_allocation_sums_exactly_to_the_original(self):
        parts = Money.of("10.00").allocate([1, 1, 1])
        assert [p.amount for p in parts] == [
            Decimal("3.34"),
            Decimal("3.33"),
            Decimal("3.33"),
        ]
        assert sum(p.cents for p in parts) == 1000

    def test_allocation_is_proportional_to_weights(self):
        parts = Money.of("100.00").allocate([70, 30])
        assert [p.amount for p in parts] == [Decimal("70.00"), Decimal("30.00")]

    def test_zero_weight_line_receives_nothing(self):
        parts = Money.of("9.99").allocate([1, 0])
        assert parts[1].is_zero
        assert parts[0].amount == Decimal("9.99")

    def test_empty_weights_are_rejected(self):
        with pytest.raises(ValueError):
            Money.of("1.00").allocate([])

    def test_all_zero_weights_are_rejected(self):
        with pytest.raises(ValueError):
            Money.of("1.00").allocate([0, 0])

    def test_negative_weights_are_rejected(self):
        with pytest.raises(ValueError):
            Money.of("1.00").allocate([-1, 2])


def test_str_shows_two_decimals_and_currency():
    assert str(Money.of("7")) == "7.00 EUR"
