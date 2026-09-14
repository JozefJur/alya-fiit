"""Payment and refund persistence."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.errors import NotFoundError
from app.infrastructure.persistence.models import Payment, Refund


class PaymentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, payment_id: int) -> Payment:
        payment = self.session.get(Payment, payment_id)
        if payment is None:
            raise NotFoundError("Payment not found.", details={"payment_id": payment_id})
        return payment

    def get_by_idempotency_key(self, key: str) -> Payment | None:
        stmt = select(Payment).where(Payment.idempotency_key == key)
        return self.session.scalars(stmt).first()

    def latest_for_order(self, order_id: int) -> Payment | None:
        stmt = select(Payment).where(Payment.order_id == order_id).order_by(Payment.id.desc())
        return self.session.scalars(stmt).first()

    def list_for_order(self, order_id: int) -> list[Payment]:
        stmt = select(Payment).where(Payment.order_id == order_id).order_by(Payment.id)
        return list(self.session.scalars(stmt))

    def add(self, payment: Payment) -> Payment:
        self.session.add(payment)
        self.session.flush()
        return payment


class RefundRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_for_payment(self, payment_id: int) -> list[Refund]:
        stmt = select(Refund).where(Refund.payment_id == payment_id).order_by(Refund.id)
        return list(self.session.scalars(stmt))

    def add(self, refund: Refund) -> Refund:
        self.session.add(refund)
        self.session.flush()
        return refund
