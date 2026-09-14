"""Processing of (simulated) payment gateway results — idempotent by design.

Runs inside the caller's transaction: during checkout right after the gateway
call, and again whenever the callback endpoint replays a result.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.application.commands.commands import PaymentCallbackCommand
from app.application.services.audit import AuditLogService
from app.application.services.inventory import InventoryService
from app.application.services.notifications import NotificationService
from app.application.services.order_transitions import OrderTransitionExecutor
from app.domain.entities.enums import ActorKind, OrderEvent, PaymentStatus
from app.domain.errors import DuplicateCallbackError, NotFoundError, ValidationError
from app.domain.policies.payments import (
    CallbackDecision,
    PaymentIdempotencyPolicy,
    RecordedCallback,
)
from app.infrastructure.persistence.models import Payment
from app.infrastructure.repositories.coupons import CouponRepository
from app.infrastructure.repositories.orders import OrderRepository
from app.infrastructure.repositories.payments import PaymentRepository

_EVENT_FOR_STATUS = {
    PaymentStatus.AUTHORIZED: OrderEvent.PAYMENT_AUTHORIZED,
    PaymentStatus.DECLINED: OrderEvent.PAYMENT_DECLINED,
    PaymentStatus.TIMEOUT: OrderEvent.PAYMENT_TIMEOUT,
}


@dataclass(frozen=True)
class PaymentProcessingResult:
    payment: Payment
    replayed: bool


class PaymentResultProcessor:
    def __init__(
        self,
        payments: PaymentRepository,
        orders: OrderRepository,
        coupons: CouponRepository,
        inventory: InventoryService,
        notifications: NotificationService,
        transitions: OrderTransitionExecutor,
        audit: AuditLogService,
        idempotency: PaymentIdempotencyPolicy | None = None,
    ) -> None:
        self._payments = payments
        self._orders = orders
        self._coupons = coupons
        self._inventory = inventory
        self._notifications = notifications
        self._transitions = transitions
        self._audit = audit
        self._idempotency = idempotency or PaymentIdempotencyPolicy()

    def process(self, command: PaymentCallbackCommand) -> PaymentProcessingResult:
        payment = self._payments.get_by_idempotency_key(command.idempotency_key)
        if payment is None:
            raise NotFoundError(
                "Unknown payment idempotency key.",
                details={"idempotency_key": command.idempotency_key},
            )
        incoming_status = self._parse_status(command.status)

        recorded = None
        if payment.status != PaymentStatus.PENDING:
            recorded = RecordedCallback(
                idempotency_key=payment.idempotency_key, resulting_status=payment.status
            )
        decision = self._idempotency.decide(recorded, incoming_status)

        if decision == CallbackDecision.REPLAY:
            self._audit.record(
                actor_user_id=None,
                action="payment.callback_replayed",
                entity_type="payment",
                entity_id=payment.id,
                details={"status": incoming_status.value},
            )
            order = self._orders.get(payment.order_id)
            if incoming_status == PaymentStatus.AUTHORIZED:
                self._notifications.payment_confirmed(order)
            return PaymentProcessingResult(payment=payment, replayed=True)
        if decision == CallbackDecision.CONFLICT:
            raise DuplicateCallbackError(
                "Conflicting result for an already processed payment.",
                details={
                    "idempotency_key": command.idempotency_key,
                    "recorded": payment.status.value,
                    "incoming": incoming_status.value,
                },
            )

        return PaymentProcessingResult(
            payment=self._apply_result(payment, incoming_status, command), replayed=False
        )

    # ------------------------------------------------------------------

    def _apply_result(
        self, payment: Payment, status: PaymentStatus, command: PaymentCallbackCommand
    ) -> Payment:
        order = self._orders.get(payment.order_id)
        payment.status = status
        if command.gateway_reference:
            payment.gateway_reference = command.gateway_reference

        self._audit.record(
            actor_user_id=None,
            action="payment.result",
            entity_type="payment",
            entity_id=payment.id,
            details={"order": order.order_number, "status": status.value},
        )

        self._transitions.execute(
            order,
            _EVENT_FOR_STATUS[status],
            actor=ActorKind.SYSTEM,
            actor_user_id=None,
            note=command.message,
        )

        if status == PaymentStatus.AUTHORIZED:
            self._consume_coupon_use(order.coupon_code)
            self._notifications.payment_confirmed(order)
        else:
            if status == PaymentStatus.DECLINED:
                self._inventory.release_for_order(
                    order,
                    reason="Payment failed",
                    actor_user_id=None,
                )
            self._notifications.payment_failed(
                order, command.message or "The payment was not completed."
            )
        return payment

    def _consume_coupon_use(self, coupon_code: str | None) -> None:
        if not coupon_code:
            return
        coupon = self._coupons.get_by_code(coupon_code)
        if coupon is not None:
            coupon.used_count += 1

    @staticmethod
    def _parse_status(raw: str) -> PaymentStatus:
        try:
            status = PaymentStatus(raw)
        except ValueError:
            raise ValidationError(
                f"Unknown payment status '{raw}'.",
                details={"allowed": ["authorized", "declined", "timeout"]},
            ) from None
        if status not in _EVENT_FOR_STATUS:
            raise ValidationError(
                f"Status '{raw}' cannot be delivered by a callback.",
                details={"allowed": ["authorized", "declined", "timeout"]},
            )
        return status
