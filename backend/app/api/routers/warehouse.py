"""Warehouse endpoints: work queue, fulfillment steps, stock operations."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.dependencies.auth import require_warehouse
from app.api.dependencies.container import Services, get_services
from app.api.mappers import (
    movement_out,
    order_detail_out,
    order_summary_out,
    stock_level_out,
)
from app.api.schemas.orders import OrderDetailOut, OrderSummaryOut
from app.api.schemas.warehouse import (
    StockAdjustIn,
    StockLevelOut,
    StockMovementOut,
    ThresholdIn,
)
from app.application.commands.commands import StockAdjustmentCommand
from app.infrastructure.persistence.models import User

router = APIRouter(prefix="/api/warehouse", tags=["warehouse"])


@router.get("/orders", response_model=list[OrderSummaryOut])
def work_queue(
    _user: User = Depends(require_warehouse), services: Services = Depends(get_services)
) -> list[OrderSummaryOut]:
    return [order_summary_out(order, include_email=True) for order in services.picking.work_queue()]


@router.post("/orders/{order_id}/start-picking", response_model=OrderDetailOut)
def start_picking(
    order_id: int,
    user: User = Depends(require_warehouse),
    services: Services = Depends(get_services),
) -> OrderDetailOut:
    return order_detail_out(services.picking.start_picking(order_id, actor=user))


@router.post("/orders/{order_id}/mark-ready", response_model=OrderDetailOut)
def mark_ready(
    order_id: int,
    user: User = Depends(require_warehouse),
    services: Services = Depends(get_services),
) -> OrderDetailOut:
    return order_detail_out(services.picking.mark_ready(order_id, actor=user))


@router.post("/orders/{order_id}/ship", response_model=OrderDetailOut)
def ship(
    order_id: int,
    user: User = Depends(require_warehouse),
    services: Services = Depends(get_services),
) -> OrderDetailOut:
    order = services.shipment.ship(order_id, actor=user)
    return order_detail_out(order, expected_delivery=services.shipment.expected_delivery_for(order))


@router.post("/orders/{order_id}/mark-delivered", response_model=OrderDetailOut)
def mark_delivered(
    order_id: int,
    user: User = Depends(require_warehouse),
    services: Services = Depends(get_services),
) -> OrderDetailOut:
    return order_detail_out(services.shipment.mark_delivered(order_id, actor=user))


@router.post("/orders/{order_id}/receive-return", response_model=OrderDetailOut)
def receive_return(
    order_id: int,
    user: User = Depends(require_warehouse),
    services: Services = Depends(get_services),
) -> OrderDetailOut:
    return order_detail_out(services.shipment.receive_return(order_id, actor=user))


# ---------------------------------------------------------------------------
# Stock
# ---------------------------------------------------------------------------


@router.get("/inventory", response_model=list[StockLevelOut])
def inventory(
    _user: User = Depends(require_warehouse), services: Services = Depends(get_services)
) -> list[StockLevelOut]:
    return [
        stock_level_out(level, services.low_stock_policy)
        for level in services.stock_levels.list_all()
    ]


@router.post("/inventory/adjust", response_model=StockLevelOut)
def adjust_stock(
    payload: StockAdjustIn,
    user: User = Depends(require_warehouse),
    services: Services = Depends(get_services),
) -> StockLevelOut:
    level = services.inventory.adjust(
        StockAdjustmentCommand(
            variant_id=payload.variant_id,
            quantity_change=payload.quantity_change,
            reason=payload.reason,
            actor_user_id=user.id,
        )
    )
    return stock_level_out(level, services.low_stock_policy)


@router.post("/inventory/threshold", response_model=StockLevelOut)
def set_threshold(
    payload: ThresholdIn,
    user: User = Depends(require_warehouse),
    services: Services = Depends(get_services),
) -> StockLevelOut:
    level = services.inventory.set_low_stock_threshold(
        variant_id=payload.variant_id,
        threshold=payload.low_stock_threshold,
        actor_user_id=user.id,
    )
    return stock_level_out(level, services.low_stock_policy)


@router.get("/inventory/{variant_id}/movements", response_model=list[StockMovementOut])
def variant_movements(
    variant_id: int,
    _user: User = Depends(require_warehouse),
    services: Services = Depends(get_services),
) -> list[StockMovementOut]:
    return [movement_out(m) for m in services.stock_movements.list_for_variant(variant_id)]
