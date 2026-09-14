"""Cart persistence."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.domain.entities.enums import CartStatus
from app.domain.errors import NotFoundError
from app.infrastructure.persistence.models import Cart, CartItem, Product, ProductVariant


class CartRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def _loaded(self, stmt):  # noqa: ANN001, ANN202 - internal helper
        return stmt.options(
            selectinload(Cart.items)
            .selectinload(CartItem.variant)
            .selectinload(ProductVariant.product)
            .selectinload(Product.category),
            selectinload(Cart.items)
            .selectinload(CartItem.variant)
            .selectinload(ProductVariant.stock_level),
        )

    def active_carts_for(self, customer_id: int) -> list[Cart]:
        stmt = self._loaded(
            select(Cart)
            .where(Cart.customer_id == customer_id, Cart.status == CartStatus.ACTIVE)
            .order_by(Cart.id)
        )
        return list(self.session.scalars(stmt))

    def get_owned(self, cart_id: int, customer_id: int) -> Cart:
        cart = self.session.get(Cart, cart_id)
        if cart is None or cart.customer_id != customer_id:
            raise NotFoundError("Cart not found.", details={"cart_id": cart_id})
        return cart

    def add(self, cart: Cart) -> Cart:
        self.session.add(cart)
        self.session.flush()
        return cart

    def flush(self) -> None:
        """Flush pending cart mutations so relationships resolve on re-read."""
        self.session.flush()

    def find_item(self, cart: Cart, variant_id: int) -> CartItem | None:
        for item in cart.items:
            if item.variant_id == variant_id:
                return item
        return None
