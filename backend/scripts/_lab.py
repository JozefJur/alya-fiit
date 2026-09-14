"""Shared plumbing for the profiling and benchmark scripts.

Both scripts measure the same workload — the admin inventory & sales report —
against the performance database, so the setup lives in one place.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

DATA_DIR = BACKEND_DIR / "data"
PERF_DB = DATA_DIR / "perf.db"
OUTPUT_DIR = BACKEND_DIR / "benchmark-output"
PROFILE_DIR = BACKEND_DIR / "profiling-output"

#: Default reporting window: the last full month of the dataset — the period
#: an administrator would normally ask for.
DEFAULT_DATE_FROM = "2026-08-01"
DEFAULT_DATE_TO = "2026-08-31"


def configure_perf_database() -> Path:
    """Point the application at the performance database (before imports)."""
    if not PERF_DB.exists():
        raise SystemExit(
            f"performance database not found: {PERF_DB}\n"
            "Create it first:  python scripts/task.py seed-performance"
        )
    os.environ["ALYA_DATABASE_URL"] = f"sqlite:///{PERF_DB}"
    return PERF_DB


class QueryCounter:
    """Counts SQL statements executed on an engine (context manager)."""

    def __init__(self, engine: Any) -> None:
        self._engine = engine
        self.count = 0
        self.statements: list[str] = []

    def _before_cursor_execute(self, _conn, _cursor, statement, _params, _context, _many):  # noqa: ANN001
        self.count += 1
        if len(self.statements) < 20:
            self.statements.append(statement.split("\n")[0][:120])

    def __enter__(self) -> QueryCounter:
        from sqlalchemy import event

        event.listen(self._engine, "before_cursor_execute", self._before_cursor_execute)
        return self

    def __exit__(self, *_exc: object) -> None:
        from sqlalchemy import event

        event.remove(self._engine, "before_cursor_execute", self._before_cursor_execute)


def build_report_workload(
    date_from: str = DEFAULT_DATE_FROM,
    date_to: str = DEFAULT_DATE_TO,
    category_id: int | None = None,
) -> tuple[Callable[[], dict], Any]:
    """Return ``(run_report, engine)`` for the performance database.

    ``run_report()`` executes exactly what ``GET /api/admin/reports/
    inventory-sales`` does, minus HTTP — a fresh session per call, so each
    measurement starts from a cold identity map.
    """
    from app.api.dependencies.container import Services
    from app.application.commands.commands import ReportQuery
    from app.application.use_cases.inventory_sales_report import InventorySalesReport
    from app.config import Settings
    from app.infrastructure.persistence.database import get_engine, get_session_factory

    engine = get_engine()
    factory = get_session_factory()
    settings = Settings()

    def run_report() -> dict:
        session = factory()
        try:
            services = Services(session, settings)
            use_case = InventorySalesReport(services.sales_report, services.inventory_report)
            return use_case.build(
                ReportQuery(
                    date_from=date_from,
                    date_to=date_to,
                    category_id=category_id,
                    top_limit=10,
                )
            )
        finally:
            session.close()

    return run_report, engine


def add_window_arguments(parser: Any) -> None:
    """Shared --from/--to/--category options for the lab scripts."""
    parser.add_argument("--from", dest="date_from", default=DEFAULT_DATE_FROM, help="ISO date")
    parser.add_argument("--to", dest="date_to", default=DEFAULT_DATE_TO, help="ISO date")
    parser.add_argument("--category", type=int, default=None, help="restrict to one category id")


def summarize(values: list[float]) -> dict[str, float]:
    """Median / min / max / spread — never report a single run."""
    ordered = sorted(values)
    count = len(ordered)
    middle = count // 2
    median = ordered[middle] if count % 2 else (ordered[middle - 1] + ordered[middle]) / 2
    return {
        "runs": count,
        "median": median,
        "min": ordered[0],
        "max": ordered[-1],
        "spread_pct": ((ordered[-1] - ordered[0]) / median * 100) if median else 0.0,
    }
