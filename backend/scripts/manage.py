"""Backend maintenance CLI: schema, reset, seeding.

Usage (from the repository root, cross-platform):

    python scripts/task.py reset
    python scripts/task.py seed-small
    python scripts/task.py seed-performance

or directly:

    python backend/scripts/manage.py seed-small --database dev
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

DATABASES = {
    "dev": "dev.db",
    "test": "test.db",
    "perf": "perf.db",
    "e2e": "e2e.db",
}


def _configure_database(target: str) -> Path:
    """Point the app at one of the three databases before importing settings."""
    if target not in DATABASES:
        raise SystemExit(f"unknown database '{target}' (choose from {', '.join(DATABASES)})")
    data_dir = BACKEND_DIR / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = data_dir / DATABASES[target]
    os.environ["ALYA_DATABASE_URL"] = f"sqlite:///{db_path}"
    return db_path


def _reset_files(db_path: Path) -> None:
    for suffix in ("", "-journal", "-wal", "-shm"):
        candidate = Path(str(db_path) + suffix)
        if candidate.exists():
            candidate.unlink()


def _wipe(db_path: Path, *, recreate_file: bool = False) -> None:
    """Empty the database.

    By default the tables are dropped and recreated **inside the existing
    file**. That matters whenever another process already has the database
    open — a running backend (Docker, `dev-backend`, an E2E server) keeps
    serving the old, unlinked inode if the file is deleted underneath it, and
    then silently shows empty data.

    ``recreate_file`` deletes the file instead. Only use it when you know no
    process is holding the database open, e.g. to reclaim space after the
    performance dataset.
    """
    from app.infrastructure.persistence.database import (
        create_schema,
        drop_schema,
        reset_state_for_tests,
    )

    reset_state_for_tests()
    if recreate_file:
        _reset_files(db_path)
    else:
        create_schema()
        drop_schema()
    create_schema()


def command_create_schema(_args: argparse.Namespace, db_path: Path) -> None:
    from app.infrastructure.persistence.database import create_schema

    create_schema()
    print(f"schema ready: {db_path}")


def command_reset(args: argparse.Namespace, db_path: Path) -> None:
    _wipe(db_path, recreate_file=args.recreate_file)
    print(f"database reset (empty schema): {db_path}")


def command_seed_small(args: argparse.Namespace, db_path: Path) -> None:
    from app.infrastructure.persistence.database import create_schema, get_session_factory
    from app.infrastructure.seed.small import seed_small

    if args.keep:
        create_schema()
    else:
        _wipe(db_path, recreate_file=args.recreate_file)
    started = time.perf_counter()
    session = get_session_factory()()
    try:
        summary = seed_small(session)
        session.commit()
    finally:
        session.close()
    elapsed = time.perf_counter() - started
    print(f"seed-small done in {elapsed:.2f}s → {db_path}")
    for key, value in summary.items():
        print(f"  {key:14} {value}")
    print("\nTest accounts (password in README):")
    print("  admin@alya.test / warehouse@alya.test / support@alya.test /")
    print("  customer1@alya.test / customer2@alya.test")


def command_seed_performance(args: argparse.Namespace, db_path: Path) -> None:
    from app.infrastructure.persistence.database import create_schema, get_engine
    from app.infrastructure.seed.performance import seed_performance

    if args.keep:
        create_schema()
    else:
        _wipe(db_path, recreate_file=args.recreate_file)
    started = time.perf_counter()
    summary = seed_performance(get_engine(), scale=args.scale)
    elapsed = time.perf_counter() - started
    print(f"seed-performance done in {elapsed:.1f}s → {db_path}")
    for key, value in summary.items():
        print(f"  {key:18} {value}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Alya-FIIT backend management")
    parser.add_argument(
        "--database",
        default="dev",
        choices=sorted(DATABASES),
        help="which SQLite database to act on (default: dev)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    recreate_help = (
        "delete and recreate the database file instead of emptying it in place; "
        "only safe when no server has the database open"
    )

    subparsers.add_parser("create-schema", help="create tables if missing")
    reset = subparsers.add_parser("reset", help="empty the database and recreate the schema")
    reset.add_argument("--recreate-file", action="store_true", help=recreate_help)

    small = subparsers.add_parser("seed-small", help="reset and load the development dataset")
    small.add_argument("--keep", action="store_true", help="do not wipe the database first")
    small.add_argument("--recreate-file", action="store_true", help=recreate_help)

    perf = subparsers.add_parser(
        "seed-performance", help="reset and bulk-load the large performance dataset"
    )
    perf.add_argument("--keep", action="store_true", help="do not wipe the database first")
    perf.add_argument("--recreate-file", action="store_true", help=recreate_help)
    perf.add_argument(
        "--scale",
        type=float,
        default=1.0,
        help="fraction of the full dataset (e.g. 0.1 for a quick smoke run)",
    )

    args = parser.parse_args(argv)
    db_path = _configure_database(args.database)

    handlers = {
        "create-schema": command_create_schema,
        "reset": command_reset,
        "seed-small": command_seed_small,
        "seed-performance": command_seed_performance,
    }
    handlers[args.command](args, db_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
