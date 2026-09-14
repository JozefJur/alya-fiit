# Performance tooling

The repository ships a large dataset, a benchmark and a profiler for the
reporting endpoints. None of it runs in CI — it is used when someone is
working on performance.

## The large dataset

```bash
python scripts/task.py seed-performance
```

Fills `backend/data/perf.db`, a file separate from the development, test and
E2E databases, so nothing else is affected. It is written with bulk inserts and
takes a few seconds.

| Rows | Count |
|---|---|
| Categories | 10 |
| Products | 1 000 |
| Product variants | 2 500 |
| Users | 20 005 |
| Orders | 50 000 |
| Order items | ~150 000 |
| Payments | 50 000 |
| Stock reservations | ~28 000 |
| Stock movements | ~101 000 |
| Audit entries | 50 000 |

A fixed RNG seed makes the dataset identical on every machine, so two runs of
the same code are comparable. Scale it down on a slow machine:

```bash
python backend/scripts/manage.py --database perf seed-performance --scale 0.2
```

## Benchmarking

```bash
python scripts/task.py benchmark-report
python backend/scripts/benchmark_report.py --runs 7 --memory --json
```

The workload is the administrator report:

```text
GET /api/admin/reports/inventory-sales?from=YYYY-MM-DD&to=YYYY-MM-DD[&category_id=N]
```

Per run and as a summary it reports:

- **wall time** — median, min, max and spread across the runs
- **CPU time** — shows whether the work is CPU-bound or waiting on I/O
- **SQL statement count** — machine independent, so it is comparable between
  runs on different hardware
- **peak memory** — only with `--memory`, measured in a separate run

Options:

| Option | Meaning |
|---|---|
| `--runs N` | Measured repetitions (default 5) |
| `--warmup N` | Unmeasured runs first (default 1) |
| `--from` / `--to` | Reporting window; the default is the last full month of the dataset |
| `--category` | Restrict to one category |
| `--memory` | Add one traced run for peak memory |
| `--json` | Also write the result to `backend/benchmark-output/` |

Report the **median of at least five runs**; a single measurement mostly
reflects what else the machine was doing. The spread tells you whether the
machine was quiet enough to trust the numbers.

> `tracemalloc` roughly triples the runtime of this workload, which is why the
> benchmark keeps it off during the timed runs and adds one extra traced run
> for the memory figure. Never quote a traced or profiled run as a timing.

## Profiling

```bash
python scripts/task.py profile-report
python backend/scripts/profile_report.py --sort tottime --limit 30
```

Output:

- the hottest functions by cumulative or own time (`pstats`)
- the number of SQL statements executed and the first few of them
- the top allocation sites (`tracemalloc`)
- a `.prof` file in `backend/profiling-output/`

```bash
python -m pstats backend/profiling-output/report-<timestamp>.prof
# inside: sort cumtime / stats 20 / callers <function>
pip install snakeviz && snakeviz backend/profiling-output/report-<timestamp>.prof
```

## Bulk CSV import

A second workload, for the inventory import path:

```bash
python backend/scripts/generate_import_csv.py --rows 20000 --out /tmp/stock.csv
```

`--invalid-ratio` mixes in invalid rows to check the validation and
all-or-nothing behavior. Post the file to `/api/admin/inventory/import` as an
administrator.

## Load scenario

`backend/locustfile.py` drives browse → cart → checkout:

```bash
backend/.venv/bin/python -m pip install ".[loadtest]"
backend/.venv/bin/python -m locust -f backend/locustfile.py --host http://localhost:8000
```

SQLite serialises writes, so the numbers show contention rather than the
throughput a server database would give.

## Keeping the results correct

`backend/app/tests/integration/test_reports.py` pins every value the report
produces, including the CSV export. Run it after any change to the reporting
code:

```bash
python scripts/task.py test-integration
```
