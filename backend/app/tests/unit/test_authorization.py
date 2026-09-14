"""Role permissions, order access and return eligibility."""

from datetime import datetime, timedelta

import pytest

from app.domain.entities.enums import ActorKind, OrderEvent, OrderStatus, UserRole
from app.domain.errors import NotFoundError, PermissionDeniedError
from app.domain.policies.authorization import AuthorizationPolicy
from app.domain.policies.orders import OrderAccessPolicy, ReturnEligibilityPolicy
from app.tests.fixtures.doubles import FakeOrder

NOW = datetime(2026, 6, 15, 12, 0, 0)


class TestAuthorizationPolicyOrderEvents:
    @pytest.mark.parametrize(
        ("actor", "status", "event", "expected"),
        [
            (ActorKind.SYSTEM, OrderStatus.DRAFT, OrderEvent.SUBMIT_PAYMENT, True),
            (ActorKind.SYSTEM, OrderStatus.PAID, OrderEvent.SUBMIT_PAYMENT, False),
            (ActorKind.SYSTEM, OrderStatus.PAID, OrderEvent.START_PICKING, False),
            (ActorKind.CUSTOMER, OrderStatus.PAID, OrderEvent.CANCEL, True),
            (ActorKind.CUSTOMER, OrderStatus.PICKING, OrderEvent.CANCEL, False),
            (ActorKind.CUSTOMER, OrderStatus.PICKING, OrderEvent.REQUEST_CANCEL, True),
            (ActorKind.CUSTOMER, OrderStatus.DELIVERED, OrderEvent.REQUEST_RETURN, True),
            (ActorKind.CUSTOMER, OrderStatus.SHIPPED, OrderEvent.REQUEST_RETURN, False),
            (ActorKind.WAREHOUSE_STAFF, OrderStatus.PAID, OrderEvent.START_PICKING, True),
            (ActorKind.WAREHOUSE_STAFF, OrderStatus.PAID, OrderEvent.CANCEL, False),
            (ActorKind.WAREHOUSE_STAFF, OrderStatus.READY_TO_SHIP, OrderEvent.SHIP, True),
            (ActorKind.SUPPORT_AGENT, OrderStatus.PAID, OrderEvent.CANCEL, True),
            (ActorKind.SUPPORT_AGENT, OrderStatus.RETURNED, OrderEvent.REFUND, True),
            (ActorKind.SUPPORT_AGENT, OrderStatus.PAID, OrderEvent.START_PICKING, False),
            (ActorKind.ADMINISTRATOR, OrderStatus.READY_TO_SHIP, OrderEvent.SHIP, True),
            (
                ActorKind.ADMINISTRATOR,
                OrderStatus.PENDING_PAYMENT,
                OrderEvent.PAYMENT_AUTHORIZED,
                False,
            ),
            (ActorKind.ADMINISTRATOR, OrderStatus.PICKING, OrderEvent.REQUEST_CANCEL, False),
        ],
    )
    def test_permission_matrix(self, actor, status, event, expected):
        assert AuthorizationPolicy().may_trigger_order_event(actor, status, event) is expected

    def test_support_cannot_cancel_a_shipped_order(self):
        policy = AuthorizationPolicy()
        assert not policy.may_trigger_order_event(
            ActorKind.SUPPORT_AGENT, OrderStatus.SHIPPED, OrderEvent.CANCEL
        )


