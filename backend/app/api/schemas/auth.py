"""Auth and user schemas."""

from __future__ import annotations

from pydantic import Field

from app.api.schemas.common import ApiModel
from app.domain.entities.enums import UserRole


class LoginIn(ApiModel):
    # Plain str: internal accounts use domains that strict e-mail validators
    # reject, and the credentials are verified server-side anyway.
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=128)


class UserOut(ApiModel):
    id: int
    email: str
    full_name: str
    role: UserRole


class TokenOut(ApiModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class AddressIn(ApiModel):
    label: str = "Home"
    street: str
    city: str
    zip_code: str
    country: str = "SK"
    is_default: bool = False


class AddressOut(ApiModel):
    id: int
    label: str
    street: str
    city: str
    zip_code: str
    country: str
    is_default: bool
