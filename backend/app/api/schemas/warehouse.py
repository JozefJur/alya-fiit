"""Warehouse and inventory schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.api.schemas.common import ApiModel
from app.domain.entities.enums import MovementType


class StockLevelOut(ApiModel):
    variant_id: int
    sku: str
    product_name: str
    variant_name: str
    on_hand: int
    reserved: int
    available: int
    low_stock_threshold: int
    is_low_stock: bool


class StockMovementOut(ApiModel):
    id: int
    variant_id: int
    movement_type: MovementType
    quantity: int
    reason: str
    reference: str | None
    actor_user_id: int | None
    created_at: datetime


class StockAdjustIn(ApiModel):
    variant_id: int
    quantity_change: int
    # The "reason is mandatory" rule belongs to the domain (InventoryService),
    # so a blank reason returns that rule's message instead of a generic
    # schema error.
    reason: str = Field(default="", max_length=255)


class ThresholdIn(ApiModel):
    variant_id: int
    low_stock_threshold: int | None = Field(default=None, ge=0)


class ImportRowErrorOut(ApiModel):
    line: int
    field: str
    message: str


class ImportResultOut(ApiModel):
    applied: int
    unchanged: int
    movements: int
