"""Cart workflows: one active cart per customer, item rules, coupon handling."""

from __future__ import annotations

from dataclasses import dataclass

from app.application.services.pricing import CartPriceCalculator, PricingService
from app.domain.entities.pricing import PriceBreakdown, PricingLineInput
from app.domain.errors import (
    CouponNotEligibleError,
    NotFoundError,
    ProductNotAvailableError,
    ValidationError,
)
from app.domain.policies.cart import CartItemPolicy
from app.domain.policies.catalog import ProductActivationPolicy, VariantAvailabilityPolicy
from app.domain.policies.coupons import CouponValidator
from app.infrastructure.adapters.clock import Clock, SystemClock
from app.infrastructure.persistence.models import Cart, CartItem, Coupon
from app.infrastructure.repositories.carts import CartRepository
from app.infrastructure.repositories.catalog import VariantRepository
from app.infrastructure.repositories.coupons import CouponRepository


class _OnHandView:
    """Stock view used when re-checking an existing cart line."""

    def __init__(self, level) -> None:  # noqa: ANN001
        self.variant_id = level.variant_id
        self.on_hand = level.on_hand
        self.reserved = 0
        self.low_stock_threshold = level.low_stock_threshold


@dataclass(frozen=True)
class CartProblem:
    variant_id: int
    code: str
    message: str


@dataclass(frozen=True)
class PricedCart:
    cart: Cart
    breakdown: PriceBreakdown
    problems: list[CartProblem]
    coupon_error: str | None = None


class CartMergeService:
    """Merges a stray active cart into the target one (defensive repair).

    Quantities of the same variant are summed and capped at ``max_per_line``;
    the source cart is emptied and converted so the unique-active-cart
    invariant holds again.
    """

    def __init__(self, max_per_line: int) -> None:
        if max_per_line < 1:
            raise ValueError("max_per_line must be >= 1")
        self.max_per_line = max_per_line

    def merge(self, target: Cart, source: Cart) -> Cart:
        if target.id == source.id:
            raise ValidationError("Cannot merge a cart into itself.")
        by_variant = {item.variant_id: item for item in target.items}
        for item in list(source.items):
            existing = by_variant.get(item.variant_id)
            if existing is None:
                target.items.append(
                    CartItem(
                        variant_id=item.variant_id, quantity=min(item.quantity, self.max_per_line)
                    )
                )
            else:
                existing.quantity = min(existing.quantity + item.quantity, self.max_per_line)
            source.items.remove(item)
        from app.domain.entities.enums import CartStatus

        source.status = CartStatus.CONVERTED
        if target.coupon_code is None and source.coupon_code is not None:
            target.coupon_code = source.coupon_code
        return target


