"""cProfile + tracemalloc profile of the admin inventory & sales report.

    python scripts/task.py profile-report
    python backend/scripts/profile_report.py --sort tottime --limit 30

Writes a .prof file that can be opened with snakeviz or `python -m pstats`,
prints the hottest functions, and reports the allocation hot spots.
"""

from __future__ import annotations

import argparse
import cProfile
import io
import pstats
import tracemalloc
from datetime import UTC, datetime

from _lab import (  # noqa: E402 - path bootstrap happens inside _lab
    PROFILE_DIR,
    QueryCounter,
    add_window_arguments,
    build_report_workload,
    configure_perf_database,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Profile the inventory & sales report")
    parser.add_argument(
        "--sort",
        default="cumtime",
        choices=["cumtime", "tottime", "ncalls"],
        help="how to rank the printed functions (default cumtime)",
    )
    parser.add_argument("--limit", type=int, default=25, help="functions to print")
    parser.add_argument("--warmup", type=int, default=1, help="unprofiled warm-up runs")
    add_window_arguments(parser)
    args = parser.parse_args(argv)

    database = configure_perf_database()
    run_report, engine = build_report_workload(args.date_from, args.date_to, args.category)
    print(f"Database: {database}")
    print(f"Window  : {args.date_from} … {args.date_to}\n")

    for _ in range(args.warmup):
        run_report()

    tracemalloc.start(10)
    profiler = cProfile.Profile()
    with QueryCounter(engine) as counter:
        profiler.enable()
        report = run_report()
        profiler.disable()
    snapshot = tracemalloc.take_snapshot()
    tracemalloc.stop()

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    profile_path = PROFILE_DIR / f"report-{stamp}.prof"
    profiler.dump_stats(str(profile_path))

    buffer = io.StringIO()
    stats = pstats.Stats(profiler, stream=buffer).strip_dirs().sort_stats(args.sort)
    stats.print_stats(args.limit)
    print(buffer.getvalue())

    print(f"SQL statements executed: {counter.count}")
    print(f"Report rows: {len(report['variants'])}\n")
    if counter.statements:
        print("First statements (truncated):")
        for statement in counter.statements[:5]:
            print(f"  {statement}")

    print("\nTop allocation sites:")
    for stat in snapshot.statistics("lineno")[:10]:
        print(f"  {stat}")

    print(f"\nProfile written to {profile_path}")
    print("Inspect it with:  python -m pstats " + str(profile_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
