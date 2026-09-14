"""Order schemas (customer, support, warehouse views)."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.api.schemas.common import ApiModel, MoneyStr, RateStr
from app.domain.entities.enums import (
    OrderStatus,
    PaymentStatus,
    RequestStatus,
    RequestType,
)


class OrderItemOut(ApiModel):
    variant_id: int
    product_name: str
    sku: str
    unit_price: MoneyStr
    vat_rate: RateStr
    quantity: int
    discount_amount: MoneyStr
    vat_amount: MoneyStr
    line_total: MoneyStr


class OrderHistoryOut(ApiModel):
    from_status: OrderStatus | None
    to_status: OrderStatus
    event: str
    actor_user_id: int | None
    note: str
    created_at: datetime


class PaymentOut(ApiModel):
    id: int
    amount: MoneyStr
    status: PaymentStatus
    idempotency_key: str
    gateway_reference: str | None
    created_at: datetime


class OrderSummaryOut(ApiModel):
    id: int
    order_number: str
    status: OrderStatus
    grand_total: MoneyStr
    created_at: datetime
    items_count: int
    customer_id: int
    customer_email: str | None = None


class OrderDetailOut(ApiModel):
    id: int
    order_number: str
    customer_id: int
    status: OrderStatus
    subtotal: MoneyStr
    discount_total: MoneyStr
    vat_total: MoneyStr
    grand_total: MoneyStr
    coupon_code: str | None
    ship_to_name: str
    ship_street: str
    ship_city: str
    ship_zip: str
    ship_country: str
    created_at: datetime
    shipped_at: datetime | None
    delivered_at: datetime | None
    expected_delivery: str | None = None
    items: list[OrderItemOut]
    status_history: list[OrderHistoryOut]
    payments: list[PaymentOut]
    allowed_events: list[str] = []


class OrderActionIn(ApiModel):
    reason: str = Field(default="", max_length=500)


class RequestOut(ApiModel):
    id: int
    order_id: int
    order_number: str
    request_type: RequestType
    reason: str
    status: RequestStatus
    requested_by: int
    created_at: datetime
    decided_at: datetime | None
    decision_note: str


class RequestDecisionIn(ApiModel):
    note: str = Field(default="", max_length=500)


class PaymentCallbackIn(ApiModel):
    idempotency_key: str = Field(min_length=1, max_length=64)
    status: str
    gateway_reference: str | None = None
    message: str = ""


class PaymentCallbackOut(ApiModel):
    payment_id: int
    order_id: int
    status: PaymentStatus
    replayed: bool
