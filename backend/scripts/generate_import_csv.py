"""Generate a large inventory CSV for the optional import benchmark.

    python backend/scripts/generate_import_csv.py --rows 20000 --out /tmp/stock.csv

By default the SKUs come from the performance database, so the file imports
cleanly. ``--invalid-ratio`` mixes in broken rows to check the validation and
all-or-nothing behavior instead.
"""

from __future__ import annotations

import argparse
import csv
import random
from pathlib import Path

from _lab import BACKEND_DIR, configure_perf_database  # noqa: E402 - path bootstrap


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate an inventory import CSV")
    parser.add_argument("--rows", type=int, default=20_000, help="rows to write")
    parser.add_argument(
        "--out",
        type=Path,
        default=BACKEND_DIR / "benchmark-output" / "stock-import.csv",
        help="output file",
    )
    parser.add_argument(
        "--invalid-ratio",
        type=float,
        default=0.0,
        help="fraction of invalid rows (0.0-1.0)",
    )
    parser.add_argument("--seed", type=int, default=20260101)
    args = parser.parse_args(argv)

    if not (0.0 <= args.invalid_ratio <= 1.0):
        raise SystemExit("--invalid-ratio must be within 0.0-1.0")

    configure_perf_database()
    from sqlalchemy import select

    from app.infrastructure.persistence.database import get_session_factory
    from app.infrastructure.persistence.models import ProductVariant

    session = get_session_factory()()
    try:
        skus = list(session.scalars(select(ProductVariant.sku).order_by(ProductVariant.id)))
    finally:
        session.close()
    if not skus:
        raise SystemExit("the performance database has no variants — seed it first")

    rng = random.Random(args.seed)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["sku", "on_hand", "low_stock_threshold"])
        written = 0
        invalid = 0
        for index in range(args.rows):
            sku = skus[index % len(skus)]
            if rng.random() < args.invalid_ratio:
                invalid += 1
                writer.writerow([f"MISSING-{index:06d}", "not-a-number", ""])
            else:
                writer.writerow([sku, rng.randint(0, 500), rng.choice(["", "3", "5", "10"])])
            written += 1

    print(f"wrote {written} rows ({invalid} invalid) to {args.out}")
    print("Import it as an administrator:")
    print("  POST /api/admin/inventory/import   (multipart field name: file)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
