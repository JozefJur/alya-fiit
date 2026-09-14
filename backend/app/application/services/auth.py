"""Authentication: password hashing, credential checks, JWT issuing/decoding."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import bcrypt
import jwt

from app.config import Settings
from app.domain.errors import AuthenticationError
from app.infrastructure.adapters.clock import Clock, SystemClock
from app.infrastructure.persistence.models import User
from app.infrastructure.repositories.users import UserRepository


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=10)).decode("ascii")


def verify_password(plain: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), password_hash.encode("ascii"))
    except ValueError:
        return False


class InvalidCredentialsError(AuthenticationError):
    code = "invalid_credentials"


class InvalidTokenError(AuthenticationError):
    code = "invalid_token"


class AuthService:
    def __init__(
        self, users: UserRepository, settings: Settings, clock: Clock | None = None
    ) -> None:
        self._users = users
        self._settings = settings
        self._clock = clock or SystemClock()

    def authenticate(self, email: str, password: str) -> User:
        user = self._users.get_by_email(email)
        if user is None or not user.is_active or not verify_password(password, user.password_hash):
            # One error for all causes — never reveal whether the account exists.
            raise InvalidCredentialsError("Invalid e-mail or password.")
        return user

    def issue_token(self, user: User) -> str:
        now = self._clock.now()
        payload: dict[str, Any] = {
            "sub": str(user.id),
            "role": user.role.value,
            "iat": now,
            "exp": now + timedelta(minutes=self._settings.jwt_expires_minutes),
        }
        return jwt.encode(
            payload, self._settings.jwt_secret, algorithm=self._settings.jwt_algorithm
        )

    def decode_token(self, token: str) -> dict[str, Any]:
        try:
            return jwt.decode(
                token, self._settings.jwt_secret, algorithms=[self._settings.jwt_algorithm]
            )
        except jwt.ExpiredSignatureError as exc:
            raise InvalidTokenError("Session expired, please sign in again.") from exc
        except jwt.InvalidTokenError as exc:
            raise InvalidTokenError("Invalid authentication token.") from exc
