# Alya-FIIT

Alya-FIIT is our electronics e-shop with an integrated warehouse back office.
A customer browses the catalog, adds product variants to a cart, applies
coupons, checks out, and tracks the order. Warehouse staff pick and ship it,
support agents handle cancellations and returns, and administrators manage the
catalog, inventory, coupons, users, imports and reports.

This repository contains the whole application: FastAPI backend, React
frontend, the test suites and the tooling around them.

Payments and notifications run against local sandbox adapters, so a checkout
never contacts a provider and no mail is ever sent. All data in the seeded
environments is generated.

---

## Running it (Docker)

Requires Docker Desktop (macOS/Windows) or Docker Engine + the Compose plugin
(Linux). On Windows, Docker Desktop needs the **WSL2 backend**.

```bash
docker compose up --build -d
docker compose exec backend python scripts/manage.py seed-small
```

| | |
|---|---|
| Shop | <http://localhost:5173> |
| API documentation | <http://localhost:8000/docs> |

`docker compose down` stops it and keeps the database volume; add `-v` to drop
it as well.

### Local accounts

Created by `seed-small` in development and test environments only.

| Role | E-mail | Password |
|---|---|---|
| Administrator | `admin@alya.test` | `Admin123!` |
| Warehouse staff | `warehouse@alya.test` | `Warehouse123!` |
| Support agent | `support@alya.test` | `Support123!` |
| Customer | `customer1@alya.test` | `Customer123!` |
| Customer | `customer2@alya.test` | `Customer123!` |

The sign-in screen fills these in with one click.

### Sandbox payments

Checkout talks to the sandbox payment adapter, which returns the outcome the
chosen card asks for:

| Card on the checkout page | Token | Result |
|---|---|---|
| Sandbox card — authorized | `tok-success` | Payment authorized, order `PAID` |
| Sandbox card — declined | `tok-declined` | Order `PAYMENT_FAILED` |
| Sandbox card — timeout | `tok-timeout` | Order `PAYMENT_FAILED` |

Seeded coupons: `WELCOME10` (10 %), `FIIT5` (5 € off, minimum 50 € net),
`LAPTOP50` (50 € off laptops), plus `EXPIRED10` and `EXHAUSTED`, which are
invalid by design so the rejection paths can be exercised.

---

## Commands

Everything goes through one cross-platform script that needs nothing but
Python — it behaves the same in PowerShell, cmd, bash and zsh:

```bash
python scripts/task.py --list      # show every target
python scripts/task.py <target>
```

On macOS/Linux (or WSL/Git Bash) `make <target>` wraps the same script.

| Target | What it does |
|---|---|
| `setup` | Create the backend venv, install backend and frontend dependencies |
| `up` / `down` / `logs` | Docker Compose lifecycle |
| `reset` | Empty the development database |
| `seed-small` | Reset and load the development dataset |
| `seed-performance` | Load the large dataset used for performance work |
| `lint` | Ruff, ruff format check, mypy, Bandit, ESLint, tsc |
| `metrics` | Radon complexity and maintainability index |
| `audit` | pip-audit and npm audit (needs network) |
| `test-unit` / `test-integration` / `test-e2e` / `test` | Test levels |
| `coverage` | Backend tests with a coverage report |
| `profile-report` | cProfile + tracemalloc profile of the report endpoint |
| `benchmark-report` | Repeated benchmark of the report endpoint |
| `site` | Render the documentation into browsable HTML (`site/`) |
| `dev-backend` / `dev-frontend` | Run one process directly, with reload |

---

## Running it without Docker

For machines where Docker is not available. It works, but Docker is the
supported path.

**Prerequisites:** Python 3.12+ and Node.js 20+ on `PATH`.

> macOS ships Python 3.9 as `python3`. `scripts/task.py setup` looks for a
> newer interpreter on `PATH` and tells you if it cannot find one; you can also
> pick it explicitly: `python3.13 scripts/task.py setup`.

### 1. Install dependencies

```bash
python scripts/task.py setup
```

Or by hand:

```bash
# backend
cd backend
python -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"        # Windows: .venv\Scripts\python -m pip install -e ".[dev]"
cd ..

# frontend
cd frontend
npm install
cd ..
```

### 2. Seed the database

```bash
python scripts/task.py seed-small
```

### 3. Start both processes (two terminals)

```bash
# terminal 1 — backend on http://localhost:8000
python scripts/task.py dev-backend

# terminal 2 — frontend on http://localhost:5173
python scripts/task.py dev-frontend
```

The Vite dev server proxies `/api` to `http://localhost:8000`, so the browser
stays same-origin and no CORS setup is needed. Point it elsewhere with
`VITE_API_PROXY_TARGET`.

---

## Testing

```bash
python scripts/task.py test-unit
python scripts/task.py test-integration
python scripts/task.py test-e2e
python scripts/task.py coverage
```

