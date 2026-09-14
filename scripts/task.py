#!/usr/bin/env python3
"""Cross-platform task runner for Alya-FIIT.

Works identically on Windows, macOS and Linux with only Python installed:

    python scripts/task.py setup
    python scripts/task.py up
    python scripts/task.py test

Run ``python scripts/task.py --list`` to see every target. The ``Makefile`` in
the repository root is a thin wrapper around this script for people who have
``make`` available.

Notes:
  * no shell syntax is used — every command is a list passed to subprocess,
    so quoting/globbing differences between shells cannot break it;
  * paths are built with pathlib, never by string concatenation with "/";
  * the virtualenv's interpreter is located per-OS (Scripts\\ vs bin/).
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
VENV = BACKEND / ".venv"
IS_WINDOWS = platform.system() == "Windows"

#: The backend needs at least this interpreter (see backend/pyproject.toml).
MINIMUM_PYTHON = (3, 12)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


class TaskError(RuntimeError):
    pass


def venv_python() -> Path:
    """Path to the backend virtualenv interpreter (per-OS layout)."""
    return (
        VENV
        / ("Scripts" if IS_WINDOWS else "bin")
        / ("python.exe" if IS_WINDOWS else "python")
    )


def python_for_backend() -> Path:
    """Prefer the venv interpreter; fall back to the current one."""
    candidate = venv_python()
    return candidate if candidate.exists() else Path(sys.executable)


def interpreter_version(executable: str | Path) -> tuple[int, int] | None:
    """(major, minor) of another interpreter, or None if it cannot be run."""
    probe = subprocess.run(
        [
            str(executable),
            "-c",
            "import sys; print(sys.version_info[0], sys.version_info[1])",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if probe.returncode != 0:
        return None
    try:
        major, minor = probe.stdout.split()
        return int(major), int(minor)
    except ValueError:
        return None


def find_suitable_python() -> Path:
    """An interpreter that satisfies MINIMUM_PYTHON.

    The interpreter running this script is preferred, but on macOS ``python3``
    is often the 3.9 that ships with the system — so named versions on PATH are
    tried before giving up.
    """
    if sys.version_info[:2] >= MINIMUM_PYTHON:
        return Path(sys.executable)

    wanted = f"{MINIMUM_PYTHON[0]}.{MINIMUM_PYTHON[1]}"
    for minor in range(20, MINIMUM_PYTHON[1] - 1, -1):
        name = f"python{MINIMUM_PYTHON[0]}.{minor}"
        found = shutil.which(name)
        if found and (interpreter_version(found) or (0, 0)) >= MINIMUM_PYTHON:
            print(
                f"note: {platform.python_version()} is too old; using {found} instead"
            )
            return Path(found)

    raise TaskError(
        f"Python {wanted}+ is required, but this is {platform.python_version()} "
        f"({sys.executable}).\n"
        "  Install a newer Python (https://www.python.org/downloads/ or your\n"
        "  package manager) and run this script with it, for example:\n"
        f"      python{wanted} scripts/task.py setup\n"
        "  Alternatively use the Docker path, which brings its own Python:\n"
        "      python scripts/task.py up"
    )


def npm_command() -> list[str]:
    """npm invocation that also works on Windows (npm.cmd)."""
    executable = shutil.which("npm")
    if executable is None:
        raise TaskError(
            "npm was not found on PATH. Install Node.js LTS (https://nodejs.org) "
            "or use the Docker path (python scripts/task.py up)."
        )
    return [executable]


def docker_compose_command() -> list[str]:
    """`docker compose` (v2) with a fallback to the legacy `docker-compose`."""
    if shutil.which("docker"):
        probe = subprocess.run(
            ["docker", "compose", "version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if probe.returncode == 0:
            return ["docker", "compose"]
    legacy = shutil.which("docker-compose")
    if legacy:
        return [legacy]
    raise TaskError(
        "Docker Compose was not found. Install Docker Desktop (Windows/macOS) or "
        "docker + the compose plugin (Linux). See README.md for the manual, "
        "Docker-free path."
    )


def run(
    command: Sequence[str | Path],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    check: bool = True,
) -> int:
    printable = " ".join(str(part) for part in command)
    location = cwd or ROOT
    print(f"\n$ {printable}\n  (in {location})", flush=True)
    merged_env = {**os.environ, **(env or {})}
    result = subprocess.run(
        [str(part) for part in command], cwd=str(location), env=merged_env, check=False
    )
    if check and result.returncode != 0:
        raise TaskError(
            f"command failed with exit code {result.returncode}: {printable}"
        )
    return result.returncode


def manage(*args: str, database: str = "dev") -> None:
    run(
        [
            python_for_backend(),
            BACKEND / "scripts" / "manage.py",
            "--database",
            database,
            *args,
        ],
        cwd=BACKEND,
    )


# ---------------------------------------------------------------------------
# targets
# ---------------------------------------------------------------------------


def task_setup() -> None:
    """Create the backend venv, install backend + frontend dependencies."""
    interpreter = find_suitable_python()

    existing = venv_python()
    if existing.exists():
        version = interpreter_version(existing)
        if version is None or version < MINIMUM_PYTHON:
            print(f"note: {VENV} has an unusable Python; recreating it")
            shutil.rmtree(VENV)
    if not venv_python().exists():
        run([interpreter, "-m", "venv", str(VENV)])
    run([venv_python(), "-m", "pip", "install", "--upgrade", "pip"])
    run([venv_python(), "-m", "pip", "install", "-e", ".[dev]"], cwd=BACKEND)
    run([*npm_command(), "install"], cwd=FRONTEND)
    print("\nSetup complete. Next: python scripts/task.py seed-small")


def task_up() -> None:
    """Start the whole application with Docker Compose (primary path)."""
    run([*docker_compose_command(), "up", "--build", "-d"])
    print("\nBackend:  http://localhost:8000/docs")
    print("Frontend: http://localhost:5173")
    print("Seed the database with: python scripts/task.py seed-small")


def task_down() -> None:
    """Stop the Docker Compose stack (keeps the database volume)."""
    run([*docker_compose_command(), "down"])


def task_logs() -> None:
    """Tail Docker Compose logs."""
    run([*docker_compose_command(), "logs", "-f"], check=False)


def task_reset() -> None:
    """Wipe the development database and recreate an empty schema."""
    manage("reset")


def task_seed_small() -> None:
    """Reset the development database and load the development dataset."""
    manage("seed-small")


def task_seed_performance() -> None:
    """Load the large performance dataset (manual step, never in CI)."""
    manage("seed-performance", database="perf")


def task_lint() -> None:
    """Run every static check: ruff, mypy, bandit, eslint, tsc."""
    python = python_for_backend()
    run([python, "-m", "ruff", "check", "app"], cwd=BACKEND)
    run([python, "-m", "ruff", "format", "--check", "app"], cwd=BACKEND)
    run([python, "-m", "ruff", "check", str(ROOT / "scripts")])
    run([python, "-m", "ruff", "format", "--check", str(ROOT / "scripts")])
    run([python, "-m", "mypy", "app"], cwd=BACKEND)
    run(
        [python, "-m", "bandit", "-q", "-c", "pyproject.toml", "-r", "app"], cwd=BACKEND
    )
    run([*npm_command(), "run", "lint"], cwd=FRONTEND)
    run([*npm_command(), "run", "typecheck"], cwd=FRONTEND)


def task_audit() -> None:
    """Check dependencies for known vulnerabilities (manual, network needed)."""
    run([python_for_backend(), "-m", "pip_audit"], cwd=BACKEND, check=False)
    run([*npm_command(), "audit"], cwd=FRONTEND, check=False)


#: Optional local config for the docs build, e.g.
#: {"output": "site", "sections": [{"path": "guides", "title": "Guides"}]}
#: — see scripts/build_site.py. A missing file builds the documentation alone.
SITE_CONFIG = ROOT / "scripts" / "site.local.json"


def task_site() -> None:
    """Render the documentation into the static HTML site (site/)."""
    command: list[str | Path] = [
        python_for_backend(),
        ROOT / "scripts" / "build_site.py",
    ]
    if SITE_CONFIG.exists():
        config = json.loads(SITE_CONFIG.read_text(encoding="utf-8"))
        if config.get("output"):
            command += ["--output", ROOT / config["output"]]

        sections = config.get("sections")
        if sections is None:
            # Older single-section form.
            sections = (
                [{"path": config["extra_section"], "title": config.get("extra_title")}]
                if config.get("extra_section")
                else []
            )
        for section in sections:
            path = section.get("path")
            if not path or not (ROOT / path).is_dir():
                continue
            command += ["--extra-section", path]
            command += ["--extra-title", section.get("title") or "Guides"]
    run(command)


def task_metrics() -> None:
    """Print complexity/maintainability metrics (Radon) for the backend."""
    python = python_for_backend()
    run(
        [python, "-m", "radon", "cc", "-s", "-a", "--total-average", "app"], cwd=BACKEND
    )
    run([python, "-m", "radon", "mi", "-s", "app"], cwd=BACKEND)


def task_test_unit() -> None:
    """Backend unit tests."""
    run([python_for_backend(), "-m", "pytest", "app/tests/unit"], cwd=BACKEND)


def task_test_integration() -> None:
    """Backend integration tests (isolated SQLite database per test)."""
    run([python_for_backend(), "-m", "pytest", "app/tests/integration"], cwd=BACKEND)


def task_test_e2e() -> None:
    """Playwright end-to-end tests (starts backend + frontend itself)."""
    run([*npm_command(), "run", "test:e2e"], cwd=FRONTEND)


def task_test() -> None:
    """Unit + integration + E2E."""
    task_test_unit()
    task_test_integration()
    task_test_e2e()


def task_coverage() -> None:
    """Backend tests with a coverage report (terminal + HTML)."""
    run(
        [
            python_for_backend(),
            "-m",
            "pytest",
            "app/tests/unit",
            "app/tests/integration",
            "--cov=app",
            "--cov-report=term-missing:skip-covered",
            "--cov-report=html",
        ],
        cwd=BACKEND,
    )
    print(f"\nHTML report: {BACKEND / 'htmlcov' / 'index.html'}")


def task_profile_report() -> None:
    """cProfile + tracemalloc profile of the report endpoint (perf database)."""
    run([python_for_backend(), BACKEND / "scripts" / "profile_report.py"], cwd=BACKEND)


def task_benchmark_report() -> None:
    """Repeated benchmark of the report endpoint (perf database, manual step)."""
    run(
        [python_for_backend(), BACKEND / "scripts" / "benchmark_report.py"], cwd=BACKEND
    )


def task_dev_backend() -> None:
    """Run the backend with autoreload (manual, Docker-free path)."""
    run(
        [
            python_for_backend(),
            "-m",
            "uvicorn",
            "app.main:app",
            "--reload",
            "--port",
            "8000",
        ],
        cwd=BACKEND,
        check=False,
    )


def task_dev_frontend() -> None:
    """Run the Vite dev server (manual, Docker-free path)."""
    run([*npm_command(), "run", "dev"], cwd=FRONTEND, check=False)


TARGETS: dict[str, Callable[[], None]] = {
    "setup": task_setup,
    "up": task_up,
    "down": task_down,
    "logs": task_logs,
    "reset": task_reset,
    "seed-small": task_seed_small,
    "seed-performance": task_seed_performance,
    "lint": task_lint,
    "audit": task_audit,
    "site": task_site,
    "metrics": task_metrics,
    "test-unit": task_test_unit,
    "test-integration": task_test_integration,
    "test-e2e": task_test_e2e,
    "test": task_test,
    "coverage": task_coverage,
    "profile-report": task_profile_report,
    "benchmark-report": task_benchmark_report,
    "dev-backend": task_dev_backend,
    "dev-frontend": task_dev_frontend,
}


def print_targets() -> None:
    print("Available targets:\n")
    width = max(len(name) for name in TARGETS)
    for name, function in TARGETS.items():
        summary = (function.__doc__ or "").strip().splitlines()[0]
        print(f"  {name.ljust(width)}  {summary}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Alya-FIIT cross-platform task runner",
        epilog="Example: python scripts/task.py seed-small",
    )
    parser.add_argument("target", nargs="?", help="task to run (see --list)")
    parser.add_argument("--list", action="store_true", help="list available targets")
    args = parser.parse_args(argv)

    if args.list or not args.target:
        print_targets()
        return 0
    if args.target not in TARGETS:
        print(f"unknown target '{args.target}'\n", file=sys.stderr)
        print_targets()
        return 2
    try:
        TARGETS[args.target]()
    except TaskError as error:
        print(f"\nERROR: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
