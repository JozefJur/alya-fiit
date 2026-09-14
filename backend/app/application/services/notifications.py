"""Notification composition — renders subjects/bodies and hands them to the outbox."""

from __future__ import annotations

from app.domain.entities.enums import NotificationType
from app.infrastructure.adapters.notification_gateway import NotificationGateway
from app.infrastructure.persistence.models import Order


class NotificationService:
    """Builds human-readable notifications for lifecycle events.

    Templates are plain strings for now; the outbox row carries the payload a
    real mail renderer would use.
    """

    def __init__(self, gateway: NotificationGateway) -> None:
        self._gateway = gateway

    def order_created(self, order: Order) -> None:
        self._send_order_event(
            order,
            NotificationType.ORDER_CREATED,
            f"Order {order.order_number} received",
            f"We received your order {order.order_number} "
            f"for {order.grand_total:.2f} EUR and are waiting for payment.",
        )

    def payment_confirmed(self, order: Order) -> None:
        self._send_order_event(
            order,
            NotificationType.PAYMENT_CONFIRMED,
            f"Payment for {order.order_number} confirmed",
            f"Your payment of {order.grand_total:.2f} EUR for order "
            f"{order.order_number} was authorized. We are preparing your items.",
        )

    def payment_failed(self, order: Order, reason: str) -> None:
        self._send_order_event(
            order,
            NotificationType.PAYMENT_FAILED,
            f"Payment for {order.order_number} failed",
            f"The payment for order {order.order_number} was not completed: {reason} "
            "No money was taken and the reserved items were released.",
            extra={"reason": reason},
        )

    def order_cancelled(self, order: Order, refunded: bool) -> None:
        body = f"Your order {order.order_number} was cancelled."
        if refunded:
            body += f" A refund of {order.grand_total:.2f} EUR is on its way."
        self._send_order_event(
            order,
            NotificationType.ORDER_CANCELLED,
            f"Order {order.order_number} cancelled",
            body,
            extra={"refunded": refunded},
        )

    def order_shipped(self, order: Order, estimated_delivery: str) -> None:
        self._send_order_event(
            order,
            NotificationType.ORDER_SHIPPED,
            f"Order {order.order_number} shipped",
            f"Your order {order.order_number} was handed to the carrier. "
            f"Estimated delivery: {estimated_delivery}.",
            extra={"estimated_delivery": estimated_delivery},
        )

    def order_delivered(self, order: Order) -> None:
        self._send_order_event(
            order,
            NotificationType.ORDER_DELIVERED,
            f"Order {order.order_number} delivered",
            f"Your order {order.order_number} was delivered. Enjoy!",
        )

    def return_instructions(self, order: Order) -> None:
        self._send_order_event(
            order,
            NotificationType.RETURN_INSTRUCTIONS,
            f"Return for {order.order_number} approved",
            f"Your return for order {order.order_number} was approved. "
            "Please send the items back to our warehouse within 14 days.",
        )

    def refund_completed(self, order: Order) -> None:
        self._send_order_event(
            order,
            NotificationType.REFUND_COMPLETED,
            f"Refund for {order.order_number} completed",
            f"We refunded {order.grand_total:.2f} EUR for order {order.order_number}.",
        )

    def low_stock_alert(self, *, admin_user_id: int, sku: str, available: int) -> None:
        self._gateway.send(
            recipient_user_id=admin_user_id,
            notification_type=NotificationType.LOW_STOCK_ALERT,
            subject=f"Low stock: {sku}",
            body=f"Variant {sku} is low on stock ({available} available).",
            payload={"sku": sku, "available": available},
        )

    def _send_order_event(
        self,
        order: Order,
        notification_type: NotificationType,
        subject: str,
        body: str,
        extra: dict | None = None,
    ) -> None:
        payload = {"order_number": order.order_number, "status": order.status.value}
        if extra:
            payload.update(extra)
        self._gateway.send(
            recipient_user_id=order.customer_id,
            notification_type=notification_type,
            subject=subject,
            body=body,
            payload=payload,
        )
