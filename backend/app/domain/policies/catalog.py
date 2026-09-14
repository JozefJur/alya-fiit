"""Catalog activation and availability rules."""

from __future__ import annotations

from app.domain.entities.interfaces import (
    CategoryLike,
    ProductLike,
    StockLevelLike,
    VariantLike,
)
from app.domain.errors import InsufficientStockError, ProductNotAvailableError


class ProductActivationPolicy:
    """An item is orderable only when category, product, and variant are all active."""

    def is_orderable(
        self, category: CategoryLike, product: ProductLike, variant: VariantLike
    ) -> bool:
        return bool(category.is_active and product.is_active and variant.is_active)

    def inactive_reason(
        self, category: CategoryLike, product: ProductLike, variant: VariantLike
    ) -> str | None:
        if not category.is_active:
            return "category_inactive"
        if not product.is_active:
            return "product_inactive"
        if not variant.is_active:
            return "variant_inactive"
        return None

    def ensure_orderable(
        self, category: CategoryLike, product: ProductLike, variant: VariantLike
    ) -> None:
        reason = self.inactive_reason(category, product, variant)
        if reason is not None:
            raise ProductNotAvailableError(
                "This product is currently not available.",
                details={"reason": reason, "variant_id": variant.id},
            )


class VariantAvailabilityPolicy:
    """Stock-based availability: requested quantity must fit into ``available``."""

    def available(self, stock: StockLevelLike) -> int:
        return stock.on_hand - stock.reserved

    def is_available(self, stock: StockLevelLike, requested_quantity: int) -> bool:
        if requested_quantity <= 0:
            return False
        return requested_quantity <= self.available(stock)

    def ensure_available(self, stock: StockLevelLike, requested_quantity: int) -> None:
        available = self.available(stock)
        if requested_quantity > available:
            raise InsufficientStockError(
                "Not enough stock available.",
                details={
                    "variant_id": stock.variant_id,
                    "requested": requested_quantity,
                    "available": available,
                },
            )
