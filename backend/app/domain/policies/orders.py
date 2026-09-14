"""Order access and return-eligibility rules."""

from __future__ import annotations

from datetime import datetime, timedelta

from app.domain.entities.enums import OrderStatus, UserRole
from app.domain.entities.interfaces import OrderLike
from app.domain.errors import NotFoundError, PermissionDeniedError

#: Roles that may read any order (customers are limited to their own).
_READ_ALL_ROLES = frozenset(
    {UserRole.WAREHOUSE_STAFF, UserRole.SUPPORT_AGENT, UserRole.ADMINISTRATOR}
)

#: States in which the owner may cancel directly (without a request).
CUSTOMER_CANCELLABLE_STATES = frozenset({OrderStatus.PENDING_PAYMENT, OrderStatus.PAID})


class OrderAccessPolicy:
    """Horizontal access: who may see or act on a given order."""

    def can_view(self, user_id: int, role: UserRole, order: OrderLike) -> bool:
        if role in _READ_ALL_ROLES:
            return True
        return order.customer_id == user_id

    def ensure_can_view(self, user_id: int, role: UserRole, order: OrderLike) -> None:
        """Foreign customers get 404, not 403 — the order's existence is not leaked."""
        if not self.can_view(user_id, role, order):
            raise NotFoundError("Order not found.", details={"order_id": order.id})

    def ensure_owner(self, user_id: int, order: OrderLike) -> None:
        if order.customer_id != user_id:
            raise NotFoundError("Order not found.", details={"order_id": order.id})

    def ensure_can_act_as_owner(self, user_id: int, role: UserRole, order: OrderLike) -> None:
        """Customer lifecycle actions (cancel, request return) — owner only."""
        if role != UserRole.CUSTOMER:
            raise PermissionDeniedError(
                "Only the customer who placed the order may perform this action."
            )
        self.ensure_owner(user_id, order)


class ReturnEligibilityPolicy:
    """A delivered order may be returned within the return window."""

    def __init__(self, return_window_days: int) -> None:
        if return_window_days <= 0:
            raise ValueError("return_window_days must be positive")
        self.return_window_days = return_window_days

    def is_eligible(self, order: OrderLike, now: datetime) -> bool:
        if order.status != OrderStatus.DELIVERED:
            return False
        if order.delivered_at is None:
            return False
        deadline = order.delivered_at + timedelta(days=self.return_window_days)
        return now <= deadline

    def rejection_reason(self, order: OrderLike, now: datetime) -> str | None:
        if order.status != OrderStatus.DELIVERED:
            return "order_not_delivered"
        if order.delivered_at is None:
            return "missing_delivery_timestamp"
        if now > order.delivered_at + timedelta(days=self.return_window_days):
            return "return_window_expired"
        return None
