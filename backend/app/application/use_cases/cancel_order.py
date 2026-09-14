"""Order cancellation flows: direct cancel, cancel requests, and their decisions."""

from __future__ import annotations

from app.application.services.audit import AuditLogService
from app.application.services.inventory import InventoryService
from app.application.services.notifications import NotificationService
from app.application.services.order_transitions import OrderTransitionExecutor
from app.application.services.payments import PaymentService, RefundService
from app.domain.entities.enums import (
    ActorKind,
    OrderEvent,
    RequestStatus,
    RequestType,
    UserRole,
)
from app.domain.errors import ConflictError
from app.domain.policies.authorization import AuthorizationPolicy
from app.infrastructure.adapters.clock import Clock, SystemClock
from app.infrastructure.persistence.models import Order, OrderRequest, User
from app.infrastructure.repositories.orders import OrderRequestRepository


class OrderCancellationService:
    def __init__(
        self,
        requests: OrderRequestRepository,
        inventory: InventoryService,
        payments: PaymentService,
        refunds: RefundService,
        notifications: NotificationService,
        transitions: OrderTransitionExecutor,
        audit: AuditLogService,
        clock: Clock | None = None,
    ) -> None:
        self._requests = requests
        self._inventory = inventory
        self._payments = payments
        self._refunds = refunds
        self._notifications = notifications
        self._transitions = transitions
        self._audit = audit
        self._clock = clock or SystemClock()

    # ------------------------------------------------------------------
    # Direct cancellation (allowed states; ownership checked by caller)
    # ------------------------------------------------------------------

    def cancel(self, order: Order, *, actor: User, reason: str) -> Order:
        had_authorized_payment = self._payments.authorized_payment(order) is not None
        self._transitions.execute(
            order,
            OrderEvent.CANCEL,
            actor=AuthorizationPolicy.actor_kind_for(actor.role),
            actor_user_id=actor.id,
            note=reason,
        )
        self._inventory.release_for_order(order, reason="Order cancelled", actor_user_id=actor.id)
        if had_authorized_payment:
            self._refunds.refund_order_payment(
                order,
                reason=f"Cancellation: {reason}" if reason else "Cancellation",
                actor_user_id=actor.id,
            )
        self._notifications.order_cancelled(order, refunded=had_authorized_payment)
        return order

    # ------------------------------------------------------------------
    # Cancel requests (order already in PICKING)
    # ------------------------------------------------------------------

    def request_cancellation(self, order: Order, *, customer: User, reason: str) -> OrderRequest:
        if self._requests.pending_for_order(order.id, RequestType.CANCEL) is not None:
            raise ConflictError("A cancellation request is already pending for this order.")
        self._transitions.execute(
            order,
            OrderEvent.REQUEST_CANCEL,
            actor=ActorKind.CUSTOMER,
            actor_user_id=customer.id,
            note=reason,
        )
        request = self._requests.add(
            OrderRequest(
                order_id=order.id,
                request_type=RequestType.CANCEL,
                reason=reason,
                requested_by=customer.id,
            )
        )
        self._audit.record(
            actor_user_id=customer.id,
            action="order.cancel_requested",
            entity_type="order",
            entity_id=order.id,
            details={"request_id": request.id, "reason": reason},
        )
        return request

    def decide_cancellation(
        self, request: OrderRequest, *, approve: bool, decider: User, note: str = ""
    ) -> OrderRequest:
        self._ensure_pending(request, RequestType.CANCEL)
        order = request.order
        event = OrderEvent.APPROVE_CANCEL if approve else OrderEvent.REJECT_CANCEL
        self._transitions.execute(
            order,
            event,
            actor=AuthorizationPolicy.actor_kind_for(decider.role),
            actor_user_id=decider.id,
            note=note,
        )
        if approve:
            self._inventory.release_for_order(
                order, reason="Cancellation approved", actor_user_id=decider.id
            )
            refunded = self._payments.authorized_payment(order) is not None
            if refunded:
                self._refunds.refund_order_payment(
                    order, reason="Cancellation approved", actor_user_id=decider.id
                )
            self._notifications.order_cancelled(order, refunded=refunded)
        request.status = RequestStatus.APPROVED if approve else RequestStatus.REJECTED
        request.decided_by = decider.id
        request.decision_note = note
        request.decided_at = self._clock.now()
        self._audit.record(
            actor_user_id=decider.id,
            action="order.cancel_decided",
            entity_type="order",
            entity_id=order.id,
            details={"request_id": request.id, "approved": approve, "note": note},
        )
        return request

    # ------------------------------------------------------------------

    @staticmethod
    def _ensure_pending(request: OrderRequest, expected_type: RequestType) -> None:
        if request.request_type != expected_type:
            raise ConflictError("Request type mismatch.")
        if request.status != RequestStatus.PENDING:
            raise ConflictError("This request was already decided.")

    @staticmethod
    def ensure_decider_role(role: UserRole) -> None:
        if role not in (UserRole.SUPPORT_AGENT, UserRole.ADMINISTRATOR):
            raise ConflictError("Only support or administrators decide requests.")
