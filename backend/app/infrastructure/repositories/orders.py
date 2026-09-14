"""Order persistence: orders, history, requests."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.domain.entities.enums import OrderStatus, RequestStatus, RequestType
from app.domain.errors import NotFoundError
from app.infrastructure.persistence.models import Order, OrderItem, OrderRequest


class OrderRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def _loaded(self, stmt):  # noqa: ANN001, ANN202 - internal helper
        return stmt.options(
            selectinload(Order.items),
            selectinload(Order.status_history),
            selectinload(Order.payments),
            selectinload(Order.requests),
        )

    def get(self, order_id: int) -> Order:
        order = self.session.scalars(
            self._loaded(select(Order).where(Order.id == order_id))
        ).first()
        if order is None:
            raise NotFoundError("Order not found.", details={"order_id": order_id})
        return order

    def get_by_number(self, order_number: str) -> Order | None:
        stmt = self._loaded(select(Order).where(Order.order_number == order_number))
        return self.session.scalars(stmt).first()

    def list_for_customer(self, customer_id: int) -> list[Order]:
        stmt = self._loaded(
            select(Order)
            .where(Order.customer_id == customer_id, Order.status != OrderStatus.DRAFT)
            .order_by(Order.created_at.desc(), Order.id.desc())
        )
        return list(self.session.scalars(stmt))

    def list_by_statuses(self, statuses: tuple[OrderStatus, ...]) -> list[Order]:
        stmt = self._loaded(
            select(Order).where(Order.status.in_(statuses)).order_by(Order.created_at)
        )
        return list(self.session.scalars(stmt))

    def list_all(self, limit: int = 500) -> list[Order]:
        stmt = self._loaded(
            select(Order)
            .where(Order.status != OrderStatus.DRAFT)
            .order_by(Order.created_at.desc(), Order.id.desc())
            .limit(limit)
        )
        return list(self.session.scalars(stmt))

    def list_in_period(self, start: datetime, end: datetime) -> list[Order]:
        stmt = select(Order).where(Order.created_at >= start, Order.created_at < end)
        return list(self.session.scalars(stmt))

    def items_for_order(self, order_id: int) -> list[OrderItem]:
        stmt = select(OrderItem).where(OrderItem.order_id == order_id)
        return list(self.session.scalars(stmt))

    def add(self, order: Order) -> Order:
        self.session.add(order)
        self.session.flush()
        return order

    def next_sequence_number(self) -> int:
        return (self.session.scalar(select(func.max(Order.id))) or 0) + 1


class OrderRequestRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, request_id: int) -> OrderRequest:
        request = self.session.scalars(
            select(OrderRequest)
            .where(OrderRequest.id == request_id)
            .options(selectinload(OrderRequest.order))
        ).first()
        if request is None:
            raise NotFoundError("Request not found.", details={"request_id": request_id})
        return request

    def pending_for_order(self, order_id: int, request_type: RequestType) -> OrderRequest | None:
        stmt = select(OrderRequest).where(
            OrderRequest.order_id == order_id,
            OrderRequest.request_type == request_type,
            OrderRequest.status == RequestStatus.PENDING,
        )
        return self.session.scalars(stmt).first()

    def list_pending(self) -> list[OrderRequest]:
        stmt = (
            select(OrderRequest)
            .where(OrderRequest.status == RequestStatus.PENDING)
            .options(selectinload(OrderRequest.order))
            .order_by(OrderRequest.created_at)
        )
        return list(self.session.scalars(stmt))

    def add(self, request: OrderRequest) -> OrderRequest:
        self.session.add(request)
        self.session.flush()
        return request
