"""Fixed local accounts for development and test environments."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.application.services.auth import hash_password
from app.domain.entities.enums import UserRole
from app.infrastructure.persistence.models import Address, User

#: email, password, full name, role
SEED_ACCOUNTS: list[tuple[str, str, str, UserRole]] = [
    ("admin@alya.test", "Admin123!", "Alica Adminová", UserRole.ADMINISTRATOR),
    ("warehouse@alya.test", "Warehouse123!", "Viktor Skladník", UserRole.WAREHOUSE_STAFF),
    ("support@alya.test", "Support123!", "Simona Supportová", UserRole.SUPPORT_AGENT),
    ("customer1@alya.test", "Customer123!", "Cyril Zákazník", UserRole.CUSTOMER),
    ("customer2@alya.test", "Customer123!", "Zuzana Nakupná", UserRole.CUSTOMER),
]


def ensure_seed_accounts(session: Session) -> dict[str, User]:
    """Insert the fixed accounts if missing; returns them keyed by e-mail."""
    users: dict[str, User] = {}
    for email, password, full_name, role in SEED_ACCOUNTS:
        existing = session.query(User).filter(User.email == email).first()
        if existing is None:
            existing = User(
                email=email,
                password_hash=hash_password(password),
                full_name=full_name,
                role=role,
            )
            session.add(existing)
            session.flush()
            if role == UserRole.CUSTOMER:
                session.add(
                    Address(
                        user_id=existing.id,
                        label="Home",
                        street="Ilkovičova 2",
                        city="Bratislava",
                        zip_code="84216",
                        country="SK",
                        is_default=True,
                    )
                )
        users[email] = existing
    return users
