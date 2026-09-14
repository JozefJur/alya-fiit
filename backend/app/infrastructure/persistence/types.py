"""Custom column types.

SQLite has no exact decimal type, so storing ``NUMERIC`` would silently fall
back to floats. Monetary amounts and rates are therefore stored as scaled
integers (cents, basis points) and exposed to Python as exact ``Decimal``s.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import Integer
from sqlalchemy.types import TypeDecorator


class ScaledDecimal(TypeDecorator[Decimal]):
    """Decimal stored as ``int(value * scale)``.

    ``ScaledDecimal(100)`` → money in cents; ``ScaledDecimal(10000)`` → rates
    in basis points (0.23 ↔ 2300).
    """

    impl = Integer
    cache_ok = True

    def __init__(self, scale: int) -> None:
        super().__init__()
        self.scale = scale

    def process_bind_param(self, value: Any, dialect: Any) -> int | None:
        if value is None:
            return None
        if isinstance(value, float):
            raise TypeError("floats are not allowed for exact decimal columns")
        as_decimal = value if isinstance(value, Decimal) else Decimal(str(value))
        scaled = (as_decimal * self.scale).to_integral_value()
        if scaled != as_decimal * self.scale:
            raise ValueError(f"value {as_decimal} has more precision than 1/{self.scale}")
        return int(scaled)

    def process_result_value(self, value: int | None, dialect: Any) -> Decimal | None:
        if value is None:
            return None
        return Decimal(value) / self.scale


def money_column_type() -> ScaledDecimal:
    return ScaledDecimal(100)


def rate_column_type() -> ScaledDecimal:
    return ScaledDecimal(10000)
