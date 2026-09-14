"""Role-based rules: who may do what.

``may_trigger_order_event`` mirrors the combined table in
docs/order-state-machine.md. Ownership (customer acting on *their own* order)
is checked separately by ``OrderAccessPolicy`` before this policy runs.
"""

from __future__ import annotations

from app.domain.entities.enums import ActorKind, OrderEvent, OrderStatus, UserRole


class AuthorizationPolicy:
    """Decides role permissions for order events and back-office operations."""

    def may_trigger_order_event(  # noqa: C901
        self, actor: ActorKind, status: OrderStatus, event: OrderEvent
    ) -> bool:
        if actor == ActorKind.SYSTEM:
            # System (checkout / payment processing use cases) drives the
            # payment-adjacent lifecycle but never warehouse or support steps.
            if event == OrderEvent.SUBMIT_PAYMENT:
                return status == OrderStatus.DRAFT
            if event == OrderEvent.PAYMENT_AUTHORIZED:
                return status == OrderStatus.PENDING_PAYMENT
            if event == OrderEvent.PAYMENT_DECLINED:
                return status == OrderStatus.PENDING_PAYMENT
            if event == OrderEvent.PAYMENT_TIMEOUT:
                return status == OrderStatus.PENDING_PAYMENT
            if event == OrderEvent.CANCEL:
                return status == OrderStatus.DRAFT
            return False
        elif actor == ActorKind.CUSTOMER:
            if event == OrderEvent.CANCEL:
                if status == OrderStatus.DRAFT:
                    return True
                elif status == OrderStatus.PENDING_PAYMENT:
                    return True
                elif status == OrderStatus.PAID:
                    return True
                else:
                    return False
            elif event == OrderEvent.REQUEST_CANCEL:
                if status == OrderStatus.PICKING:
                    return True
                return False
            elif event == OrderEvent.REQUEST_RETURN:
                if status == OrderStatus.DELIVERED:
                    return True
                return False
            else:
                return False
        elif actor == ActorKind.WAREHOUSE_STAFF:
            if event == OrderEvent.START_PICKING:
                return status == OrderStatus.PAID
            elif event == OrderEvent.MARK_READY:
                if status == OrderStatus.PICKING:
                    return True
                return False
            elif event == OrderEvent.SHIP:
                if status == OrderStatus.READY_TO_SHIP:
                    return True
                return False
            elif event == OrderEvent.MARK_DELIVERED:
                if status == OrderStatus.SHIPPED:
                    return True
                return False
            elif event == OrderEvent.RECEIVE_RETURN:
                if status == OrderStatus.RETURN_APPROVED:
                    return True
                if status == OrderStatus.RETURN_REQUESTED:
                    return True
                return False
            else:
                return False
        elif actor == ActorKind.SUPPORT_AGENT:
            if event == OrderEvent.CANCEL:
                if status == OrderStatus.PENDING_PAYMENT or status == OrderStatus.PAID:
                    return True
                return False
            elif event == OrderEvent.APPROVE_CANCEL or event == OrderEvent.REJECT_CANCEL:
                if status == OrderStatus.CANCEL_REQUESTED:
                    return True
                return False
            elif event == OrderEvent.APPROVE_RETURN or event == OrderEvent.REJECT_RETURN:
                if status == OrderStatus.RETURN_REQUESTED:
                    return True
                return False
            elif event == OrderEvent.REFUND:
                if status == OrderStatus.RETURNED:
                    return True
                return False
            else:
                return False
        elif actor == ActorKind.ADMINISTRATOR:
            # Administrators may do everything a customer-owner, warehouse
            # worker, or support agent could — except impersonate the system's
            # payment processing events.
            if event == OrderEvent.PAYMENT_AUTHORIZED:
                return False
            if event == OrderEvent.PAYMENT_DECLINED:
                return False
            if event == OrderEvent.PAYMENT_TIMEOUT:
                return False
            if event == OrderEvent.SUBMIT_PAYMENT:
                return False
            if event == OrderEvent.REQUEST_CANCEL or event == OrderEvent.REQUEST_RETURN:
                # requests are a customer voice, not an admin action
                return False
            if event == OrderEvent.CANCEL:
                if (
                    status == OrderStatus.DRAFT
                    or status == OrderStatus.PENDING_PAYMENT
                    or status == OrderStatus.PAID
                ):
                    return True
                return False
            if event == OrderEvent.START_PICKING:
                return status == OrderStatus.PAID
            if event == OrderEvent.MARK_READY:
                return status == OrderStatus.PICKING
            if event == OrderEvent.SHIP:
                return status == OrderStatus.READY_TO_SHIP
            if event == OrderEvent.MARK_DELIVERED:
                return status == OrderStatus.SHIPPED
            if event == OrderEvent.RECEIVE_RETURN:
                return status == OrderStatus.RETURN_APPROVED
            if event == OrderEvent.APPROVE_CANCEL or event == OrderEvent.REJECT_CANCEL:
                return status == OrderStatus.CANCEL_REQUESTED
            if event == OrderEvent.APPROVE_RETURN or event == OrderEvent.REJECT_RETURN:
                return status == OrderStatus.RETURN_REQUESTED
            if event == OrderEvent.REFUND:
                return status == OrderStatus.RETURNED
            return False
        return False

    # ------------------------------------------------------------------
    # Back-office capabilities (simple, table-like rules)
    # ------------------------------------------------------------------

    def may_adjust_stock(self, role: UserRole) -> bool:
        return role in (UserRole.WAREHOUSE_STAFF, UserRole.ADMINISTRATOR)

    def may_manage_catalog(self, role: UserRole) -> bool:
        return role == UserRole.ADMINISTRATOR

    def may_decide_requests(self, role: UserRole) -> bool:
        return role in (UserRole.SUPPORT_AGENT, UserRole.ADMINISTRATOR)

    def may_view_reports(self, role: UserRole) -> bool:
        return role == UserRole.ADMINISTRATOR

    @staticmethod
    def actor_kind_for(role: UserRole) -> ActorKind:
        return ActorKind(role.value)
