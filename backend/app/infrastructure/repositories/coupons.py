"""Coupon persistence."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.errors import NotFoundError
from app.infrastructure.persistence.models import Coupon


class CouponRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, coupon_id: int) -> Coupon:
        coupon = self.session.get(Coupon, coupon_id)
        if coupon is None:
            raise NotFoundError("Coupon not found.", details={"coupon_id": coupon_id})
        return coupon

    def get_by_code(self, code: str) -> Coupon | None:
        """Codes are stored uppercase; lookup is case-insensitive."""
        normalized = code.strip().upper()
        return self.session.scalars(select(Coupon).where(Coupon.code == normalized)).first()

    def list_all(self) -> list[Coupon]:
        return list(self.session.scalars(select(Coupon).order_by(Coupon.id)))

    def add(self, coupon: Coupon) -> Coupon:
        self.session.add(coupon)
        self.session.flush()
        return coupon
