"""Inventory service: reservations, releases, consumption, adjustments, low stock."""

from __future__ import annotations

from app.application.commands.commands import StockAdjustmentCommand
from app.application.services.audit import AuditLogService
from app.application.services.notifications import NotificationService
from app.domain.entities.enums import (
    MovementType,
    ReservationStatus,
    UserRole,
)
from app.domain.errors import ConflictError, ValidationError
from app.domain.policies.catalog import VariantAvailabilityPolicy
from app.domain.policies.inventory import LowStockPolicy
from app.infrastructure.adapters.clock import Clock, SystemClock
from app.infrastructure.persistence.models import (
    Order,
    StockLevel,
    StockMovement,
    StockReservation,
)
from app.infrastructure.repositories.inventory import (
    ReservationRepository,
    StockLevelRepository,
    StockMovementRepository,
)
from app.infrastructure.repositories.users import UserRepository


class InventoryService:
    def __init__(
        self,
        stock_levels: StockLevelRepository,
        movements: StockMovementRepository,
        reservations: ReservationRepository,
        audit: AuditLogService,
        notifications: NotificationService,
        users: UserRepository,
        low_stock_policy: LowStockPolicy,
        availability_policy: VariantAvailabilityPolicy | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._stock_levels = stock_levels
        self._movements = movements
        self._reservations = reservations
        self._audit = audit
        self._notifications = notifications
        self._users = users
        self._low_stock = low_stock_policy
        self._availability = availability_policy or VariantAvailabilityPolicy()
        self._clock = clock or SystemClock()

    # ------------------------------------------------------------------
    # Reservation lifecycle (tied to orders)
    # ------------------------------------------------------------------

    def reserve_for_order(self, order: Order, lines: list[tuple[int, int]]) -> None:
        """Reserve ``[(variant_id, quantity), ...]`` for the order atomically.

        The caller's transaction guarantees all-or-nothing: the first failing
        line raises and rolls back every previous reservation.
        """
        for variant_id, quantity in lines:
            level = self._stock_levels.get_for_variant(variant_id)
            self._availability.ensure_available(level, quantity)
            level.reserved += quantity
            self._reservations.add(
                StockReservation(order_id=order.id, variant_id=variant_id, quantity=quantity)
            )
            self._movements.add(
                StockMovement(
                    variant_id=variant_id,
                    movement_type=MovementType.RESERVATION,
                    quantity=-quantity,
                    reason="Reserved for order",
                    reference=order.order_number,
                    actor_user_id=order.customer_id,
                )
            )
        self._audit.record(
            actor_user_id=order.customer_id,
            action="stock.reserved",
            entity_type="order",
            entity_id=order.id,
            details={"lines": [{"variant_id": v, "quantity": q} for v, q in lines]},
        )

    def release_for_order(self, order: Order, *, reason: str, actor_user_id: int | None) -> int:
        """Release all active reservations of the order; returns released count."""
        released = 0
        for reservation in self._reservations.active_for_order(order.id):
            level = self._stock_levels.get_for_variant(reservation.variant_id)
            if level.reserved < reservation.quantity:
                raise ConflictError(
                    "Stock ledger inconsistent: reserved less than reservation.",
                    details={"variant_id": reservation.variant_id},
                )
            level.reserved -= reservation.quantity
            reservation.status = ReservationStatus.RELEASED
            reservation.released_at = self._clock.now()
            self._movements.add(
                StockMovement(
                    variant_id=reservation.variant_id,
                    movement_type=MovementType.RELEASE,
                    quantity=reservation.quantity,
                    reason=reason,
                    reference=order.order_number,
                    actor_user_id=actor_user_id,
                )
            )
            released += 1
        if released:
            self._audit.record(
                actor_user_id=actor_user_id,
                action="stock.released",
                entity_type="order",
                entity_id=order.id,
                details={"reason": reason, "reservations": released},
            )
        return released

    def consume_for_order(self, order: Order, *, actor_user_id: int) -> None:
        """Shipment: reserved goods leave the warehouse (on_hand and reserved drop)."""
        active = self._reservations.active_for_order(order.id)
        if not active:
            raise ConflictError(
                "No active reservations to ship for this order.",
                details={"order_id": order.id},
            )
        for reservation in active:
            level = self._stock_levels.get_for_variant(reservation.variant_id)
            if level.on_hand < reservation.quantity or level.reserved < reservation.quantity:
                raise ConflictError(
                    "Stock ledger inconsistent for shipment.",
                    details={"variant_id": reservation.variant_id},
                )
            level.on_hand -= reservation.quantity
            level.reserved -= reservation.quantity
            reservation.status = ReservationStatus.CONSUMED
            reservation.released_at = self._clock.now()
            self._movements.add(
                StockMovement(
                    variant_id=reservation.variant_id,
                    movement_type=MovementType.SHIPMENT,
                    quantity=-reservation.quantity,
                    reason="Order shipped",
                    reference=order.order_number,
                    actor_user_id=actor_user_id,
                )
            )
            self._alert_if_low(level)
        self._audit.record(
            actor_user_id=actor_user_id,
            action="stock.consumed",
            entity_type="order",
            entity_id=order.id,
            details={"reservations": len(active)},
        )

    def restock_for_order(self, order: Order, *, actor_user_id: int) -> None:
        """Return receipt: consumed goods come back into on_hand."""
        for item in order.items:
            level = self._stock_levels.get_for_variant(item.variant_id)
            level.on_hand += item.quantity
            self._movements.add(
                StockMovement(
                    variant_id=item.variant_id,
                    movement_type=MovementType.RETURN,
                    quantity=item.quantity,
                    reason="Customer return received",
                    reference=order.order_number,
                    actor_user_id=actor_user_id,
                )
            )

    # ------------------------------------------------------------------
    # Manual stock operations (admin / warehouse)
    # ------------------------------------------------------------------

    def adjust(self, command: StockAdjustmentCommand) -> StockLevel:
        if not command.reason or not command.reason.strip():
            raise ValidationError("A reason is required for stock adjustments.")
        if command.quantity_change == 0:
            raise ValidationError("Adjustment must change the quantity.")
        level = self._stock_levels.get_for_variant(command.variant_id)
        new_on_hand = level.on_hand + command.quantity_change
        if new_on_hand < 0:
            raise ConflictError(
                "Adjustment would make on-hand stock negative.",
                details={"on_hand": level.on_hand, "change": command.quantity_change},
            )
        if new_on_hand < level.reserved:
            raise ConflictError(
                "Adjustment would drop on-hand below the reserved quantity.",
                details={"reserved": level.reserved, "new_on_hand": new_on_hand},
            )
        level.on_hand = new_on_hand
        self._movements.add(
            StockMovement(
                variant_id=command.variant_id,
                movement_type=MovementType.ADJUSTMENT,
                quantity=command.quantity_change,
                reason=command.reason.strip(),
                actor_user_id=command.actor_user_id,
            )
        )
        self._audit.record(
            actor_user_id=command.actor_user_id,
            action="stock.adjusted",
            entity_type="variant",
            entity_id=command.variant_id,
            details={"change": command.quantity_change, "reason": command.reason.strip()},
        )
        self._alert_if_low(level)
        return level

    def receive(
        self, *, variant_id: int, quantity: int, actor_user_id: int, reason: str = "Goods receipt"
    ) -> StockLevel:
        if quantity <= 0:
            raise ValidationError("Receipt quantity must be positive.")
        level = self._stock_levels.get_for_variant(variant_id)
        level.on_hand += quantity
        self._movements.add(
            StockMovement(
                variant_id=variant_id,
                movement_type=MovementType.RECEIPT,
                quantity=quantity,
                reason=reason,
                actor_user_id=actor_user_id,
            )
        )
        self._audit.record(
            actor_user_id=actor_user_id,
            action="stock.received",
            entity_type="variant",
            entity_id=variant_id,
            details={"quantity": quantity},
        )
        return level

    def set_low_stock_threshold(
        self, *, variant_id: int, threshold: int | None, actor_user_id: int
    ) -> StockLevel:
        if threshold is not None and threshold < 0:
            raise ValidationError("Threshold must be >= 0 (or empty for the default).")
        level = self._stock_levels.get_for_variant(variant_id)
        level.low_stock_threshold = threshold
        self._audit.record(
            actor_user_id=actor_user_id,
            action="stock.threshold_changed",
            entity_type="variant",
            entity_id=variant_id,
            details={"threshold": threshold},
        )
        return level

    # ------------------------------------------------------------------
    # Low-stock alerting
    # ------------------------------------------------------------------

    def low_stock_levels(self) -> list[StockLevel]:
        return [level for level in self._stock_levels.list_all() if self._low_stock.is_low(level)]

    def _alert_if_low(self, level: StockLevel) -> None:
        if not self._low_stock.is_low(level):
            return
        sku = level.variant.sku if level.variant else str(level.variant_id)
        for user in self._users.list_all():
            if user.role == UserRole.ADMINISTRATOR and user.is_active:
                self._notifications.low_stock_alert(
                    admin_user_id=user.id, sku=sku, available=level.available
                )
