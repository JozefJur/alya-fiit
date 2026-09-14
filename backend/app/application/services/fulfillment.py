"""Warehouse workflows: picking queue, shipping, delivery, return receipt."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from app.application.services.inventory import InventoryService
from app.application.services.notifications import NotificationService
from app.application.services.order_transitions import OrderTransitionExecutor
from app.domain.entities.enums import OrderEvent, OrderStatus
from app.domain.policies.authorization import AuthorizationPolicy
from app.domain.state_machines.shipment_state_machine import ShipmentStateMachine
from app.infrastructure.adapters.clock import Clock, SystemClock
from app.infrastructure.persistence.models import Order, User
from app.infrastructure.repositories.orders import OrderRepository


class DeliveryEstimateService:
    """Estimates a delivery date by adding business days (Mon–Fri) to a start."""

    def __init__(self, business_days: int) -> None:
        if business_days < 0:
            raise ValueError("business_days must be >= 0")
        self.business_days = business_days

    def estimate_from(self, start: datetime) -> date:
        current = start.date()
        remaining = self.business_days
        while remaining > 0:
            current += timedelta(days=1)
            if current.weekday() < 5:  # Mon..Fri
                remaining -= 1
        return current

    def describe(self, start: datetime) -> str:
        return self.estimate_from(start).isoformat()


class PickingService:
    """Queue view and the first fulfillment steps."""

    def __init__(
        self,
        orders: OrderRepository,
        transitions: OrderTransitionExecutor,
        state_machine: ShipmentStateMachine | None = None,
    ) -> None:
        self._orders = orders
        self._transitions = transitions
        self._machine = state_machine or ShipmentStateMachine()

    def work_queue(self) -> list[Order]:
        return self._orders.list_by_statuses(self._machine.queue_states())

    def start_picking(self, order_id: int, *, actor: User) -> Order:
        return self._advance(order_id, OrderEvent.START_PICKING, actor)

    def mark_ready(self, order_id: int, *, actor: User) -> Order:
        return self._advance(order_id, OrderEvent.MARK_READY, actor)

    def _advance(self, order_id: int, event: OrderEvent, actor: User) -> Order:
        order = self._orders.get(order_id)
        self._transitions.execute(
            order,
            event,
            actor=AuthorizationPolicy.actor_kind_for(actor.role),
            actor_user_id=actor.id,
        )
        return order


class ShipmentService:
    """Shipping consumes reserved stock; delivery and return receipt close the loop."""

    def __init__(
        self,
        orders: OrderRepository,
        inventory: InventoryService,
        notifications: NotificationService,
        transitions: OrderTransitionExecutor,
        delivery_estimate: DeliveryEstimateService,
        clock: Clock | None = None,
    ) -> None:
        self._orders = orders
        self._inventory = inventory
        self._notifications = notifications
        self._transitions = transitions
        self._delivery = delivery_estimate
        self._clock = clock or SystemClock()

    def ship(self, order_id: int, *, actor: User) -> Order:
        order = self._orders.get(order_id)
        self._transitions.execute(
            order,
            OrderEvent.SHIP,
            actor=AuthorizationPolicy.actor_kind_for(actor.role),
            actor_user_id=actor.id,
        )
        self._inventory.consume_for_order(order, actor_user_id=actor.id)
        estimate = self._delivery.describe(order.shipped_at or self._clock.now())
        self._notifications.order_shipped(order, estimated_delivery=estimate)
        return order

    def mark_delivered(self, order_id: int, *, actor: User) -> Order:
        order = self._orders.get(order_id)
        self._transitions.execute(
            order,
            OrderEvent.MARK_DELIVERED,
            actor=AuthorizationPolicy.actor_kind_for(actor.role),
            actor_user_id=actor.id,
        )
        self._notifications.order_delivered(order)
        return order

    def receive_return(self, order_id: int, *, actor: User) -> Order:
        order = self._orders.get(order_id)
        self._transitions.execute(
            order,
            OrderEvent.RECEIVE_RETURN,
            actor=AuthorizationPolicy.actor_kind_for(actor.role),
            actor_user_id=actor.id,
        )
        self._inventory.restock_for_order(order, actor_user_id=actor.id)
        return order

    def expected_delivery_for(self, order: Order) -> str | None:
        if order.status not in (OrderStatus.SHIPPED, OrderStatus.DELIVERED):
            return None
        if order.shipped_at is None:
            return None
        return self._delivery.describe(order.shipped_at)
