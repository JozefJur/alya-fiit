"""Order state machine and shipment pipeline rules."""

import pytest

from app.domain.entities.enums import ActorKind, OrderEvent, OrderStatus
from app.domain.errors import InvalidStateTransitionError, PermissionDeniedError
from app.domain.state_machines.order_state_machine import (
    TRANSITIONS,
    OrderStateMachine,
)
from app.domain.state_machines.shipment_state_machine import ShipmentStateMachine


class TestTargetState:
    def test_defined_transition_returns_the_next_state(self):
        machine = OrderStateMachine()
        assert (
            machine.target_state(OrderStatus.PAID, OrderEvent.START_PICKING) == OrderStatus.PICKING
        )

    def test_undefined_transition_raises_with_context(self):
        machine = OrderStateMachine()
        with pytest.raises(InvalidStateTransitionError) as error:
            machine.target_state(OrderStatus.PAID, OrderEvent.SHIP)
        assert error.value.details == {"status": "PAID", "event": "ship"}

    def test_terminal_states_have_no_outgoing_transitions(self):
        machine = OrderStateMachine()
        for status in (OrderStatus.CANCELLED, OrderStatus.PAYMENT_FAILED, OrderStatus.REFUNDED):
            assert machine.is_terminal(status)
            assert [event for (state, event) in TRANSITIONS if state == status] == []


class TestApplyWithRoles:
    def test_warehouse_can_start_picking_a_paid_order(self):
        machine = OrderStateMachine()
        assert (
            machine.apply(OrderStatus.PAID, OrderEvent.START_PICKING, ActorKind.WAREHOUSE_STAFF)
            == OrderStatus.PICKING
        )

    def test_customer_cannot_start_picking(self):
        machine = OrderStateMachine()
        with pytest.raises(PermissionDeniedError):
            machine.apply(OrderStatus.PAID, OrderEvent.START_PICKING, ActorKind.CUSTOMER)

    def test_customer_may_cancel_a_paid_order(self):
        machine = OrderStateMachine()
        assert (
            machine.apply(OrderStatus.PAID, OrderEvent.CANCEL, ActorKind.CUSTOMER)
            == OrderStatus.CANCELLED
        )

    def test_customer_cannot_cancel_after_shipping(self):
        machine = OrderStateMachine()
        with pytest.raises(InvalidStateTransitionError):
            machine.apply(OrderStatus.SHIPPED, OrderEvent.CANCEL, ActorKind.CUSTOMER)

    def test_only_the_system_confirms_payments(self):
        machine = OrderStateMachine()
        assert (
            machine.apply(
                OrderStatus.PENDING_PAYMENT, OrderEvent.PAYMENT_AUTHORIZED, ActorKind.SYSTEM
            )
            == OrderStatus.PAID
        )
        for actor in (ActorKind.CUSTOMER, ActorKind.WAREHOUSE_STAFF, ActorKind.ADMINISTRATOR):
            with pytest.raises(PermissionDeniedError):
                machine.apply(OrderStatus.PENDING_PAYMENT, OrderEvent.PAYMENT_AUTHORIZED, actor)

    def test_support_decides_cancel_requests(self):
        machine = OrderStateMachine()
        assert (
            machine.apply(
                OrderStatus.CANCEL_REQUESTED, OrderEvent.APPROVE_CANCEL, ActorKind.SUPPORT_AGENT
            )
            == OrderStatus.CANCELLED
        )
        assert (
            machine.apply(
                OrderStatus.CANCEL_REQUESTED, OrderEvent.REJECT_CANCEL, ActorKind.SUPPORT_AGENT
            )
            == OrderStatus.PICKING
        )

    def test_warehouse_cannot_decide_cancel_requests(self):
        machine = OrderStateMachine()
        with pytest.raises(PermissionDeniedError):
            machine.apply(
                OrderStatus.CANCEL_REQUESTED,
                OrderEvent.APPROVE_CANCEL,
                ActorKind.WAREHOUSE_STAFF,
            )

    def test_can_apply_is_false_for_undefined_transitions(self):
        machine = OrderStateMachine()
        assert not machine.can_apply(OrderStatus.DRAFT, OrderEvent.SHIP, ActorKind.ADMINISTRATOR)


class TestAllowedEvents:
    def test_customer_sees_only_own_actions_on_a_paid_order(self):
        events = OrderStateMachine().allowed_events(OrderStatus.PAID, ActorKind.CUSTOMER)
        assert set(events) == {OrderEvent.CANCEL}

    def test_warehouse_sees_the_next_fulfillment_step(self):
        events = OrderStateMachine().allowed_events(OrderStatus.PAID, ActorKind.WAREHOUSE_STAFF)
        assert set(events) == {OrderEvent.START_PICKING}

    def test_terminal_state_offers_nothing(self):
        assert (
            OrderStateMachine().allowed_events(OrderStatus.CANCELLED, ActorKind.ADMINISTRATOR) == []
        )

    def test_delivered_order_can_be_returned_by_its_customer(self):
        events = OrderStateMachine().allowed_events(OrderStatus.DELIVERED, ActorKind.CUSTOMER)
        assert set(events) == {OrderEvent.REQUEST_RETURN}


class TestShipmentStateMachine:
    def test_next_event_follows_the_pipeline(self):
        machine = ShipmentStateMachine()
        assert machine.next_event(OrderStatus.PAID) == OrderEvent.START_PICKING
        assert machine.next_event(OrderStatus.READY_TO_SHIP) == OrderEvent.SHIP

    def test_delivered_order_has_no_next_step(self):
        machine = ShipmentStateMachine()
        assert not machine.can_advance(OrderStatus.DELIVERED)
        with pytest.raises(InvalidStateTransitionError):
            machine.next_event(OrderStatus.DELIVERED)

    def test_steps_remaining_counts_down_to_delivery(self):
        machine = ShipmentStateMachine()
        assert machine.steps_remaining(OrderStatus.PAID) == 4
        assert machine.steps_remaining(OrderStatus.SHIPPED) == 1
        assert machine.steps_remaining(OrderStatus.DELIVERED) == 0

    def test_state_outside_the_pipeline_is_rejected(self):
        with pytest.raises(InvalidStateTransitionError):
            ShipmentStateMachine().steps_remaining(OrderStatus.CANCELLED)

    def test_queue_states_include_work_and_exclude_finished_orders(self):
        queue = ShipmentStateMachine().queue_states()
        assert OrderStatus.PAID in queue
        assert OrderStatus.CANCEL_REQUESTED in queue
        assert OrderStatus.DELIVERED not in queue
        assert OrderStatus.CANCELLED not in queue
