"""Customer order endpoints: checkout, listing, lifecycle actions."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.dependencies.auth import get_current_user, require_customer
from app.api.dependencies.container import Services, get_services
from app.api.mappers import order_detail_out, order_summary_out, request_out
from app.api.schemas.cart import CheckoutIn
from app.api.schemas.orders import (
    OrderActionIn,
    OrderDetailOut,
    OrderSummaryOut,
    RequestOut,
)
from app.application.commands.commands import CheckoutCommand, ShippingAddress
from app.domain.policies.authorization import AuthorizationPolicy
from app.infrastructure.persistence.models import User

router = APIRouter(prefix="/api/orders", tags=["orders"])


def _detail(services: Services, order, user: User) -> OrderDetailOut:
    actor = AuthorizationPolicy.actor_kind_for(user.role)
    allowed = [
        event.value for event in services.order_state_machine.allowed_events(order.status, actor)
    ]
    return order_detail_out(
        order,
        allowed_events=allowed,
        expected_delivery=services.shipment.expected_delivery_for(order),
    )


@router.post("/checkout", response_model=OrderDetailOut, status_code=201)
def checkout(
    payload: CheckoutIn,
    user: User = Depends(require_customer),
    services: Services = Depends(get_services),
) -> OrderDetailOut:
    order = services.checkout.checkout(
        CheckoutCommand(
            customer_id=user.id,
            payment_token=payload.payment_token,
            coupon_code=payload.coupon_code,
            address=ShippingAddress(
                name=payload.address.name,
                street=payload.address.street,
                city=payload.address.city,
                zip_code=payload.address.zip_code,
                country=payload.address.country,
            ),
        )
    )
    return _detail(services, order, user)


@router.get("", response_model=list[OrderSummaryOut])
def my_orders(
    user: User = Depends(require_customer), services: Services = Depends(get_services)
) -> list[OrderSummaryOut]:
    return [order_summary_out(order) for order in services.order_service.list_for_customer(user)]


@router.get("/{order_id}", response_model=OrderDetailOut)
def order_detail(
    order_id: int,
    user: User = Depends(get_current_user),
    services: Services = Depends(get_services),
) -> OrderDetailOut:
    order = services.order_service.get_for_user(order_id, user)
    return _detail(services, order, user)


@router.post("/{order_id}/cancel", response_model=OrderDetailOut)
def cancel_order(
    order_id: int,
    payload: OrderActionIn,
    user: User = Depends(require_customer),
    services: Services = Depends(get_services),
) -> OrderDetailOut:
    order = services.order_service.get_for_user(order_id, user)
    services.cancellation.cancel(order, actor=user, reason=payload.reason)
    return _detail(services, order, user)


@router.post("/{order_id}/request-cancel", response_model=RequestOut, status_code=201)
def request_cancel(
    order_id: int,
    payload: OrderActionIn,
    user: User = Depends(require_customer),
    services: Services = Depends(get_services),
) -> RequestOut:
    order = services.order_service.get_for_user(order_id, user)
    request = services.cancellation.request_cancellation(
        order, customer=user, reason=payload.reason
    )
    return request_out(request)


@router.post("/{order_id}/request-return", response_model=RequestOut, status_code=201)
def request_return(
    order_id: int,
    payload: OrderActionIn,
    user: User = Depends(require_customer),
    services: Services = Depends(get_services),
) -> RequestOut:
    request = services.order_service.request_return(order_id, customer=user, reason=payload.reason)
    return request_out(request)