class CartService:
    def __init__(
        self,
        carts: CartRepository,
        variants: VariantRepository,
        coupons: CouponRepository,
        item_policy: CartItemPolicy,
        pricing: PricingService,
        calculator: CartPriceCalculator,
        merge_service: CartMergeService,
        coupon_validator: CouponValidator | None = None,
        clock: Clock | None = None,
        activation_policy: ProductActivationPolicy | None = None,
        availability_policy: VariantAvailabilityPolicy | None = None,
    ) -> None:
        self._carts = carts
        self._variants = variants
        self._coupons = coupons
        self._item_policy = item_policy
        self._pricing = pricing
        self._calculator = calculator
        self._merge = merge_service
        self._coupon_validator = coupon_validator or CouponValidator()
        self._clock = clock or SystemClock()
        self._activation = activation_policy or ProductActivationPolicy()
        self._availability = availability_policy or VariantAvailabilityPolicy()

    # ------------------------------------------------------------------
    # Cart lifecycle
    # ------------------------------------------------------------------

    def get_active_cart(self, customer_id: int) -> Cart:
        carts = self._carts.active_carts_for(customer_id)
        if not carts:
            return self._carts.add(Cart(customer_id=customer_id))
        primary = carts[0]
        for stray in carts[1:]:  # self-heal: the DB constraint should prevent this
            self._merge.merge(primary, stray)
        return primary

    # ------------------------------------------------------------------
    # Items
    # ------------------------------------------------------------------

    def add_item(self, customer_id: int, variant_id: int, quantity: int) -> Cart:
        cart = self.get_active_cart(customer_id)
        variant = self._variants.get(variant_id)
        product = variant.product
        stock = variant.stock_level
        if stock is None:
            raise ProductNotAvailableError(
                "This product is currently not available.",
                details={"reason": "no_stock_record", "variant_id": variant_id},
            )
        existing = self._carts.find_item(cart, variant_id)
        new_quantity = quantity + (existing.quantity if existing else 0)
        self._item_policy.validate_line(
            category=product.category,
            product=product,
            variant=variant,
            stock=stock,
            quantity=quantity,
        )
        if existing:
            existing.quantity = new_quantity
        else:
            cart.items.append(CartItem(variant_id=variant_id, quantity=quantity))
        cart.updated_at = self._clock.now()
        # Flush so the new line's variant/product relationships are loadable
        # for callers that price or validate the cart in the same transaction.
        self._carts.flush()
        return cart

    def update_item(self, customer_id: int, variant_id: int, quantity: int) -> Cart:
        cart = self.get_active_cart(customer_id)
        item = self._carts.find_item(cart, variant_id)
        if item is None:
            raise NotFoundError("Item is not in the cart.", details={"variant_id": variant_id})
        if quantity == 0:
            return self.remove_item(customer_id, variant_id)
        variant = self._variants.get(variant_id)
        stock = variant.stock_level
        if stock is None:
            raise ProductNotAvailableError(
                "This product is currently not available.",
                details={"reason": "no_stock_record", "variant_id": variant_id},
            )
        self._item_policy.validate_line(
            category=variant.product.category,
            product=variant.product,
            variant=variant,
            stock=_OnHandView(stock),
            quantity=quantity,
        )
        item.quantity = quantity
        cart.updated_at = self._clock.now()
        self._carts.flush()
        return cart

    def remove_item(self, customer_id: int, variant_id: int) -> Cart:
        cart = self.get_active_cart(customer_id)
        item = self._carts.find_item(cart, variant_id)
        if item is None:
            raise NotFoundError("Item is not in the cart.", details={"variant_id": variant_id})
        cart.items.remove(item)
        cart.updated_at = self._clock.now()
        self._carts.flush()
        return cart

    def clear(self, customer_id: int) -> Cart:
        cart = self.get_active_cart(customer_id)
        cart.items.clear()
        cart.coupon_code = None
        cart.updated_at = self._clock.now()
        self._carts.flush()
        return cart

    # ------------------------------------------------------------------
    # Coupons
    # ------------------------------------------------------------------

    def apply_coupon(self, customer_id: int, code: str) -> Cart:
        cart = self.get_active_cart(customer_id)
        coupon = self._coupons.get_by_code(code)
        if coupon is None:
            raise NotFoundError("Coupon code does not exist.", details={"code": code})
        error = self._quick_coupon_check(coupon)
        if error is not None:
            raise CouponNotEligibleError(error[1], reason=error[0])
        cart.coupon_code = coupon.code
        cart.updated_at = self._clock.now()
        return cart

    def remove_coupon(self, customer_id: int) -> Cart:
        cart = self.get_active_cart(customer_id)
        cart.coupon_code = None
        cart.updated_at = self._clock.now()
        return cart

    def _quick_coupon_check(self, coupon: Coupon) -> tuple[str, str] | None:
        """Cheap pre-check when attaching a coupon to the cart.

        Full validation (incl. minimum cart value against eligible lines)
        happens at pricing/checkout time via ``CouponValidator``.
        """
        now = self._clock.now()
        if not coupon.is_active:
            return ("inactive", "This coupon is not active.")
        if now < coupon.valid_from:
            return ("not_started", "This coupon is not valid yet.")
        if now > coupon.valid_until:
            return ("expired", "This coupon has expired.")
        if coupon.max_uses is not None and coupon.used_count >= coupon.max_uses:
            return ("exhausted", "This coupon has reached its usage limit.")
        return None

    # ------------------------------------------------------------------
    # Priced view
    # ------------------------------------------------------------------

    def build_pricing_lines(self, cart: Cart) -> list[PricingLineInput]:
        lines: list[PricingLineInput] = []
        for item in cart.items:
            variant = item.variant
            product = variant.product
            lines.append(
                self._pricing.build_line(
                    product=product,
                    variant=variant,
                    category_id=product.category_id,
                    product_name=f"{product.name} — {variant.name}",
                    quantity=item.quantity,
                )
            )
        return lines

    def priced_cart(self, customer_id: int) -> PricedCart:
        """Cart with server-computed totals plus per-line problems (if any)."""
        self._carts.flush()
        cart = self.get_active_cart(customer_id)
        problems = self.collect_problems(cart)
        lines = self.build_pricing_lines(cart)

        coupon = None
        coupon_error: str | None = None
        if cart.coupon_code:
            coupon = self._coupons.get_by_code(cart.coupon_code)
            if coupon is None:
                coupon_error = "Coupon no longer exists."
            else:
                try:
                    # The same validation checkout runs, so the cart never shows
                    # a discount checkout would refuse (e.g. below the minimum).
                    self._coupon_validator.validate(coupon, lines, self._clock.now())
                except CouponNotEligibleError as error:
                    coupon, coupon_error = None, error.message

        breakdown = self._calculator.price(lines, coupon)
        return PricedCart(
            cart=cart, breakdown=breakdown, problems=problems, coupon_error=coupon_error
        )

    def collect_problems(self, cart: Cart) -> list[CartProblem]:
        problems: list[CartProblem] = []
        for item in cart.items:
            variant = item.variant
            product = variant.product
            reason = self._activation.inactive_reason(product.category, product, variant)
            if reason is not None:
                problems.append(
                    CartProblem(
                        variant_id=item.variant_id,
                        code=reason,
                        message="This item is no longer available.",
                    )
                )
                continue
            stock = variant.stock_level
            available = self._availability.available(stock) if stock else 0
            if stock is None or item.quantity > available:
                problems.append(
                    CartProblem(
                        variant_id=item.variant_id,
                        code="insufficient_stock",
                        message=f"Only {max(available, 0)} left in stock.",
                    )
                )
        return problems


class CartValidator:
    """Checkout precondition: the cart must be non-empty and problem-free."""

    def __init__(self, cart_service: CartService) -> None:
        self._cart_service = cart_service

    def validate_for_checkout(self, cart: Cart) -> None:
        if not cart.items:
            raise ValidationError("Your cart is empty.")
        problems = self._cart_service.collect_problems(cart)
        if problems:
            raise ValidationError(
                "Some items in your cart are not available.",
                details={
                    "problems": [
                        {"variant_id": p.variant_id, "code": p.code, "message": p.message}
                        for p in problems
                    ]
                },
            )