E2E needs the browser binary once:
`cd frontend && npx playwright install chromium`. Playwright starts its own
backend (port 8001) and frontend (port 5174) against a dedicated `e2e.db`, so a
test run never disturbs your development database.

Conventions, fixtures and troubleshooting:
[docs/testing-guide.md](docs/testing-guide.md).

## Documentation

Browsable HTML version: open [`site/index.html`](site/index.html) — offline, no
server needed. Regenerate it with `python scripts/task.py site` after editing
any Markdown source.

| Document | Content |
|---|---|
| [docs/architecture.md](docs/architecture.md) | Layers, modules, boundaries, transactions, error handling |
| [docs/domain-model.md](docs/domain-model.md) | Entities, invariants, pricing and VAT rules, authorization matrix |
| [docs/order-state-machine.md](docs/order-state-machine.md) | Order states, transitions, roles, stock effects |
| [docs/api-overview.md](docs/api-overview.md) | All 59 endpoints, error envelope, report format |
| [docs/business-goals-and-acceptance.md](docs/business-goals-and-acceptance.md) | Product requirements and acceptance criteria |
| [docs/testing-guide.md](docs/testing-guide.md) | How to run and write tests at each level |
| [docs/performance.md](docs/performance.md) | Large dataset, benchmarking and profiling tooling |

## Architecture in one picture

```text
React + TypeScript (Vite)
  → FastAPI router + Pydantic validation
    → application service / use case      (orchestration, transaction boundary)
      → domain policies, state machines   (business rules, pure and unit-testable)
      → repositories (SQLAlchemy 2.x)
        → SQLite

Local adapters: sandbox payment gateway · notification outbox · audit log · CSV
```

Prices, discounts, VAT and coupon eligibility are computed **only** on the
server; the frontend displays what the API returns.

## Technology stack

| Area | Choice |
|---|---|
| Backend | Python 3.12+, FastAPI, SQLAlchemy 2.x, Pydantic 2.x, Uvicorn |
| Database | SQLite (separate dev / test / e2e / performance files) |
| Frontend | React 19, TypeScript 5, Vite 7, React Router |
| Backend tests | pytest, pytest-cov, pytest-mock |
| E2E tests | Playwright (TypeScript) |
| Quality | Ruff, mypy, Radon, Bandit, pip-audit, ESLint + eslint-plugin-sonarjs, tsc |
| Profiling | cProfile, tracemalloc; Locust for load scenarios |
| Containers | Docker, Docker Compose |
| CI | GitHub Actions (lint, types, unit, integration, E2E) |

### Verified environment

| Component | Version |
|---|---|
| Python | **3.14.4** (project requires ≥ 3.12) |
| Node.js | **24.20.0** (npm 11.19) |
| Docker | **29.4.0**, Compose **v5.1.2** |
| OS | macOS 26.6 (arm64) |

Backend package versions are pinned in
[`backend/requirements.lock`](backend/requirements.lock) (used by the Docker
image); `pyproject.toml` keeps compatible ranges for the manual setup. Frontend
versions are pinned in `frontend/package-lock.json`. Docker images:
`python:3.14-slim` and `node:24-alpine`.

## Environment variables

Copy [.env.example](.env.example) to `.env` to change anything; every value has
a working local default and the repository contains no secrets.

| Variable | Default | Meaning |
|---|---|---|
| `ALYA_DATABASE_URL` | `sqlite:///backend/data/dev.db` | Database file (absolute path required) |
| `ALYA_JWT_SECRET` | development placeholder | JWT signing key |
| `ALYA_VAT_RATE` | `0.23` | Default VAT rate |
| `ALYA_MAX_QUANTITY_PER_LINE` | `10` | Cart limit per line |
| `ALYA_DEFAULT_LOW_STOCK_THRESHOLD` | `5` | Low-stock threshold when a variant has none |
| `ALYA_RETURN_WINDOW_DAYS` | `14` | How long a delivered order may be returned |
| `VITE_API_PROXY_TARGET` | `http://localhost:8000` | Backend origin for the Vite dev server |

## Known limitations

- **SQLite only.** Writes are serialised; this is not sized for concurrent
  load. The Locust scenario shows contention, not throughput.
- **Sandbox payments and notifications.** No provider is contacted;
  notifications go to a database outbox the admin UI can display.
- **Authentication is minimal.** Fixed accounts, JWT with a local secret, no
  registration, password reset, MFA or third-party login.
- **No database migrations.** The schema is created from the models; changing
  it means resetting and reseeding.
- **Docker Desktop on Windows requires the WSL2 backend.**
- **The performance benchmark is a manual step** and is not part of CI.
- **`make` is not available by default on Windows.** Use
  `python scripts/task.py <target>`.
