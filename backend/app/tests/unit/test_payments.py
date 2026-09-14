"""Payment idempotency policy and the simulated gateway."""

import pytest

from app.domain.entities.enums import PaymentStatus
from app.domain.policies.payments import (
    CallbackDecision,
    PaymentIdempotencyPolicy,
    RecordedCallback,
)
from app.domain.value_objects.money import Money
from app.infrastructure.adapters.payment_gateway import (
    TOKEN_DECLINED,
    TOKEN_SUCCESS,
    TOKEN_TIMEOUT,
    SimulatedPaymentGateway,
)


class TestPaymentIdempotencyPolicy:
    def test_first_callback_is_processed(self):
        policy = PaymentIdempotencyPolicy()
        assert policy.decide(None, PaymentStatus.AUTHORIZED) == CallbackDecision.PROCESS

    def test_pending_record_is_still_unprocessed(self):
        policy = PaymentIdempotencyPolicy()
        recorded = RecordedCallback("k1", PaymentStatus.PENDING)
        assert policy.decide(recorded, PaymentStatus.AUTHORIZED) == CallbackDecision.PROCESS

    def test_same_outcome_twice_is_a_replay(self):
        policy = PaymentIdempotencyPolicy()
        recorded = RecordedCallback("k1", PaymentStatus.AUTHORIZED)
        assert policy.decide(recorded, PaymentStatus.AUTHORIZED) == CallbackDecision.REPLAY

    def test_contradicting_outcome_is_a_conflict(self):
        policy = PaymentIdempotencyPolicy()
        recorded = RecordedCallback("k1", PaymentStatus.AUTHORIZED)
        assert policy.decide(recorded, PaymentStatus.DECLINED) == CallbackDecision.CONFLICT

    def test_declined_then_declined_is_a_replay(self):
        policy = PaymentIdempotencyPolicy()
        recorded = RecordedCallback("k1", PaymentStatus.DECLINED)
        assert policy.decide(recorded, PaymentStatus.DECLINED) == CallbackDecision.REPLAY

    def test_timeout_then_authorized_is_a_conflict(self):
        policy = PaymentIdempotencyPolicy()
        recorded = RecordedCallback("k1", PaymentStatus.TIMEOUT)
        assert policy.decide(recorded, PaymentStatus.AUTHORIZED) == CallbackDecision.CONFLICT

    def test_pending_cannot_arrive_in_a_callback(self):
        with pytest.raises(ValueError):
            PaymentIdempotencyPolicy().decide(None, PaymentStatus.PENDING)


class TestSimulatedPaymentGateway:
    def _authorize(self, token: str):
        return SimulatedPaymentGateway().authorize(
            order_number="AF-2026-000001",
            amount=Money.of("10.00"),
            payment_token=token,
            idempotency_key="AF-2026-000001-p1",
        )

    def test_success_token_authorizes(self):
        outcome = self._authorize(TOKEN_SUCCESS)
        assert outcome.status == PaymentStatus.AUTHORIZED
        assert "AF-2026-000001" in outcome.message

    def test_declined_token_declines(self):
        assert self._authorize(TOKEN_DECLINED).status == PaymentStatus.DECLINED

    def test_timeout_token_times_out(self):
        assert self._authorize(TOKEN_TIMEOUT).status == PaymentStatus.TIMEOUT

    def test_unknown_token_never_authorizes(self):
        outcome = self._authorize("tok-whatever")
        assert outcome.status == PaymentStatus.DECLINED

    def test_outcome_is_deterministic_for_the_same_input(self):
        first = self._authorize(TOKEN_SUCCESS)
        second = self._authorize(TOKEN_SUCCESS)
        assert first == second

    def test_reference_is_derived_from_the_idempotency_key(self):
        outcome = self._authorize(TOKEN_SUCCESS)
        assert outcome.gateway_reference.startswith("sim-")

    @pytest.mark.parametrize("amount", ["0.00", "-1.00"])
    def test_non_positive_amount_is_rejected(self, amount: str):
        with pytest.raises(ValueError):
            SimulatedPaymentGateway().authorize(
                order_number="AF-1",
                amount=Money.of(amount),
                payment_token=TOKEN_SUCCESS,
                idempotency_key="k",
            )

    def test_refund_succeeds_and_marks_the_reference(self):
        outcome = SimulatedPaymentGateway().refund(
            gateway_reference="sim-abc", amount=Money.of("5.00"), idempotency_key="k-refund"
        )
        assert outcome.succeeded
        assert outcome.gateway_reference == "sim-abc-refund"

    def test_refund_requires_a_positive_amount(self):
        with pytest.raises(ValueError):
            SimulatedPaymentGateway().refund(
                gateway_reference="sim-abc", amount=Money.zero(), idempotency_key="k"
            )
