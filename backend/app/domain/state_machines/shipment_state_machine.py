"""Warehouse-facing view of the order lifecycle.

The fulfillment pipeline is a strict sequence; this machine answers
warehouse-specific questions (what is the next step, which orders belong in
the queue) on top of the general ``OrderStateMachine`` rules.
"""

from __future__ import annotations

from app.domain.entities.enums import OrderEvent, OrderStatus
from app.domain.errors import InvalidStateTransitionError

#: The fulfillment pipeline in processing order.
PIPELINE: tuple[OrderStatus, ...] = (
    OrderStatus.PAID,
    OrderStatus.PICKING,
    OrderStatus.READY_TO_SHIP,
    OrderStatus.SHIPPED,
    OrderStatus.DELIVERED,
)

_NEXT_EVENT: dict[OrderStatus, OrderEvent] = {
    OrderStatus.PAID: OrderEvent.START_PICKING,
    OrderStatus.PICKING: OrderEvent.MARK_READY,
    OrderStatus.READY_TO_SHIP: OrderEvent.SHIP,
    OrderStatus.SHIPPED: OrderEvent.MARK_DELIVERED,
}


class ShipmentStateMachine:
    """Pure helper for the warehouse workflow."""

    def is_in_pipeline(self, status: OrderStatus) -> bool:
        return status in PIPELINE

    def queue_states(self) -> tuple[OrderStatus, ...]:
        """States a warehouse worker sees in the work queue (not yet delivered)."""
        return (
            OrderStatus.PAID,
            OrderStatus.PICKING,
            OrderStatus.CANCEL_REQUESTED,
            OrderStatus.READY_TO_SHIP,
            OrderStatus.SHIPPED,
            OrderStatus.RETURN_APPROVED,
        )

    def next_event(self, status: OrderStatus) -> OrderEvent:
        """The single next fulfillment step from ``status``."""
        try:
            return _NEXT_EVENT[status]
        except KeyError:
            raise InvalidStateTransitionError(
                f"No fulfillment step is available from state '{status.value}'.",
                details={"status": status.value},
            ) from None

    def can_advance(self, status: OrderStatus) -> bool:
        return status in _NEXT_EVENT

    def steps_remaining(self, status: OrderStatus) -> int:
        """How many fulfillment steps remain until DELIVERED (0 when delivered)."""
        if status not in PIPELINE:
            raise InvalidStateTransitionError(
                f"Order in state '{status.value}' is not in the fulfillment pipeline.",
                details={"status": status.value},
            )
        return len(PIPELINE) - 1 - PIPELINE.index(status)
