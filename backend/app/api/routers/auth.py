"""Authentication and profile endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.dependencies.auth import get_current_user, require_customer
from app.api.dependencies.container import Services, get_services
from app.api.schemas.auth import AddressIn, AddressOut, LoginIn, TokenOut, UserOut
from app.infrastructure.persistence.models import Address, User

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenOut)
def login(payload: LoginIn, services: Services = Depends(get_services)) -> TokenOut:
    user = services.auth.authenticate(payload.email, payload.password)
    token = services.auth.issue_token(user)
    return TokenOut(access_token=token, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(user)


@router.get("/addresses", response_model=list[AddressOut])
def list_addresses(
    user: User = Depends(require_customer),
    services: Services = Depends(get_services),
) -> list[AddressOut]:
    return [AddressOut.model_validate(a) for a in services.addresses.list_for_user(user.id)]


@router.post("/addresses", response_model=AddressOut, status_code=201)
def create_address(
    payload: AddressIn,
    user: User = Depends(require_customer),
    services: Services = Depends(get_services),
) -> AddressOut:
    address = services.addresses.add(
        Address(
            user_id=user.id,
            label=payload.label,
            street=payload.street,
            city=payload.city,
            zip_code=payload.zip_code,
            country=payload.country,
            is_default=payload.is_default,
        )
    )
    return AddressOut.model_validate(address)
