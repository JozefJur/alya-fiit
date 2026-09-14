"""User and address persistence."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.errors import NotFoundError
from app.infrastructure.persistence.models import Address, User


class UserRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, user_id: int) -> User:
        user = self.session.get(User, user_id)
        if user is None:
            raise NotFoundError("User not found.", details={"user_id": user_id})
        return user

    def get_by_email(self, email: str) -> User | None:
        stmt = select(User).where(User.email == email.strip().lower())
        return self.session.scalars(stmt).first()

    def list_all(self) -> list[User]:
        return list(self.session.scalars(select(User).order_by(User.id)))

    def add(self, user: User) -> User:
        self.session.add(user)
        self.session.flush()
        return user


class AddressRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_owned(self, address_id: int, user_id: int) -> Address:
        address = self.session.get(Address, address_id)
        if address is None or address.user_id != user_id:
            raise NotFoundError("Address not found.", details={"address_id": address_id})
        return address

    def list_for_user(self, user_id: int) -> list[Address]:
        stmt = select(Address).where(Address.user_id == user_id).order_by(Address.id)
        return list(self.session.scalars(stmt))

    def add(self, address: Address) -> Address:
        self.session.add(address)
        self.session.flush()
        return address
