"""SQLAlchemy ORM models.

Data carriers only — business rules live in the domain and application layers.
Money is stored as integer cents, rates as basis points (see ``types.py``);
all timestamps are naive UTC.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.domain.entities.enums import (
    CartStatus,
    DiscountType,
    MovementType,
    NotificationStatus,
    NotificationType,
    OrderStatus,
    PaymentStatus,
    RefundStatus,
    RequestStatus,
    RequestType,
    ReservationStatus,
    UserRole,
)
from app.infrastructure.persistence.types import money_column_type, rate_column_type


def utcnow() -> datetime:
    """Naive UTC timestamp (project-wide convention)."""
    return datetime.now(UTC).replace(tzinfo=None)


def str_enum(enum_cls: type) -> Enum:
    return Enum(enum_cls, native_enum=False, validate_strings=True, length=32)


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Users & access
# ---------------------------------------------------------------------------


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(128))
    full_name: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(str_enum(UserRole), default=UserRole.CUSTOMER)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    addresses: Mapped[list[Address]] = relationship(back_populates="user")


class Address(Base):
    __tablename__ = "addresses"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    label: Mapped[str] = mapped_column(String(50), default="Home")
    street: Mapped[str] = mapped_column(String(255))
    city: Mapped[str] = mapped_column(String(120))
    zip_code: Mapped[str] = mapped_column(String(20))
    country: Mapped[str] = mapped_column(String(2), default="SK")
    is_default: Mapped[bool] = mapped_column(default=False)

    user: Mapped[User] = relationship(back_populates="addresses")


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str] = mapped_column(String(140), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(default=True)

    products: Mapped[list[Product]] = relationship(back_populates="category")


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        Index("ix_products_search", "name", "brand"),
        Index("ix_products_listing", "category_id", "is_active"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    name: Mapped[str] = mapped_column(String(255))
    slug: Mapped[str] = mapped_column(String(280), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    brand: Mapped[str] = mapped_column(String(120), index=True)
    base_price: Mapped[Decimal] = mapped_column(money_column_type())
    vat_rate: Mapped[Decimal] = mapped_column(rate_column_type())
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    category: Mapped[Category] = relationship(back_populates="products")
    variants: Mapped[list[ProductVariant]] = relationship(back_populates="product")


class ProductVariant(Base):
    __tablename__ = "product_variants"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    sku: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    attributes_json: Mapped[dict] = mapped_column(JSON, default=dict)
    price_delta: Mapped[Decimal] = mapped_column(money_column_type(), default=Decimal("0"))
    is_active: Mapped[bool] = mapped_column(default=True)

    product: Mapped[Product] = relationship(back_populates="variants")
    stock_level: Mapped[StockLevel | None] = relationship(back_populates="variant")


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------


class StockLevel(Base):
    __tablename__ = "stock_levels"

    id: Mapped[int] = mapped_column(primary_key=True)
    variant_id: Mapped[int] = mapped_column(ForeignKey("product_variants.id"), unique=True)
    on_hand: Mapped[int] = mapped_column(default=0)
    reserved: Mapped[int] = mapped_column(default=0)
    low_stock_threshold: Mapped[int | None] = mapped_column(default=None)

    variant: Mapped[ProductVariant] = relationship(back_populates="stock_level")

    @property
    def available(self) -> int:
        return self.on_hand - self.reserved


class StockMovement(Base):
    __tablename__ = "stock_movements"
    __table_args__ = (Index("ix_movements_variant_time", "variant_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    variant_id: Mapped[int] = mapped_column(ForeignKey("product_variants.id"))
    movement_type: Mapped[MovementType] = mapped_column(str_enum(MovementType))
    quantity: Mapped[int] = mapped_column()  # signed: +receipt/return, -shipment, ...
    reason: Mapped[str] = mapped_column(String(255))
    reference: Mapped[str | None] = mapped_column(String(64), default=None)  # e.g. order no.
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class StockReservation(Base):
    __tablename__ = "stock_reservations"
    __table_args__ = (Index("ix_reservations_order", "order_id", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))
    variant_id: Mapped[int] = mapped_column(ForeignKey("product_variants.id"))
    quantity: Mapped[int] = mapped_column()
    status: Mapped[ReservationStatus] = mapped_column(
        str_enum(ReservationStatus), default=ReservationStatus.ACTIVE
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    released_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)


# ---------------------------------------------------------------------------
# Cart & coupons
# ---------------------------------------------------------------------------


class Cart(Base):
    __tablename__ = "carts"
    __table_args__ = (
        Index(
            "uq_one_active_cart_per_customer",
            "customer_id",
            unique=True,
            sqlite_where=text("status = 'active'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[CartStatus] = mapped_column(str_enum(CartStatus), default=CartStatus.ACTIVE)
    coupon_code: Mapped[str | None] = mapped_column(String(40), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    items: Mapped[list[CartItem]] = relationship(
        back_populates="cart", cascade="all, delete-orphan"
    )


class CartItem(Base):
    __tablename__ = "cart_items"
    __table_args__ = (UniqueConstraint("cart_id", "variant_id", name="uq_cart_variant"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    cart_id: Mapped[int] = mapped_column(ForeignKey("carts.id"))
    variant_id: Mapped[int] = mapped_column(ForeignKey("product_variants.id"))
    quantity: Mapped[int] = mapped_column()

    cart: Mapped[Cart] = relationship(back_populates="items")
    variant: Mapped[ProductVariant] = relationship()


class Coupon(Base):
    __tablename__ = "coupons"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True)  # stored uppercase
    discount_type: Mapped[DiscountType] = mapped_column(str_enum(DiscountType))
    value: Mapped[Decimal] = mapped_column(money_column_type())  # % value or EUR amount
    valid_from: Mapped[datetime] = mapped_column(DateTime)
    valid_until: Mapped[datetime] = mapped_column(DateTime)
    min_cart_total: Mapped[Decimal | None] = mapped_column(money_column_type(), default=None)
    max_uses: Mapped[int | None] = mapped_column(default=None)
    used_count: Mapped[int] = mapped_column(default=0)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"), default=None)
    is_active: Mapped[bool] = mapped_column(default=True)


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        Index("ix_orders_customer", "customer_id", "created_at"),
        Index("ix_orders_status", "status"),
        Index("ix_orders_created", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    order_number: Mapped[str] = mapped_column(String(30), unique=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    status: Mapped[OrderStatus] = mapped_column(str_enum(OrderStatus), default=OrderStatus.DRAFT)

    subtotal: Mapped[Decimal] = mapped_column(money_column_type(), default=Decimal("0"))
    discount_total: Mapped[Decimal] = mapped_column(money_column_type(), default=Decimal("0"))
    vat_total: Mapped[Decimal] = mapped_column(money_column_type(), default=Decimal("0"))
    grand_total: Mapped[Decimal] = mapped_column(money_column_type(), default=Decimal("0"))
    coupon_code: Mapped[str | None] = mapped_column(String(40), default=None)

    ship_to_name: Mapped[str] = mapped_column(String(255), default="")
    ship_street: Mapped[str] = mapped_column(String(255), default="")
    ship_city: Mapped[str] = mapped_column(String(120), default="")
    ship_zip: Mapped[str] = mapped_column(String(20), default="")
    ship_country: Mapped[str] = mapped_column(String(2), default="SK")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    shipped_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)

    customer: Mapped[User] = relationship()
    items: Mapped[list[OrderItem]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )
    status_history: Mapped[list[OrderStatusHistory]] = relationship(
        back_populates="order", cascade="all, delete-orphan", order_by="OrderStatusHistory.id"
    )
    requests: Mapped[list[OrderRequest]] = relationship(back_populates="order")
    payments: Mapped[list[Payment]] = relationship(back_populates="order")
    reservations: Mapped[list[StockReservation]] = relationship()


class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = (Index("ix_order_items_order", "order_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))
    variant_id: Mapped[int] = mapped_column(ForeignKey("product_variants.id"))
    # Snapshot at checkout time — catalog changes never rewrite history.
    product_name: Mapped[str] = mapped_column(String(255))
    sku: Mapped[str] = mapped_column(String(64))
    unit_price: Mapped[Decimal] = mapped_column(money_column_type())  # net
    vat_rate: Mapped[Decimal] = mapped_column(rate_column_type())
    quantity: Mapped[int] = mapped_column()
    discount_amount: Mapped[Decimal] = mapped_column(money_column_type(), default=Decimal("0"))
    vat_amount: Mapped[Decimal] = mapped_column(money_column_type(), default=Decimal("0"))
    line_total: Mapped[Decimal] = mapped_column(money_column_type(), default=Decimal("0"))

    order: Mapped[Order] = relationship(back_populates="items")
    variant: Mapped[ProductVariant] = relationship()


class OrderStatusHistory(Base):
    __tablename__ = "order_status_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    from_status: Mapped[OrderStatus | None] = mapped_column(str_enum(OrderStatus), default=None)
    to_status: Mapped[OrderStatus] = mapped_column(str_enum(OrderStatus))
    event: Mapped[str] = mapped_column(String(40))
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None)
    note: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    order: Mapped[Order] = relationship(back_populates="status_history")


class OrderRequest(Base):
    __tablename__ = "order_requests"
    __table_args__ = (Index("ix_requests_status", "status", "request_type"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    request_type: Mapped[RequestType] = mapped_column(str_enum(RequestType))
    reason: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[RequestStatus] = mapped_column(
        str_enum(RequestStatus), default=RequestStatus.PENDING
    )
    requested_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None)
    decision_note: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)

    order: Mapped[Order] = relationship(back_populates="requests")


# ---------------------------------------------------------------------------
# Payments
# ---------------------------------------------------------------------------


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    amount: Mapped[Decimal] = mapped_column(money_column_type())
    status: Mapped[PaymentStatus] = mapped_column(
        str_enum(PaymentStatus), default=PaymentStatus.PENDING
    )
    payment_token: Mapped[str] = mapped_column(String(64))
    idempotency_key: Mapped[str] = mapped_column(String(64), unique=True)
    gateway_reference: Mapped[str | None] = mapped_column(String(64), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    order: Mapped[Order] = relationship(back_populates="payments")
    refunds: Mapped[list[Refund]] = relationship(back_populates="payment")


class Refund(Base):
    __tablename__ = "refunds"

    id: Mapped[int] = mapped_column(primary_key=True)
    payment_id: Mapped[int] = mapped_column(ForeignKey("payments.id"), index=True)
    amount: Mapped[Decimal] = mapped_column(money_column_type())
    reason: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[RefundStatus] = mapped_column(
        str_enum(RefundStatus), default=RefundStatus.PENDING
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)

    payment: Mapped[Payment] = relationship(back_populates="refunds")


# ---------------------------------------------------------------------------
# Platform: notifications outbox & audit log
# ---------------------------------------------------------------------------


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_recipient", "recipient_user_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    recipient_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    notification_type: Mapped[NotificationType] = mapped_column(str_enum(NotificationType))
    subject: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[NotificationStatus] = mapped_column(
        str_enum(NotificationStatus), default=NotificationStatus.PENDING
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AuditLogEntry(Base):
    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_created", "created_at"),
        Index("ix_audit_entity", "entity_type", "entity_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), default=None)
    action: Mapped[str] = mapped_column(String(80))
    entity_type: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[str] = mapped_column(String(40))
    details_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
