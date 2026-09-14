"""Cart item rules: quantity limits and add/update validation."""

from __future__ import annotations

from app.domain.entities.interfaces import (
    CategoryLike,
    ProductLike,
    StockLevelLike,
    VariantLike,
)
from app.domain.errors import InvalidQuantityError
from app.domain.policies.catalog import ProductActivationPolicy, VariantAvailabilityPolicy


class QuantityValidator:
    """A line quantity is an integer in ``1..max_per_line``."""

    def __init__(self, max_per_line: int) -> None:
        if max_per_line < 1:
            raise ValueError("max_per_line must be >= 1")
        self.max_per_line = max_per_line

    def validate(self, quantity: int) -> None:
        if not isinstance(quantity, int) or isinstance(quantity, bool):
            raise InvalidQuantityError("Quantity must be a whole number.")
        if quantity < 1:
            raise InvalidQuantityError(
                "Quantity must be at least 1.", details={"quantity": quantity}
            )
        if quantity > self.max_per_line:
            raise InvalidQuantityError(
                f"Quantity is limited to {self.max_per_line} per item.",
                details={"quantity": quantity, "max_per_line": self.max_per_line},
            )


class CartItemPolicy:
    """Combined rule for adding/updating a cart line.

    Delegates to activation, availability, and quantity rules so each can be
    mocked independently in unit tests.
    """

    def __init__(
        self,
        quantity_validator: QuantityValidator,
        activation_policy: ProductActivationPolicy | None = None,
        availability_policy: VariantAvailabilityPolicy | None = None,
    ) -> None:
        self.quantity_validator = quantity_validator
        self.activation_policy = activation_policy or ProductActivationPolicy()
        self.availability_policy = availability_policy or VariantAvailabilityPolicy()

    def validate_line(
        self,
        *,
        category: CategoryLike,
        product: ProductLike,
        variant: VariantLike,
        stock: StockLevelLike,
        quantity: int,
    ) -> None:
        """Raises a typed domain error when the line must be rejected."""
        self.quantity_validator.validate(quantity)
        self.activation_policy.ensure_orderable(category, product, variant)
        self.availability_policy.ensure_available(stock, quantity)