class TestAuthorizationPolicyCapabilities:
    def test_stock_adjustments(self):
        policy = AuthorizationPolicy()
        assert policy.may_adjust_stock(UserRole.WAREHOUSE_STAFF)
        assert policy.may_adjust_stock(UserRole.ADMINISTRATOR)
        assert not policy.may_adjust_stock(UserRole.SUPPORT_AGENT)
        assert not policy.may_adjust_stock(UserRole.CUSTOMER)

    def test_catalog_management_is_admin_only(self):
        policy = AuthorizationPolicy()
        assert policy.may_manage_catalog(UserRole.ADMINISTRATOR)
        assert not policy.may_manage_catalog(UserRole.WAREHOUSE_STAFF)

    def test_request_decisions(self):
        policy = AuthorizationPolicy()
        assert policy.may_decide_requests(UserRole.SUPPORT_AGENT)
        assert not policy.may_decide_requests(UserRole.WAREHOUSE_STAFF)

    def test_reports_are_admin_only(self):
        policy = AuthorizationPolicy()
        assert policy.may_view_reports(UserRole.ADMINISTRATOR)
        assert not policy.may_view_reports(UserRole.SUPPORT_AGENT)

    def test_actor_kind_maps_from_role(self):
        assert (
            AuthorizationPolicy.actor_kind_for(UserRole.WAREHOUSE_STAFF)
            == ActorKind.WAREHOUSE_STAFF
        )


class TestOrderAccessPolicy:
    def test_owner_can_view_own_order(self):
        policy = OrderAccessPolicy()
        assert policy.can_view(7, UserRole.CUSTOMER, FakeOrder(customer_id=7))

    def test_other_customer_cannot_view(self):
        policy = OrderAccessPolicy()
        assert not policy.can_view(8, UserRole.CUSTOMER, FakeOrder(customer_id=7))

    def test_foreign_order_is_reported_as_not_found(self):
        policy = OrderAccessPolicy()
        with pytest.raises(NotFoundError):
            policy.ensure_can_view(8, UserRole.CUSTOMER, FakeOrder(customer_id=7))

    @pytest.mark.parametrize(
        "role", [UserRole.WAREHOUSE_STAFF, UserRole.SUPPORT_AGENT, UserRole.ADMINISTRATOR]
    )
    def test_staff_roles_can_view_any_order(self, role):
        policy = OrderAccessPolicy()
        policy.ensure_can_view(999, role, FakeOrder(customer_id=7))

    def test_owner_actions_require_the_customer_role(self):
        policy = OrderAccessPolicy()
        with pytest.raises(PermissionDeniedError):
            policy.ensure_can_act_as_owner(7, UserRole.ADMINISTRATOR, FakeOrder(customer_id=7))

    def test_owner_actions_require_ownership(self):
        policy = OrderAccessPolicy()
        with pytest.raises(NotFoundError):
            policy.ensure_can_act_as_owner(8, UserRole.CUSTOMER, FakeOrder(customer_id=7))


class TestReturnEligibilityPolicy:
    def test_delivered_within_window_is_eligible(self):
        policy = ReturnEligibilityPolicy(return_window_days=14)
        order = FakeOrder(status=OrderStatus.DELIVERED, delivered_at=NOW - timedelta(days=3))
        assert policy.is_eligible(order, NOW)
        assert policy.rejection_reason(order, NOW) is None

    def test_last_day_of_the_window_is_still_eligible(self):
        policy = ReturnEligibilityPolicy(return_window_days=14)
        order = FakeOrder(status=OrderStatus.DELIVERED, delivered_at=NOW - timedelta(days=14))
        assert policy.is_eligible(order, NOW)

    def test_after_the_window_is_rejected(self):
        policy = ReturnEligibilityPolicy(return_window_days=14)
        order = FakeOrder(
            status=OrderStatus.DELIVERED, delivered_at=NOW - timedelta(days=14, seconds=1)
        )
        assert not policy.is_eligible(order, NOW)
        assert policy.rejection_reason(order, NOW) == "return_window_expired"

    def test_undelivered_order_is_rejected(self):
        policy = ReturnEligibilityPolicy(return_window_days=14)
        order = FakeOrder(status=OrderStatus.SHIPPED, delivered_at=None)
        assert policy.rejection_reason(order, NOW) == "order_not_delivered"

    def test_delivered_without_timestamp_is_reported(self):
        policy = ReturnEligibilityPolicy(return_window_days=14)
        order = FakeOrder(status=OrderStatus.DELIVERED, delivered_at=None)
        assert policy.rejection_reason(order, NOW) == "missing_delivery_timestamp"

    def test_non_positive_window_is_a_programming_error(self):
        with pytest.raises(ValueError):
            ReturnEligibilityPolicy(return_window_days=0)
