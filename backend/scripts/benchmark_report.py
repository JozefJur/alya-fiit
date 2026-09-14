"""Repeatable benchmark of the admin inventory & sales report.

    python scripts/task.py benchmark-report
    python backend/scripts/benchmark_report.py --runs 7 --warmup 2

Measures wall-clock time, CPU time and the number of SQL statements per run,
then reports median / min / max / spread over several repetitions — a single
run says nothing about a machine under load.

Needs the performance dataset (``python scripts/task.py seed-performance``)
and is run manually, not in CI.
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import time
import tracemalloc
from datetime import UTC, datetime

from _lab import (  # noqa: E402 - path bootstrap happens inside _lab
    OUTPUT_DIR,
    QueryCounter,
    add_window_arguments,
    build_report_workload,
    configure_perf_database,
    summarize,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Benchmark the inventory & sales report")
    parser.add_argument("--runs", type=int, default=5, help="measured repetitions (default 5)")
    parser.add_argument("--warmup", type=int, default=1, help="unmeasured warm-up runs")
    parser.add_argument("--json", action="store_true", help="also write a JSON result file")
    parser.add_argument(
        "--memory",
        action="store_true",
        help="add one tracemalloc run to report peak memory (not part of the timings)",
    )
    add_window_arguments(parser)
    args = parser.parse_args(argv)

    if args.runs < 5:
        print("note: fewer than 5 runs makes the median unreliable\n", file=sys.stderr)

    database = configure_perf_database()
    run_report, engine = build_report_workload(args.date_from, args.date_to, args.category)

    print(f"Database : {database}")
    print(f"Python   : {platform.python_version()} on {platform.platform()}")
    print(f"Workload : GET /api/admin/reports/inventory-sales ({args.date_from} … {args.date_to})")
    print(f"Runs     : {args.warmup} warm-up + {args.runs} measured\n")

    for _ in range(args.warmup):
        run_report()

    wall_times: list[float] = []
    cpu_times: list[float] = []
    query_counts: list[float] = []
    rows = 0

    # Timing runs first, with tracemalloc OFF: tracing every allocation slows
    # this workload down by roughly 3x and would make the timings meaningless.
    for index in range(1, args.runs + 1):
        with QueryCounter(engine) as counter:
            start_wall = time.perf_counter()
            start_cpu = time.process_time()
            report = run_report()
            wall = time.perf_counter() - start_wall
            cpu = time.process_time() - start_cpu
        rows = len(report["variants"])
        wall_times.append(wall)
        cpu_times.append(cpu)
        query_counts.append(counter.count)
        print(
            f"  run {index}: {wall * 1000:8.1f} ms wall | {cpu * 1000:8.1f} ms cpu | "
            f"{counter.count:6d} queries"
        )

    peak_memory = 0
    if args.memory:
        print("\n  measuring peak memory in a separate traced run…")
        tracemalloc.start()
        run_report()
        _, peak_memory = tracemalloc.get_traced_memory()
        tracemalloc.stop()

    wall_stats = summarize(wall_times)
    cpu_stats = summarize(cpu_times)
    query_stats = summarize(query_counts)

    print("\nResults")
    print(
        f"  wall time   median {wall_stats['median'] * 1000:.1f} ms "
        f"(min {wall_stats['min'] * 1000:.1f}, max {wall_stats['max'] * 1000:.1f}, "
        f"spread {wall_stats['spread_pct']:.1f} %)"
    )
    print(f"  cpu time    median {cpu_stats['median'] * 1000:.1f} ms")
    print(
        f"  sql queries median {query_stats['median']:.0f} "
        f"(min {query_stats['min']:.0f}, max {query_stats['max']:.0f})"
    )
    if peak_memory:
        print(f"  peak memory {peak_memory / 1024 / 1024:.1f} MiB (traced run)")
    print(f"  report rows {rows}")

    if args.json:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        target = OUTPUT_DIR / f"benchmark-{stamp}.json"
        target.write_text(
            json.dumps(
                {
                    "timestamp": stamp,
                    "window": {"from": args.date_from, "to": args.date_to},
                    "python": platform.python_version(),
                    "platform": platform.platform(),
                    "runs": args.runs,
                    "wall_seconds": wall_stats,
                    "cpu_seconds": cpu_stats,
                    "sql_queries": query_stats,
                    "peak_memory_bytes": peak_memory,
                    "report_rows": rows,
                },
                indent=2,
            )
        )
        print(f"\nJSON written to {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
