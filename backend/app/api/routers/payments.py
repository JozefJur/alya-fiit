"""Simulated payment-gateway callback endpoint.

Represents the *external* provider calling back into the shop, so it is not
authenticated with user JWTs. It is deterministic and idempotent — replaying a
callback never duplicates effects (integration scenario 4).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.dependencies.container import Services, get_services
from app.api.schemas.orders import PaymentCallbackIn, PaymentCallbackOut
from app.application.commands.commands import PaymentCallbackCommand

router = APIRouter(prefix="/api/payments", tags=["payments"])


@router.post("/callback", response_model=PaymentCallbackOut)
def payment_callback(
    payload: PaymentCallbackIn, services: Services = Depends(get_services)
) -> PaymentCallbackOut:
    result = services.payment_processor.process(
        PaymentCallbackCommand(
            idempotency_key=payload.idempotency_key,
            status=payload.status,
            gateway_reference=payload.gateway_reference,
            message=payload.message,
        )
    )
    return PaymentCallbackOut(
        payment_id=result.payment.id,
        order_id=result.payment.order_id,
        status=result.payment.status,
        replayed=result.replayed,
    )
