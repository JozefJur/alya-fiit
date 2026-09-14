"""Inventory CSV import — a stocktake with all-or-nothing semantics.

CSV columns: ``sku,on_hand[,low_stock_threshold]``. ``on_hand`` is the new
absolute quantity. If *any* row is invalid the whole import is rejected with a
per-row error report and nothing is applied (documented transactional
behavior; integration scenario 8).
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field

from app.application.services.audit import AuditLogService
from app.domain.entities.enums import MovementType
from app.domain.errors import CsvImportError, ValidationError
from app.infrastructure.persistence.models import StockMovement
from app.infrastructure.repositories.catalog import VariantRepository
from app.infrastructure.repositories.inventory import (
    StockLevelRepository,
    StockMovementRepository,
)

MAX_IMPORT_ROWS = 100_000
REQUIRED_COLUMNS = ("sku", "on_hand")
OPTIONAL_COLUMNS = ("low_stock_threshold",)


@dataclass(frozen=True)
class RowError:
    line: int
    field: str
    message: str


@dataclass(frozen=True)
class ValidRow:
    line: int
    variant_id: int
    sku: str
    new_on_hand: int
    threshold: int | None
    reserved: int
    previous_on_hand: int


@dataclass
class ImportResult:
    applied: int = 0
    unchanged: int = 0
    movements: int = 0
    row_errors: list[RowError] = field(default_factory=list)


class InventoryImportService:
    def __init__(
        self,
        variants: VariantRepository,
        stock_levels: StockLevelRepository,
        movements: StockMovementRepository,
        audit: AuditLogService,
    ) -> None:
        self._variants = variants
        self._stock_levels = stock_levels
        self._movements = movements
        self._audit = audit

    # ------------------------------------------------------------------
    # Parsing & validation
    # ------------------------------------------------------------------

    def parse(self, csv_text: str) -> list[dict[str, str]]:
        reader = csv.DictReader(io.StringIO(csv_text))
        if reader.fieldnames is None:
            raise ValidationError("The CSV file is empty.")
        normalized = [name.strip().lower() for name in reader.fieldnames]
        missing = [column for column in REQUIRED_COLUMNS if column not in normalized]
        if missing:
            raise ValidationError(
                f"Missing required CSV columns: {', '.join(missing)}.",
                details={"required": list(REQUIRED_COLUMNS)},
            )
        unknown = [
            column for column in normalized if column not in REQUIRED_COLUMNS + OPTIONAL_COLUMNS
        ]
        if unknown:
            raise ValidationError(
                f"Unknown CSV columns: {', '.join(unknown)}.",
                details={"allowed": list(REQUIRED_COLUMNS + OPTIONAL_COLUMNS)},
            )
        rows = [
            {(key or "").strip().lower(): (value or "").strip() for key, value in raw.items()}
            for raw in reader
        ]
        if len(rows) > MAX_IMPORT_ROWS:
            raise ValidationError(f"Import is limited to {MAX_IMPORT_ROWS} rows.")
        return rows

    def validate_rows(self, rows: list[dict[str, str]]) -> tuple[list[ValidRow], list[RowError]]:
        errors: list[RowError] = []
        valid: list[ValidRow] = []
        seen_skus: dict[str, int] = {}
        for index, row in enumerate(rows):
            line = index + 2  # header is line 1
            sku = row.get("sku", "")
            if not sku:
                errors.append(RowError(line, "sku", "SKU is required."))
                continue
            if sku in seen_skus:
                errors.append(
                    RowError(line, "sku", f"Duplicate SKU (already on line {seen_skus[sku]}).")
                )
                continue
            seen_skus[sku] = line

            variant = self._variants.get_by_sku(sku)
            if variant is None:
                errors.append(RowError(line, "sku", f"Unknown SKU '{sku}'."))
                continue

            raw_on_hand = row.get("on_hand", "")
            try:
                new_on_hand = int(raw_on_hand)
            except ValueError:
                errors.append(RowError(line, "on_hand", f"'{raw_on_hand}' is not a whole number."))
                continue
            if new_on_hand < 0:
                errors.append(RowError(line, "on_hand", "on_hand must be >= 0."))
                continue

            threshold: int | None = None
            raw_threshold = row.get("low_stock_threshold", "")
            if raw_threshold:
                try:
                    threshold = int(raw_threshold)
                except ValueError:
                    errors.append(
                        RowError(
                            line, "low_stock_threshold", f"'{raw_threshold}' is not a whole number."
                        )
                    )
                    continue
                if threshold < 0:
                    errors.append(RowError(line, "low_stock_threshold", "Threshold must be >= 0."))
                    continue

            level = self._stock_levels.get_for_variant(variant.id)
            if new_on_hand < level.reserved:
                errors.append(
                    RowError(
                        line,
                        "on_hand",
                        f"on_hand {new_on_hand} is below the reserved quantity "
                        f"({level.reserved}) and would break stock invariants.",
                    )
                )
                continue

            valid.append(
                ValidRow(
                    line=line,
                    variant_id=variant.id,
                    sku=sku,
                    new_on_hand=new_on_hand,
                    threshold=threshold,
                    reserved=level.reserved,
                    previous_on_hand=level.on_hand,
                )
            )
        return valid, errors

    # ------------------------------------------------------------------
    # Import
    # ------------------------------------------------------------------

    def import_csv(self, csv_text: str, *, actor_user_id: int) -> ImportResult:
        rows = self.parse(csv_text)
        valid, errors = self.validate_rows(rows)
        if errors:
            raise CsvImportError(
                "Import rejected: the file contains invalid rows. Nothing was applied.",
                details={
                    "row_errors": [
                        {"line": e.line, "field": e.field, "message": e.message} for e in errors
                    ],
                    "valid_rows": len(valid),
                },
            )

        result = ImportResult()
        for row in valid:
            level = self._stock_levels.get_for_variant(row.variant_id)
            delta = row.new_on_hand - level.on_hand
            if row.threshold is not None:
                level.low_stock_threshold = row.threshold
            if delta == 0:
                result.unchanged += 1
                continue
            level.on_hand = row.new_on_hand
            self._movements.add(
                StockMovement(
                    variant_id=row.variant_id,
                    movement_type=MovementType.IMPORT,
                    quantity=delta,
                    reason="CSV stock import",
                    actor_user_id=actor_user_id,
                )
            )
            result.applied += 1
            result.movements += 1

        self._audit.record(
            actor_user_id=actor_user_id,
            action="stock.imported",
            entity_type="inventory",
            entity_id="csv",
            details={"applied": result.applied, "unchanged": result.unchanged},
        )
        return result
