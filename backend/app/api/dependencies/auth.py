"""Authentication and role-guard dependencies."""

from __future__ import annotations

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.api.dependencies.container import Services, get_services
from app.application.services.auth import InvalidTokenError
from app.domain.entities.enums import UserRole
from app.domain.errors import PermissionDeniedError
from app.infrastructure.persistence.models import User

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    services: Services = Depends(get_services),
) -> User:
    if credentials is None:
        raise InvalidTokenError("Authentication required.")
    payload = services.auth.decode_token(credentials.credentials)
    user = services.users.get(int(payload["sub"]))
    if not user.is_active:
        raise InvalidTokenError("This account is deactivated.")
    return user


def require_roles(*roles: UserRole):
    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise PermissionDeniedError(
                "You do not have permission for this operation.",
                details={"required_roles": [role.value for role in roles]},
            )
        return user

    return dependency


require_customer = require_roles(UserRole.CUSTOMER)
require_warehouse = require_roles(UserRole.WAREHOUSE_STAFF, UserRole.ADMINISTRATOR)
require_support = require_roles(UserRole.SUPPORT_AGENT, UserRole.ADMINISTRATOR)
require_admin = require_roles(UserRole.ADMINISTRATOR)
