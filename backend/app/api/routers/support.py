"""Support-agent endpoints: order overview, request decisions, final refunds."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.dependencies.auth import require_support
from app.api.dependencies.container import Services, get_services
from app.api.mappers import order_detail_out, order_summary_out, request_out
from app.api.schemas.orders import (
    OrderActionIn,
    OrderDetailOut,
    OrderSummaryOut,
    RequestDecisionIn,
    RequestOut,
)
from app.domain.entities.enums import RequestType
from app.infrastructure.persistence.models import User

router = APIRouter(prefix="/api/support", tags=["support"])


@router.get("/orders", response_model=list[OrderSummaryOut])
def all_orders(
    _user: User = Depends(require_support), services: Services = Depends(get_services)
) -> list[OrderSummaryOut]:
    return [
        order_summary_out(order, include_email=True) for order in services.order_service.list_all()
    ]


@router.get("/orders/{order_id}", response_model=OrderDetailOut)
def order_detail(
    order_id: int,
    user: User = Depends(require_support),
    services: Services = Depends(get_services),
) -> OrderDetailOut:
    order = services.order_service.get_for_user(order_id, user)
    return order_detail_out(order)


@router.post("/orders/{order_id}/cancel", response_model=OrderDetailOut)
def cancel_order(
    order_id: int,
    payload: OrderActionIn,
    user: User = Depends(require_support),
    services: Services = Depends(get_services),
) -> OrderDetailOut:
    order = services.order_service.get_for_user(order_id, user)
    services.cancellation.cancel(order, actor=user, reason=payload.reason)
    return order_detail_out(order)


@router.post("/orders/{order_id}/refund", response_model=OrderDetailOut)
def refund_returned(
    order_id: int,
    user: User = Depends(require_support),
    services: Services = Depends(get_services),
) -> OrderDetailOut:
    order = services.order_service.refund_returned_order(order_id, actor=user)
    return order_detail_out(order)


@router.get("/requests", response_model=list[RequestOut])
def pending_requests(
    _user: User = Depends(require_support), services: Services = Depends(get_services)
) -> list[RequestOut]:
    return [request_out(r) for r in services.order_service.list_pending_requests()]


@router.post("/requests/{request_id}/approve", response_model=RequestOut)
def approve_request(
    request_id: int,
    payload: RequestDecisionIn,
    user: User = Depends(require_support),
    services: Services = Depends(get_services),
) -> RequestOut:
    return _decide(services, request_id, approve=True, decider=user, note=payload.note)


@router.post("/requests/{request_id}/reject", response_model=RequestOut)
def reject_request(
    request_id: int,
    payload: RequestDecisionIn,
    user: User = Depends(require_support),
    services: Services = Depends(get_services),
) -> RequestOut:
    return _decide(services, request_id, approve=False, decider=user, note=payload.note)


def _decide(
    services: Services, request_id: int, *, approve: bool, decider: User, note: str
) -> RequestOut:
    request = services.order_requests.get(request_id)
    if request.request_type == RequestType.CANCEL:
        decided = services.cancellation.decide_cancellation(
            request, approve=approve, decider=decider, note=note
        )
    else:
        decided = services.order_service.decide_return(
            request_id, approve=approve, decider=decider, note=note
        )
    return request_out(decided)
