"""Payment records and refunds (the gateway itself is an adapter)."""

from __future__ import annotations

from app.application.services.audit import AuditLogService
from app.domain.entities.enums import PaymentStatus, RefundStatus
from app.domain.errors import ConflictError
from app.domain.value_objects.money import Money
from app.infrastructure.adapters.clock import Clock, SystemClock
from app.infrastructure.adapters.payment_gateway import PaymentGateway
from app.infrastructure.persistence.models import Order, Payment, Refund
from app.infrastructure.repositories.payments import PaymentRepository, RefundRepository


class PaymentService:
    """Creates payment attempts with deterministic idempotency keys."""

    def __init__(self, payments: PaymentRepository, audit: AuditLogService) -> None:
        self._payments = payments
        self._audit = audit

    def create_for_order(self, order: Order, payment_token: str) -> Payment:
        attempt = len(self._payments.list_for_order(order.id)) + 1
        payment = Payment(
            order_id=order.id,
            amount=order.grand_total,
            payment_token=payment_token,
            idempotency_key=f"{order.order_number}-p{attempt}",
        )
        self._payments.add(payment)
        self._audit.record(
            actor_user_id=order.customer_id,
            action="payment.created",
            entity_type="payment",
            entity_id=payment.id,
            details={"order": order.order_number, "amount": str(order.grand_total)},
        )
        return payment

    def authorized_payment(self, order: Order) -> Payment | None:
        for payment in self._payments.list_for_order(order.id):
            if payment.status == PaymentStatus.AUTHORIZED:
                return payment
        return None


class RefundService:
    """Refunds an authorized payment through the (simulated) gateway."""

    def __init__(
        self,
        payments: PaymentRepository,
        refunds: RefundRepository,
        gateway: PaymentGateway,
        audit: AuditLogService,
        clock: Clock | None = None,
    ) -> None:
        self._payments = payments
        self._refunds = refunds
        self._gateway = gateway
        self._audit = audit
        self._clock = clock or SystemClock()

    def refund_order_payment(
        self, order: Order, *, reason: str, actor_user_id: int | None
    ) -> Refund:
        payment = self._authorized_payment_or_raise(order)
        outcome = self._gateway.refund(
            gateway_reference=payment.gateway_reference or payment.idempotency_key,
            amount=Money(payment.amount),
            idempotency_key=f"{payment.idempotency_key}-refund",
        )
        if not outcome.succeeded:  # cannot happen with the simulated gateway
            raise ConflictError("Refund was rejected by the payment provider.")
        refund = Refund(
            payment_id=payment.id,
            amount=payment.amount,
            reason=reason,
            status=RefundStatus.COMPLETED,
            completed_at=self._clock.now(),
        )
        self._refunds.add(refund)
        payment.status = PaymentStatus.REFUNDED
        self._audit.record(
            actor_user_id=actor_user_id,
            action="payment.refunded",
            entity_type="payment",
            entity_id=payment.id,
            details={"order": order.order_number, "amount": str(payment.amount), "reason": reason},
        )
        return refund

    def _authorized_payment_or_raise(self, order: Order) -> Payment:
        for payment in self._payments.list_for_order(order.id):
            if payment.status == PaymentStatus.AUTHORIZED:
                return payment
        raise ConflictError(
            "No authorized payment to refund for this order.",
            details={"order": order.order_number},
        )
