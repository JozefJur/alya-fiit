"""Checkout: cart → priced, reserved, paid order — atomically.

The whole flow runs in one transaction (the request's unit of work): if any
step fails with an unexpected error, nothing is persisted. Expected payment
failures (decline/timeout) are *not* errors: the order is kept in
``PAYMENT_FAILED`` with its reservation released, which is exactly the
behavior BG-05 requires.
"""

from __future__ import annotations

from app.application.commands.commands import CheckoutCommand, PaymentCallbackCommand
from app.application.services.audit import AuditLogService
from app.application.services.cart import CartService, CartValidator
from app.application.services.inventory import InventoryService
from app.application.services.notifications import NotificationService
from app.application.services.order_transitions import OrderTransitionExecutor
from app.application.services.payments import PaymentService
from app.application.services.pricing import CartPriceCalculator
from app.application.use_cases.process_payment_result import PaymentResultProcessor
from app.config import Settings
from app.domain.entities.enums import (
    ActorKind,
    CartStatus,
    OrderEvent,
    OrderStatus,
    PaymentStatus,
)
from app.domain.errors import ConflictError, NotFoundError, ValidationError
from app.domain.policies.coupons import CouponValidator
from app.domain.value_objects.money import Money
from app.infrastructure.adapters.clock import Clock, SystemClock
from app.infrastructure.adapters.payment_gateway import PaymentGateway
from app.infrastructure.persistence.models import Order, OrderItem, OrderStatusHistory
from app.infrastructure.repositories.coupons import CouponRepository
from app.infrastructure.repositories.orders import OrderRepository

#: Countries we ship to, with the digit count of their postal codes.
SHIPPING_COUNTRIES: dict[str, int] = {"SK": 5, "CZ": 5, "AT": 4, "HU": 4, "PL": 5, "DE": 5}

#: How many order numbers to try before giving up (unique constraint safety).
MAX_ORDER_NUMBER_ATTEMPTS = 5


