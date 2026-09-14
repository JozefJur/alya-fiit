"""Order state machine.

Single source of truth for *which transition exists* (state × event → state).
*Who may trigger it* is decided by ``AuthorizationPolicy`` (see
docs/order-state-machine.md for the combined table); the machine calls into it
so every transition passes through both checks.
"""

from __future__ import annotations

from app.domain.entities.enums import ActorKind, OrderEvent, OrderStatus
from app.domain.errors import InvalidStateTransitionError, PermissionDeniedError
from app.domain.policies.authorization import AuthorizationPolicy

TRANSITIONS: dict[tuple[OrderStatus, OrderEvent], OrderStatus] = {
    (OrderStatus.DRAFT, OrderEvent.SUBMIT_PAYMENT): OrderStatus.PENDING_PAYMENT,
    (OrderStatus.DRAFT, OrderEvent.CANCEL): OrderStatus.CANCELLED,
    (OrderStatus.PENDING_PAYMENT, OrderEvent.PAYMENT_AUTHORIZED): OrderStatus.PAID,
    (OrderStatus.PENDING_PAYMENT, OrderEvent.PAYMENT_DECLINED): OrderStatus.PAYMENT_FAILED,
    (OrderStatus.PENDING_PAYMENT, OrderEvent.PAYMENT_TIMEOUT): OrderStatus.PAYMENT_FAILED,
    (OrderStatus.PENDING_PAYMENT, OrderEvent.CANCEL): OrderStatus.CANCELLED,
    (OrderStatus.PAID, OrderEvent.START_PICKING): OrderStatus.PICKING,
    (OrderStatus.PAID, OrderEvent.CANCEL): OrderStatus.CANCELLED,
    (OrderStatus.PICKING, OrderEvent.REQUEST_CANCEL): OrderStatus.CANCEL_REQUESTED,
    (OrderStatus.CANCEL_REQUESTED, OrderEvent.APPROVE_CANCEL): OrderStatus.CANCELLED,
    (OrderStatus.CANCEL_REQUESTED, OrderEvent.REJECT_CANCEL): OrderStatus.PICKING,
    (OrderStatus.PICKING, OrderEvent.MARK_READY): OrderStatus.READY_TO_SHIP,
    (OrderStatus.READY_TO_SHIP, OrderEvent.SHIP): OrderStatus.SHIPPED,
    (OrderStatus.SHIPPED, OrderEvent.MARK_DELIVERED): OrderStatus.DELIVERED,
    (OrderStatus.DELIVERED, OrderEvent.REQUEST_RETURN): OrderStatus.RETURN_REQUESTED,
    (OrderStatus.RETURN_REQUESTED, OrderEvent.APPROVE_RETURN): OrderStatus.RETURN_APPROVED,
    (OrderStatus.RETURN_REQUESTED, OrderEvent.REJECT_RETURN): OrderStatus.DELIVERED,
    (OrderStatus.RETURN_REQUESTED, OrderEvent.RECEIVE_RETURN): OrderStatus.RETURNED,
    (OrderStatus.RETURN_APPROVED, OrderEvent.RECEIVE_RETURN): OrderStatus.RETURNED,
    (OrderStatus.RETURNED, OrderEvent.REFUND): OrderStatus.REFUNDED,
}

TERMINAL_STATES = frozenset(
    {OrderStatus.CANCELLED, OrderStatus.PAYMENT_FAILED, OrderStatus.REFUNDED}
)


class OrderStateMachine:
    """Validates and applies order status transitions (pure, no persistence)."""

    def __init__(self, authorization: AuthorizationPolicy | None = None) -> None:
        self._authorization = authorization or AuthorizationPolicy()

    def target_state(self, current: OrderStatus, event: OrderEvent) -> OrderStatus:
        """The state ``event`` leads to from ``current``; raises if undefined."""
        try:
            return TRANSITIONS[(current, event)]
        except KeyError:
            raise InvalidStateTransitionError(
                f"Event '{event.value}' is not allowed in state '{current.value}'.",
                details={"status": current.value, "event": event.value},
            ) from None

    def can_apply(self, current: OrderStatus, event: OrderEvent, actor: ActorKind) -> bool:
        if (current, event) not in TRANSITIONS:
            return False
        return self._authorization.may_trigger_order_event(actor, current, event)

    def apply(self, current: OrderStatus, event: OrderEvent, actor: ActorKind) -> OrderStatus:
        """Return the next state, enforcing both transition and role rules."""
        target = self.target_state(current, event)
        if not self._authorization.may_trigger_order_event(actor, current, event):
            raise PermissionDeniedError(
                f"Role '{actor.value}' may not trigger '{event.value}' in state '{current.value}'.",
                details={"status": current.value, "event": event.value, "actor": actor.value},
            )
        return target

    def allowed_events(self, current: OrderStatus, actor: ActorKind) -> list[OrderEvent]:
        return [
            event
            for (state, event) in TRANSITIONS
            if state == current and self.can_apply(current, event, actor)
        ]

    def is_terminal(self, status: OrderStatus) -> bool:
        return status in TERMINAL_STATES
