"""Domain enumerations shared by all layers."""

from enum import StrEnum


class UserRole(StrEnum):
    CUSTOMER = "customer"
    WAREHOUSE_STAFF = "warehouse_staff"
    ADMINISTRATOR = "administrator"
    SUPPORT_AGENT = "support_agent"


class OrderStatus(StrEnum):
    DRAFT = "DRAFT"
    PENDING_PAYMENT = "PENDING_PAYMENT"
    PAID = "PAID"
    PICKING = "PICKING"
    READY_TO_SHIP = "READY_TO_SHIP"
    SHIPPED = "SHIPPED"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"
    PAYMENT_FAILED = "PAYMENT_FAILED"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    RETURN_REQUESTED = "RETURN_REQUESTED"
    RETURN_APPROVED = "RETURN_APPROVED"
    RETURNED = "RETURNED"
    REFUNDED = "REFUNDED"


class OrderEvent(StrEnum):
    SUBMIT_PAYMENT = "submit_payment"
    CANCEL = "cancel"
    PAYMENT_AUTHORIZED = "payment_authorized"
    PAYMENT_DECLINED = "payment_declined"
    PAYMENT_TIMEOUT = "payment_timeout"
    START_PICKING = "start_picking"
    REQUEST_CANCEL = "request_cancel"
    APPROVE_CANCEL = "approve_cancel"
    REJECT_CANCEL = "reject_cancel"
    MARK_READY = "mark_ready"
    SHIP = "ship"
    MARK_DELIVERED = "mark_delivered"
    REQUEST_RETURN = "request_return"
    APPROVE_RETURN = "approve_return"
    REJECT_RETURN = "reject_return"
    RECEIVE_RETURN = "receive_return"
    REFUND = "refund"


class ActorKind(StrEnum):
    """Who is executing a state transition (used by the state machine role rules)."""

    SYSTEM = "system"  # internal use cases (checkout, payment callback processing)
    CUSTOMER = "customer"
    WAREHOUSE_STAFF = "warehouse_staff"
    ADMINISTRATOR = "administrator"
    SUPPORT_AGENT = "support_agent"


class MovementType(StrEnum):
    RECEIPT = "receipt"
    ADJUSTMENT = "adjustment"
    RESERVATION = "reservation"
    RELEASE = "release"
    SHIPMENT = "shipment"
    RETURN = "return"
    IMPORT = "import"


class ReservationStatus(StrEnum):
    ACTIVE = "active"
    RELEASED = "released"
    CONSUMED = "consumed"


class CartStatus(StrEnum):
    ACTIVE = "active"
    CONVERTED = "converted"


class DiscountType(StrEnum):
    PERCENT = "percent"
    FIXED = "fixed"


class PaymentStatus(StrEnum):
    PENDING = "pending"
    AUTHORIZED = "authorized"
    DECLINED = "declined"
    TIMEOUT = "timeout"
    REFUNDED = "refunded"


class RefundStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"


class RequestType(StrEnum):
    CANCEL = "cancel"
    RETURN = "return"


class RequestStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class NotificationStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"


class NotificationType(StrEnum):
    ORDER_CREATED = "order_created"
    PAYMENT_CONFIRMED = "payment_confirmed"
    PAYMENT_FAILED = "payment_failed"
    ORDER_CANCELLED = "order_cancelled"
    ORDER_SHIPPED = "order_shipped"
    ORDER_DELIVERED = "order_delivered"
    RETURN_INSTRUCTIONS = "return_instructions"
    REFUND_COMPLETED = "refund_completed"
    LOW_STOCK_ALERT = "low_stock_alert"