class CheckoutService:
    """Turns the customer's cart into a paid order."""

    def __init__(
        self,
        cart_service: CartService,
        cart_validator: CartValidator,
        coupons: CouponRepository,
        coupon_validator: CouponValidator,
        calculator: CartPriceCalculator,
        orders: OrderRepository,
        inventory: InventoryService,
        payments: PaymentService,
        payment_processor: PaymentResultProcessor,
        gateway: PaymentGateway,
        notifications: NotificationService,
        audit: AuditLogService,
        transitions: OrderTransitionExecutor,
        settings: Settings,
        clock: Clock | None = None,
    ) -> None:
        self._cart_service = cart_service
        self._cart_validator = cart_validator
        self._coupons = coupons
        self._coupon_validator = coupon_validator
        self._calculator = calculator
        self._orders = orders
        self._inventory = inventory
        self._payments = payments
        self._payment_processor = payment_processor
        self._gateway = gateway
        self._notifications = notifications
        self._audit = audit
        self._transitions = transitions
        self._settings = settings
        self._clock = clock or SystemClock()

    def checkout(self, command: CheckoutCommand) -> Order:
        # 1. Load and validate the cart.
        cart = self._cart_service.get_active_cart(command.customer_id)
        self._cart_validator.validate_for_checkout(cart)
        lines = self._cart_service.build_pricing_lines(cart)

        # 2. Normalise and check the shipping address.
        name = command.address.name.strip()
        street = command.address.street.strip()
        city = command.address.city.strip()
        zip_code = command.address.zip_code.strip().replace(" ", "")
        country = command.address.country.strip().upper()
        if len(name) < 2:
            raise ValidationError("Enter the recipient's full name.", details={"field": "name"})
        if len(street) < 3:
            raise ValidationError("Enter the street and house number.", details={"field": "street"})
        if len(city) < 2:
            raise ValidationError("Enter the city.", details={"field": "city"})
        if country not in SHIPPING_COUNTRIES:
            raise ValidationError(
                f"We do not ship to '{country}'.",
                details={"field": "country", "supported": sorted(SHIPPING_COUNTRIES)},
            )
        expected_zip_length = SHIPPING_COUNTRIES[country]
        if not zip_code.isdigit() or len(zip_code) != expected_zip_length:
            raise ValidationError(
                f"A {country} ZIP code has {expected_zip_length} digits.",
                details={"field": "zip_code"},
            )

        # 3. Resolve and fully validate the coupon (checkout is authoritative).
        coupon = None
        requested_code = command.coupon_code or cart.coupon_code
        if requested_code:
            coupon = self._coupons.get_by_code(requested_code)
            if coupon is None:
                raise NotFoundError("Coupon code does not exist.", details={"code": requested_code})
            self._coupon_validator.validate(coupon, lines, self._clock.now())
            if cart.coupon_code != coupon.code:
                # An explicitly submitted code wins over whatever the cart held.
                cart.coupon_code = coupon.code

        # 4. Price the cart server-side.
        breakdown = self._calculator.price(lines, coupon)

        # 5. Allocate an order number, stepping over collisions.
        now = self._clock.now()
        sequence = self._orders.next_sequence_number()
        prefix = self._settings.order_number_prefix
        order_number = f"{prefix}-{now.year}-{sequence:06d}"
        attempts = 0
        while self._orders.get_by_number(order_number) is not None:
            attempts += 1
            if attempts > MAX_ORDER_NUMBER_ATTEMPTS:
                raise ConflictError(
                    "Could not allocate an order number, please try again.",
                    details={"last_tried": order_number},
                )
            sequence += 1
            order_number = f"{prefix}-{now.year}-{sequence:06d}"

        # 6. Create the order draft with full snapshots.
        order = Order(
            order_number=order_number,
            customer_id=command.customer_id,
            status=OrderStatus.DRAFT,
            subtotal=breakdown.subtotal.amount,
            discount_total=breakdown.discount_total.amount,
            vat_total=breakdown.vat_total.amount,
            grand_total=breakdown.grand_total.amount,
            coupon_code=breakdown.coupon_code,
            ship_to_name=name,
            ship_street=street,
            ship_city=city,
            ship_zip=zip_code,
            ship_country=country,
        )
        for priced in breakdown.lines:
            source = priced.source
            order.items.append(
                OrderItem(
                    variant_id=source.variant_id,
                    product_name=source.product_name,
                    sku=source.sku,
                    unit_price=source.unit_price.amount,
                    vat_rate=source.vat_rate,
                    quantity=source.quantity,
                    discount_amount=priced.discount.amount,
                    vat_amount=priced.vat.amount,
                    line_total=priced.line_total.amount,
                )
            )
        order.status_history.append(
            OrderStatusHistory(
                from_status=None,
                to_status=OrderStatus.DRAFT,
                event="checkout_started",
                actor_user_id=command.customer_id,
                created_at=now,
            )
        )
        self._orders.add(order)
        self._audit.record(
            actor_user_id=command.customer_id,
            action="order.created",
            entity_type="order",
            entity_id=order.id,
            details={
                "order_number": order.order_number,
                "grand_total": str(order.grand_total),
                "coupon": order.coupon_code,
                "items": len(order.items),
            },
        )

        # 7. Reserve stock (any failure rolls back the whole checkout).
        self._inventory.reserve_for_order(
            order, [(item.variant_id, item.quantity) for item in order.items]
        )

        # 8. Move to PENDING_PAYMENT and notify.
        self._transitions.execute(
            order, OrderEvent.SUBMIT_PAYMENT, actor=ActorKind.SYSTEM, actor_user_id=None
        )
        self._notifications.order_created(order)

        # 9. Create the payment attempt and call the (simulated) gateway.
        payment = self._payments.create_for_order(order, command.payment_token)
        outcome = self._gateway.authorize(
            order_number=order.order_number,
            amount=Money(order.grand_total),
            payment_token=command.payment_token,
            idempotency_key=payment.idempotency_key,
        )

        # 10. Apply the gateway result (same transaction, idempotent processor).
        result = self._payment_processor.process(
            PaymentCallbackCommand(
                idempotency_key=payment.idempotency_key,
                status=outcome.status.value,
                gateway_reference=outcome.gateway_reference,
                message=outcome.message,
            )
        )

        # 11. Only a successful payment consumes the cart — after a declined or
        # timed-out payment the customer keeps the cart and can retry (BG-05).
        if result.payment.status == PaymentStatus.AUTHORIZED:
            cart.status = CartStatus.CONVERTED
            cart.coupon_code = None

        return order
