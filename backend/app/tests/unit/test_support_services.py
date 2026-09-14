"""Delivery estimates, CSV export and the audit log service."""

from datetime import datetime

import pytest

from app.application.services.audit import AuditLogService
from app.application.services.csv_io import CsvExportService
from app.application.services.fulfillment import DeliveryEstimateService
from app.domain.errors import ValidationError


class _CollectingRepository:
    def __init__(self) -> None:
        self.added: list = []

    def add(self, entry):  # noqa: ANN001, ANN201
        self.added.append(entry)
        return entry


class TestDeliveryEstimateService:
    def test_adds_business_days_only(self):
        # 2026-06-15 is a Monday → +2 business days = Wednesday 17th
        service = DeliveryEstimateService(business_days=2)
        assert service.estimate_from(datetime(2026, 6, 15, 9, 0)).isoformat() == "2026-06-17"

    def test_skips_the_weekend(self):
        # Friday 2026-06-19 → +2 business days = Tuesday 23rd
        service = DeliveryEstimateService(business_days=2)
        assert service.estimate_from(datetime(2026, 6, 19, 9, 0)).isoformat() == "2026-06-23"

    def test_shipping_on_saturday_starts_counting_on_monday(self):
        service = DeliveryEstimateService(business_days=1)
        assert service.estimate_from(datetime(2026, 6, 20, 9, 0)).isoformat() == "2026-06-22"

    def test_zero_days_is_the_same_day(self):
        service = DeliveryEstimateService(business_days=0)
        assert service.estimate_from(datetime(2026, 6, 20, 9, 0)).isoformat() == "2026-06-20"

    def test_describe_returns_an_iso_date(self):
        assert DeliveryEstimateService(1).describe(datetime(2026, 6, 15)) == "2026-06-16"

    def test_negative_days_is_a_programming_error(self):
        with pytest.raises(ValueError):
            DeliveryEstimateService(business_days=-1)


class TestCsvExportService:
    def test_header_and_rows_are_written(self):
        csv_text = CsvExportService().export(["sku", "qty"], [["A-1", 2], ["B-2", 3]])
        assert csv_text == "sku,qty\nA-1,2\nB-2,3\n"

    def test_none_becomes_an_empty_cell(self):
        assert CsvExportService().export(["a", "b"], [[1, None]]) == "a,b\n1,\n"

    def test_values_with_separators_are_quoted(self):
        csv_text = CsvExportService().export(["name"], [["Cable, 2 m"]])
        assert '"Cable, 2 m"' in csv_text

    def test_no_rows_still_emits_the_header(self):
        assert CsvExportService().export(["a"], []) == "a\n"

    def test_row_width_mismatch_is_rejected(self):
        with pytest.raises(ValidationError) as error:
            CsvExportService().export(["a", "b"], [[1]])
        assert error.value.details["row"] == 1

    def test_empty_headers_are_rejected(self):
        with pytest.raises(ValidationError):
            CsvExportService().export([], [])

    def test_duplicate_headers_are_rejected(self):
        with pytest.raises(ValidationError):
            CsvExportService().export(["a", "a"], [])


class TestAuditLogService:
    def test_records_the_event(self):
        repository = _CollectingRepository()
        AuditLogService(repository).record(  # type: ignore[arg-type]
            actor_user_id=3,
            action="order.created",
            entity_type="order",
            entity_id=42,
            details={"total": "10.00"},
        )
        entry = repository.added[0]
        assert entry.action == "order.created"
        assert entry.entity_id == "42"
        assert entry.details_json == {"total": "10.00"}

    def test_system_actor_is_allowed(self):
        repository = _CollectingRepository()
        AuditLogService(repository).record(  # type: ignore[arg-type]
            actor_user_id=None, action="payment.result", entity_type="payment", entity_id=1
        )
        assert repository.added[0].actor_user_id is None

    def test_secrets_are_redacted(self):
        repository = _CollectingRepository()
        AuditLogService(repository).record(  # type: ignore[arg-type]
            actor_user_id=1,
            action="user.updated",
            entity_type="user",
            entity_id=1,
            details={"password": "hunter2", "email": "a@b.test"},
        )
        details = repository.added[0].details_json
        assert details["password"] == "***"
        assert details["email"] == "a@b.test"

    def test_action_must_be_namespaced(self):
        repository = _CollectingRepository()
        with pytest.raises(ValueError):
            AuditLogService(repository).record(  # type: ignore[arg-type]
                actor_user_id=1, action="created", entity_type="order", entity_id=1
            )

    def test_missing_details_default_to_an_empty_dict(self):
        repository = _CollectingRepository()
        AuditLogService(repository).record(  # type: ignore[arg-type]
            actor_user_id=1, action="order.created", entity_type="order", entity_id=1
        )
        assert repository.added[0].details_json == {}
