"""Idempotency rules for payment callbacks."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.domain.entities.enums import PaymentStatus


class CallbackDecision(StrEnum):
    PROCESS = "process"  # first time we see this idempotency key → apply effects
    REPLAY = "replay"  # same key, same outcome → return original result, no effects
    CONFLICT = "conflict"  # same key, contradictory outcome → reject loudly


@dataclass(frozen=True)
class RecordedCallback:
    idempotency_key: str
    resulting_status: PaymentStatus


class PaymentIdempotencyPolicy:
    """Decides how to treat an incoming payment callback.

    A payment that is still ``pending`` has not been processed — the callback
    is processed normally. Once a terminal gateway outcome is recorded, a
    repeat with the same outcome is a harmless replay; a repeat with a
    different outcome is a conflict that must never silently overwrite the
    original result.
    """

    def decide(
        self, recorded: RecordedCallback | None, incoming_status: PaymentStatus
    ) -> CallbackDecision:
        if incoming_status == PaymentStatus.PENDING:
            raise ValueError("A callback cannot carry the 'pending' status")
        if recorded is None or recorded.resulting_status == PaymentStatus.PENDING:
            return CallbackDecision.PROCESS
        if recorded.resulting_status == incoming_status:
            return CallbackDecision.REPLAY
        return CallbackDecision.CONFLICT
