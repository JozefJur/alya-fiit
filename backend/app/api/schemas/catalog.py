"""Catalog schemas."""

from __future__ import annotations

from app.api.schemas.common import ApiModel, MoneyStr, RateStr


class CategoryOut(ApiModel):
    id: int
    name: str
    slug: str
    description: str
    is_active: bool


class VariantOut(ApiModel):
    id: int
    sku: str
    name: str
    attributes: dict
    price: MoneyStr  # effective net unit price
    price_with_vat: MoneyStr
    is_active: bool
    available: int


class ProductOut(ApiModel):
    id: int
    name: str
    slug: str
    description: str
    brand: str
    category_id: int
    category_name: str
    base_price: MoneyStr
    vat_rate: RateStr
    is_active: bool
    variants: list[VariantOut]


class ProductPageOut(ApiModel):
    items: list[ProductOut]
    total: int
    page: int
    page_size: int


class BrandsOut(ApiModel):
    brands: list[str]
