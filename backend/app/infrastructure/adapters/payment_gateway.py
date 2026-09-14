"""Payment gateway port and its deterministic local implementation.

The simulated gateway never talks to the network and never uses randomness:
the *payment token* chosen at checkout fully determines the outcome, so every
scenario is reproducible in tests and demos.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.domain.entities.enums import PaymentStatus
from app.domain.value_objects.money import Money

#: Tokens accepted by the simulated gateway.
TOKEN_SUCCESS = "tok-success"  # nosec B105 # public simulation selector, not a secret
TOKEN_DECLINED = "tok-declined"  # nosec B105 # public simulation selector, not a secret
TOKEN_TIMEOUT = "tok-timeout"  # nosec B105 # public simulation selector, not a secret

KNOWN_TOKENS = (TOKEN_SUCCESS, TOKEN_DECLINED, TOKEN_TIMEOUT)


@dataclass(frozen=True)
class PaymentOutcome:
    status: PaymentStatus  # authorized | declined | timeout
    gateway_reference: str
    message: str


@dataclass(frozen=True)
class RefundOutcome:
    succeeded: bool
    gateway_reference: str
    message: str


class PaymentGateway(Protocol):
    def authorize(
        self, *, order_number: str, amount: Money, payment_token: str, idempotency_key: str
    ) -> PaymentOutcome: ...

    def refund(
        self, *, gateway_reference: str, amount: Money, idempotency_key: str
    ) -> RefundOutcome: ...


class SimulatedPaymentGateway:
    """Deterministic stand-in for a real payment provider."""

    def authorize(
        self, *, order_number: str, amount: Money, payment_token: str, idempotency_key: str
    ) -> PaymentOutcome:
        if amount.is_negative or amount.is_zero:
            raise ValueError("authorization amount must be positive")
        reference = f"sim-{idempotency_key[:12]}"
        if payment_token == TOKEN_SUCCESS:
            return PaymentOutcome(
                status=PaymentStatus.AUTHORIZED,
                gateway_reference=reference,
                message=f"Payment for order {order_number} authorized.",
            )
        if payment_token == TOKEN_DECLINED:
            return PaymentOutcome(
                status=PaymentStatus.DECLINED,
                gateway_reference=reference,
                message="The card was declined by the issuing bank.",
            )
        if payment_token == TOKEN_TIMEOUT:
            return PaymentOutcome(
                status=PaymentStatus.TIMEOUT,
                gateway_reference=reference,
                message="The payment provider did not respond in time.",
            )
        # Unknown tokens behave like a decline — never a silent success.
        return PaymentOutcome(
            status=PaymentStatus.DECLINED,
            gateway_reference=reference,
            message="Unknown payment method token.",
        )

    def refund(
        self, *, gateway_reference: str, amount: Money, idempotency_key: str
    ) -> RefundOutcome:
        if amount.is_negative or amount.is_zero:
            raise ValueError("refund amount must be positive")
        return RefundOutcome(
            succeeded=True,
            gateway_reference=f"{gateway_reference}-refund",
            message="Refund accepted by the simulated provider.",
        )
