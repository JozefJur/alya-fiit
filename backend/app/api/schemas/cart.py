"""Cart and checkout schemas."""

from __future__ import annotations

from pydantic import Field

from app.api.schemas.common import ApiModel, MoneyStr


class CartItemIn(ApiModel):
    variant_id: int
    quantity: int = Field(ge=1)


class CartItemUpdateIn(ApiModel):
    quantity: int = Field(ge=0)  # 0 removes the item


class CouponIn(ApiModel):
    code: str = Field(min_length=1, max_length=40)


class CartLineOut(ApiModel):
    variant_id: int
    product_id: int
    product_name: str
    sku: str
    quantity: int
    unit_price: MoneyStr
    line_net: MoneyStr
    discount: MoneyStr
    vat: MoneyStr
    line_total: MoneyStr


class CartProblemOut(ApiModel):
    variant_id: int
    code: str
    message: str


class CartOut(ApiModel):
    id: int
    items: list[CartLineOut]
    subtotal: MoneyStr
    discount_total: MoneyStr
    vat_total: MoneyStr
    grand_total: MoneyStr
    coupon_code: str | None
    coupon_error: str | None
    problems: list[CartProblemOut]


class CheckoutAddressIn(ApiModel):
    name: str = Field(min_length=1, max_length=255)
    street: str = Field(min_length=1, max_length=255)
    city: str = Field(min_length=1, max_length=120)
    zip_code: str = Field(min_length=1, max_length=20)
    country: str = Field(default="SK", min_length=2, max_length=2)


class CheckoutIn(ApiModel):
    payment_token: str = Field(min_length=1, max_length=64)
    address: CheckoutAddressIn
    coupon_code: str | None = None
