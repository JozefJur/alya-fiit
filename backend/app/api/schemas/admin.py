"""Administrator schemas: catalog management, coupons, users, reports, audit."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import Field

from app.api.schemas.common import ApiModel, MoneyStr
from app.domain.entities.enums import DiscountType, NotificationType, UserRole


class ProductCreateIn(ApiModel):
    category_id: int
    name: str = Field(min_length=1, max_length=255)
    brand: str = Field(min_length=1, max_length=120)
    base_price: Decimal = Field(gt=0)
    vat_rate: Decimal | None = Field(default=None, ge=0, lt=1)
    description: str = ""


class ProductUpdateIn(ApiModel):
    name: str | None = None
    brand: str | None = None
    description: str | None = None
    base_price: Decimal | None = Field(default=None, gt=0)
    vat_rate: Decimal | None = Field(default=None, ge=0, lt=1)
    category_id: int | None = None
    is_active: bool | None = None


class VariantCreateIn(ApiModel):
    sku: str = Field(min_length=1, max_length=64)
    name: str = Field(default="", max_length=255)
    price_delta: Decimal = Decimal("0")
    attributes: dict = {}
    initial_on_hand: int = Field(default=0, ge=0)
    low_stock_threshold: int | None = Field(default=None, ge=0)


class VariantUpdateIn(ApiModel):
    name: str | None = None
    price_delta: Decimal | None = None
    is_active: bool | None = None


class CouponCreateIn(ApiModel):
    code: str = Field(min_length=1, max_length=40)
    discount_type: DiscountType
    value: Decimal = Field(gt=0)
    valid_from: datetime
    valid_until: datetime
    min_cart_total: Decimal | None = Field(default=None, gt=0)
    max_uses: int | None = Field(default=None, ge=1)
    category_id: int | None = None


class CouponOut(ApiModel):
    id: int
    code: str
    discount_type: DiscountType
    value: MoneyStr
    valid_from: datetime
    valid_until: datetime
    min_cart_total: MoneyStr | None
    max_uses: int | None
    used_count: int
    category_id: int | None
    is_active: bool


class CouponActiveIn(ApiModel):
    is_active: bool


class AdminUserOut(ApiModel):
    id: int
    email: str
    full_name: str
    role: UserRole
    is_active: bool
    created_at: datetime


class AdminUserUpdateIn(ApiModel):
    role: UserRole | None = None
    is_active: bool | None = None


class AuditEntryOut(ApiModel):
    id: int
    actor_user_id: int | None
    action: str
    entity_type: str
    entity_id: str
    details: dict
    created_at: datetime


class NotificationOut(ApiModel):
    id: int
    recipient_user_id: int
    notification_type: NotificationType
    subject: str
    body: str
    status: str
    created_at: datetime


class ProductImportReportOut(ApiModel):
    created: int
