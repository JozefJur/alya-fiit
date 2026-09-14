"""Customer cart endpoints (always return the fresh priced cart)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.dependencies.auth import require_customer
from app.api.dependencies.container import Services, get_services
from app.api.mappers import cart_out
from app.api.schemas.cart import CartItemIn, CartItemUpdateIn, CartOut, CouponIn
from app.infrastructure.persistence.models import User

router = APIRouter(prefix="/api/cart", tags=["cart"])


def _priced(services: Services, user: User) -> CartOut:
    return cart_out(services.cart_service.priced_cart(user.id))


@router.get("", response_model=CartOut)
def get_cart(
    user: User = Depends(require_customer), services: Services = Depends(get_services)
) -> CartOut:
    return _priced(services, user)


@router.post("/items", response_model=CartOut, status_code=201)
def add_item(
    payload: CartItemIn,
    user: User = Depends(require_customer),
    services: Services = Depends(get_services),
) -> CartOut:
    services.cart_service.add_item(user.id, payload.variant_id, payload.quantity)
    return _priced(services, user)


@router.patch("/items/{variant_id}", response_model=CartOut)
def update_item(
    variant_id: int,
    payload: CartItemUpdateIn,
    user: User = Depends(require_customer),
    services: Services = Depends(get_services),
) -> CartOut:
    services.cart_service.update_item(user.id, variant_id, payload.quantity)
    return _priced(services, user)


@router.delete("/items/{variant_id}", response_model=CartOut)
def remove_item(
    variant_id: int,
    user: User = Depends(require_customer),
    services: Services = Depends(get_services),
) -> CartOut:
    services.cart_service.remove_item(user.id, variant_id)
    return _priced(services, user)


@router.delete("", response_model=CartOut)
def clear_cart(
    user: User = Depends(require_customer), services: Services = Depends(get_services)
) -> CartOut:
    services.cart_service.clear(user.id)
    return _priced(services, user)


@router.post("/coupon", response_model=CartOut)
def apply_coupon(
    payload: CouponIn,
    user: User = Depends(require_customer),
    services: Services = Depends(get_services),
) -> CartOut:
    services.cart_service.apply_coupon(user.id, payload.code)
    return _priced(services, user)


@router.delete("/coupon", response_model=CartOut)
def remove_coupon(
    user: User = Depends(require_customer), services: Services = Depends(get_services)
) -> CartOut:
    services.cart_service.remove_coupon(user.id)
    return _priced(services, user)
