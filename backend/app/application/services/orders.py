"""Order read/lifecycle operations outside checkout and cancellation."""

from __future__ import annotations

from app.application.services.audit import AuditLogService
from app.application.services.notifications import NotificationService
from app.application.services.order_transitions import OrderTransitionExecutor
from app.application.services.payments import RefundService
from app.domain.entities.enums import (
    ActorKind,
    OrderEvent,
    RequestStatus,
    RequestType,
)
from app.domain.errors import ConflictError
from app.domain.policies.authorization import AuthorizationPolicy
from app.domain.policies.orders import OrderAccessPolicy, ReturnEligibilityPolicy
from app.infrastructure.adapters.clock import Clock, SystemClock
from app.infrastructure.persistence.models import Order, OrderRequest, User
from app.infrastructure.repositories.orders import OrderRepository, OrderRequestRepository


class OrderService:
    def __init__(
        self,
        orders: OrderRepository,
        requests: OrderRequestRepository,
        access_policy: OrderAccessPolicy,
        return_policy: ReturnEligibilityPolicy,
        transitions: OrderTransitionExecutor,
        refunds: RefundService,
        notifications: NotificationService,
        audit: AuditLogService,
        clock: Clock | None = None,
    ) -> None:
        self._orders = orders
        self._requests = requests
        self._access = access_policy
        self._return_policy = return_policy
        self._transitions = transitions
        self._refunds = refunds
        self._notifications = notifications
        self._audit = audit
        self._clock = clock or SystemClock()

    # ------------------------------------------------------------------
    # Reading (with horizontal access control)
    # ------------------------------------------------------------------

    def list_for_customer(self, customer: User) -> list[Order]:
        return self._orders.list_for_customer(customer.id)

    def get_for_user(self, order_id: int, user: User) -> Order:
        order = self._orders.get(order_id)
        self._access.ensure_can_view(user.id, user.role, order)
        return order

    def list_all(self) -> list[Order]:
        return self._orders.list_all()

    def list_pending_requests(self) -> list[OrderRequest]:
        return self._requests.list_pending()

    # ------------------------------------------------------------------
    # Returns
    # ------------------------------------------------------------------

    def request_return(self, order_id: int, *, customer: User, reason: str) -> OrderRequest:
        order = self._orders.get(order_id)
        self._access.ensure_can_act_as_owner(customer.id, customer.role, order)
        rejection = self._return_policy.rejection_reason(order, self._clock.now())
        if rejection is not None:
            raise ConflictError(
                "This order is not eligible for a return.",
                details={"reason": rejection},
            )
        if self._requests.pending_for_order(order.id, RequestType.RETURN) is not None:
            raise ConflictError("A return request is already pending for this order.")
        self._transitions.execute(
            order,
            OrderEvent.REQUEST_RETURN,
            actor=ActorKind.CUSTOMER,
            actor_user_id=customer.id,
            note=reason,
        )
        request = self._requests.add(
            OrderRequest(
                order_id=order.id,
                request_type=RequestType.RETURN,
                reason=reason,
                requested_by=customer.id,
            )
        )
        self._audit.record(
            actor_user_id=customer.id,
            action="order.return_requested",
            entity_type="order",
            entity_id=order.id,
            details={"request_id": request.id, "reason": reason},
        )
        return request

    def decide_return(
        self, request_id: int, *, approve: bool, decider: User, note: str = ""
    ) -> OrderRequest:
        request = self._requests.get(request_id)
        if request.request_type != RequestType.RETURN:
            raise ConflictError("Request type mismatch.")
        if request.status != RequestStatus.PENDING:
            raise ConflictError("This request was already decided.")
        order = request.order
        event = OrderEvent.APPROVE_RETURN if approve else OrderEvent.REJECT_RETURN
        self._transitions.execute(
            order,
            event,
            actor=AuthorizationPolicy.actor_kind_for(decider.role),
            actor_user_id=decider.id,
            note=note,
        )
        request.status = RequestStatus.APPROVED if approve else RequestStatus.REJECTED
        request.decided_by = decider.id
        request.decision_note = note
        request.decided_at = self._clock.now()
        if approve:
            self._notifications.return_instructions(order)
        self._audit.record(
            actor_user_id=decider.id,
            action="order.return_decided",
            entity_type="order",
            entity_id=order.id,
            details={"request_id": request.id, "approved": approve},
        )
        return request

    def refund_returned_order(self, order_id: int, *, actor: User) -> Order:
        """Final step of the return flow: RETURNED → REFUNDED with a money refund."""
        order = self._orders.get(order_id)
        self._transitions.execute(
            order,
            OrderEvent.REFUND,
            actor=AuthorizationPolicy.actor_kind_for(actor.role),
            actor_user_id=actor.id,
            note="Return refunded",
        )
        self._refunds.refund_order_payment(
            order, reason="Returned goods refunded", actor_user_id=actor.id
        )
        self._notifications.refund_completed(order)
        return order
