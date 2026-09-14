"""Generic CSV export (imports live in their own use cases/validators)."""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Sequence

from app.domain.errors import ValidationError


class CsvExportService:
    """Builds CSV text from headers + rows with strict shape checking."""

    delimiter = ","

    def export(self, headers: Sequence[str], rows: Iterable[Sequence[object]]) -> str:
        if not headers:
            raise ValidationError("CSV export needs at least one column.")
        if len(set(headers)) != len(headers):
            raise ValidationError("CSV headers must be unique.")
        buffer = io.StringIO()
        writer = csv.writer(buffer, delimiter=self.delimiter, lineterminator="\n")
        writer.writerow(headers)
        for index, row in enumerate(rows, start=1):
            if len(row) != len(headers):
                raise ValidationError(
                    f"Row {index} has {len(row)} cells, expected {len(headers)}.",
                    details={"row": index},
                )
            writer.writerow(["" if cell is None else cell for cell in row])
        return buffer.getvalue()
