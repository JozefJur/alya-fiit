"""Inventory persistence: stock levels, movements, reservations."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.entities.enums import ReservationStatus
from app.domain.errors import NotFoundError
from app.infrastructure.persistence.models import (
    StockLevel,
    StockMovement,
    StockReservation,
)


class StockLevelRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_for_variant(self, variant_id: int) -> StockLevel:
        stmt = select(StockLevel).where(StockLevel.variant_id == variant_id)
        level = self.session.scalars(stmt).first()
        if level is None:
            raise NotFoundError(
                "Stock record not found for variant.", details={"variant_id": variant_id}
            )
        return level

    def get_many(self, variant_ids: list[int]) -> dict[int, StockLevel]:
        stmt = select(StockLevel).where(StockLevel.variant_id.in_(variant_ids))
        return {level.variant_id: level for level in self.session.scalars(stmt)}

    def list_all(self) -> list[StockLevel]:
        return list(self.session.scalars(select(StockLevel)))

    def add(self, level: StockLevel) -> StockLevel:
        self.session.add(level)
        self.session.flush()
        return level


class StockMovementRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, movement: StockMovement) -> StockMovement:
        self.session.add(movement)
        self.session.flush()
        return movement

    def list_for_variant(self, variant_id: int, limit: int = 100) -> list[StockMovement]:
        stmt = (
            select(StockMovement)
            .where(StockMovement.variant_id == variant_id)
            .order_by(StockMovement.created_at.desc(), StockMovement.id.desc())
            .limit(limit)
        )
        return list(self.session.scalars(stmt))

    def list_recent(self, limit: int = 200) -> list[StockMovement]:
        stmt = (
            select(StockMovement)
            .order_by(StockMovement.created_at.desc(), StockMovement.id.desc())
            .limit(limit)
        )
        return list(self.session.scalars(stmt))


class ReservationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, reservation: StockReservation) -> StockReservation:
        self.session.add(reservation)
        self.session.flush()
        return reservation

    def active_for_order(self, order_id: int) -> list[StockReservation]:
        stmt = select(StockReservation).where(
            StockReservation.order_id == order_id,
            StockReservation.status == ReservationStatus.ACTIVE,
        )
        return list(self.session.scalars(stmt))

    def list_for_order(self, order_id: int) -> list[StockReservation]:
        stmt = select(StockReservation).where(StockReservation.order_id == order_id)
        return list(self.session.scalars(stmt))
