"""Money value object.

Exact decimal arithmetic for EUR amounts: 2 decimal places, ROUND_HALF_UP.
Persistence stores integer cents; domain code must never use floats for money.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

_CENT = Decimal("0.01")

Numeric = int | str | Decimal


class CurrencyMismatchError(ValueError):
    pass


@dataclass(frozen=True)
class Money:
    amount: Decimal
    currency: str = "EUR"

    def __post_init__(self) -> None:
        if not isinstance(self.amount, Decimal):
            raise TypeError("Money.amount must be a Decimal; use Money.of(...) for strings")
        quantized = self.amount.quantize(_CENT, rounding=ROUND_HALF_UP)
        object.__setattr__(self, "amount", quantized)

    # --- constructors -------------------------------------------------
    @classmethod
    def of(cls, value: Numeric, currency: str = "EUR") -> Money:
        return cls(Decimal(str(value)), currency)

    @classmethod
    def from_cents(cls, cents: int, currency: str = "EUR") -> Money:
        return cls(Decimal(cents) / 100, currency)

    @classmethod
    def zero(cls, currency: str = "EUR") -> Money:
        return cls(Decimal("0"), currency)

    # --- accessors ----------------------------------------------------
    @property
    def cents(self) -> int:
        return int((self.amount * 100).to_integral_value(rounding=ROUND_HALF_UP))

    @property
    def is_negative(self) -> bool:
        return self.amount < 0

    @property
    def is_zero(self) -> bool:
        return self.amount == 0

    # --- arithmetic ---------------------------------------------------
    def _check(self, other: Money) -> None:
        if not isinstance(other, Money):
            raise TypeError(f"expected Money, got {type(other).__name__}")
        if self.currency != other.currency:
            raise CurrencyMismatchError(f"{self.currency} vs {other.currency}")

    def __add__(self, other: Money) -> Money:
        self._check(other)
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: Money) -> Money:
        self._check(other)
        return Money(self.amount - other.amount, self.currency)

    def __neg__(self) -> Money:
        return Money(-self.amount, self.currency)

    def times(self, quantity: int) -> Money:
        if not isinstance(quantity, int):
            raise TypeError("quantity must be an int")
        return Money(self.amount * quantity, self.currency)

    def percentage(self, rate: Decimal) -> Money:
        """``rate`` is a fraction (VAT 23 % → Decimal('0.23')). Rounds HALF_UP to cents."""
        if not isinstance(rate, Decimal):
            raise TypeError("rate must be a Decimal")
        return Money(self.amount * rate, self.currency)

    def min(self, other: Money) -> Money:
        self._check(other)
        return self if self.amount <= other.amount else other

    # --- comparisons --------------------------------------------------
    def __lt__(self, other: Money) -> bool:
        self._check(other)
        return self.amount < other.amount

    def __le__(self, other: Money) -> bool:
        self._check(other)
        return self.amount <= other.amount

    def __gt__(self, other: Money) -> bool:
        self._check(other)
        return self.amount > other.amount

    def __ge__(self, other: Money) -> bool:
        self._check(other)
        return self.amount >= other.amount

    # --- allocation ---------------------------------------------------
    def allocate(self, weights: list[int]) -> list[Money]:
        """Split proportionally to ``weights`` without losing a cent.

        Largest-remainder method: floor shares first, then distribute the
        remaining cents to the largest fractional remainders (ties: earlier
        weight wins). The parts always sum exactly to ``self``.
        """
        if not weights:
            raise ValueError("weights must not be empty")
        if any(w < 0 for w in weights):
            raise ValueError("weights must be non-negative")
        total_weight = sum(weights)
        if total_weight == 0:
            raise ValueError("at least one weight must be positive")

        total_cents = self.cents
        floors: list[int] = []
        remainders: list[tuple[Decimal, int]] = []
        for index, weight in enumerate(weights):
            exact = Decimal(total_cents) * weight / total_weight
            floor = int(exact.to_integral_value(rounding="ROUND_FLOOR"))
            floors.append(floor)
            remainders.append((exact - floor, index))

        leftover = total_cents - sum(floors)
        for _, index in sorted(remainders, key=lambda pair: (-pair[0], pair[1])):
            if leftover <= 0:
                break
            floors[index] += 1
            leftover -= 1

        return [Money.from_cents(cents, self.currency) for cents in floors]

    def __str__(self) -> str:
        return f"{self.amount:.2f} {self.currency}"
