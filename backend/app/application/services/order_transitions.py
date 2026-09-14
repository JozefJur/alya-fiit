"""Shared helper: apply an order transition with history + audit in one place."""

from __future__ import annotations

from app.application.services.audit import AuditLogService
from app.domain.entities.enums import ActorKind, OrderEvent, OrderStatus
from app.domain.state_machines.order_state_machine import OrderStateMachine
from app.infrastructure.adapters.clock import Clock
from app.infrastructure.persistence.models import Order, OrderStatusHistory


class OrderTransitionExecutor:
    """Validates the transition, mutates the order, and records history/audit.

    Side effects beyond the order row (stock, payments, notifications) belong
    to the calling use case — this class keeps the bookkeeping consistent.
    """

    def __init__(
        self, state_machine: OrderStateMachine, audit: AuditLogService, clock: Clock
    ) -> None:
        self._machine = state_machine
        self._audit = audit
        self._clock = clock

    def execute(
        self,
        order: Order,
        event: OrderEvent,
        *,
        actor: ActorKind,
        actor_user_id: int | None,
        note: str = "",
    ) -> OrderStatus:
        previous = order.status
        order.status = self._machine.apply(previous, event, actor)
        now = self._clock.now()
        order.updated_at = now
        if order.status == OrderStatus.SHIPPED:
            order.shipped_at = now
        if order.status == OrderStatus.DELIVERED:
            order.delivered_at = now
        order.status_history.append(
            OrderStatusHistory(
                from_status=previous,
                to_status=order.status,
                event=event.value,
                actor_user_id=actor_user_id,
                note=note,
                created_at=now,
            )
        )
        self._audit.record(
            actor_user_id=actor_user_id,
            action="order.status_changed",
            entity_type="order",
            entity_id=order.id,
            details={
                "from": previous.value,
                "to": order.status.value,
                "event": event.value,
                "note": note,
            },
        )
        return order.status
