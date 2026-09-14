# Architecture

Alya-FIIT is a **modular monolith**: one FastAPI backend process, one React frontend, one
SQLite database. Modularity comes from explicit layers and per-domain modules, not from
deployment units. Each layer boundary is a seam that can be tested and measured on its
own.

## 1. High-level picture

```text
React UI (TypeScript, Vite)
  → FastAPI router + request validation (Pydantic)
    → application service / use case        (orchestration, transactions)
      → domain entities / policies / state machines   (business rules, pure logic)
      → repositories (SQLAlchemy 2.x)       (persistence)
        → SQLite

Application services also call local adapters (ports & adapters style):
  → SimulatedPaymentGateway   (deterministic payment simulation)
  → NotificationGateway       (DB outbox instead of real e-mail)
  → AuditLogService           (append-only audit trail)
  → CSV import/export service
```

No external runtime services are used. Everything runs offline after dependencies are
installed.

## 2. Backend layout

```text
backend/
  app/
    api/
      routers/          # thin HTTP endpoints only: parse request, call use case, map response
      dependencies/     # auth (JWT), role guards, DB session, pagination params
    domain/
      entities/         # domain objects and enums (order status, movement types, roles)
      value_objects/    # Money, Quantity, CouponCode, DateRange, ...
      policies/         # pure decision logic (coupon eligibility, authorization, low stock…)
      state_machines/   # order state machine, shipment state machine
    application/
      services/         # stateful orchestration (cart, checkout, payment, picking, reports…)
      use_cases/        # one class per sensitive workflow with explicit transaction scope
      commands/         # input DTOs for use cases
      queries/          # read-side helpers (catalog filtering, report queries)
    infrastructure/
      persistence/      # engine/session factory, SQLAlchemy ORM models, DB bootstrap
      repositories/     # repository implementations over the ORM models
      adapters/         # simulated payment gateway, notification outbox, CSV, clock
      seed/             # seed-small and seed-performance data builders
    tests/
      unit/
      integration/
      fixtures/
  scripts/              # profiling, benchmark, and maintenance CLIs (run via task runner)
  pyproject.toml
```

### Dependency rule

- `domain` imports nothing from other layers (pure Python, fully unit-testable).
- `application` imports `domain` and abstract ports; it never touches FastAPI or raw SQL.
- `infrastructure` implements persistence and adapters; it may import `domain` and
  `application` interfaces.
- `api` wires everything together via FastAPI dependency injection and stays thin: no
  business decisions in routers.

Adapters are defined as small Python protocols/ABCs (`PaymentGateway`,
`NotificationGateway`, `Clock`) in the application layer and implemented in
`infrastructure/adapters`. Tests substitute them with mocks or fakes.

## 3. Domain modules

Within the layers, code is organized by domain area (one module = one folder/file cluster
per layer):

| Module | Responsibility |
|---|---|
| `catalog` | Categories, products, variants, search/filtering, activation rules |
| `inventory` | Stock levels, movements, reservations, low-stock policy, CSV import/export |
| `cart` | One active cart per customer, item rules, quantity validation, merge |
| `pricing` | Money, VAT, discounts, coupons, cart/order price calculation |
| `orders` | Orders, order items, checkout, state machine, cancellation, returns |
| `payments` | Simulated gateway, payment processing, idempotency, refunds |
| `fulfillment` | Picking, shipment workflow, delivery estimate |
| `reporting` | Inventory & sales report, CSV exports |
| `users` | Users, roles, JWT auth, authorization policy |
| `platform` | Audit log, notification outbox, clock, shared errors |

## 4. Databases

SQLite with three separate database files (paths configurable via environment):

| Purpose | Default file | Used by |
|---|---|---|
| Development | `backend/data/dev.db` | `make up`, local runs, seed-small |
| Tests | `backend/data/test.db` (or per-test temp file) | pytest integration tests |
| Performance | `backend/data/perf.db` | seed-performance + benchmark |

The schema is created from the SQLAlchemy metadata on startup and by the seed scripts;
there is no migration tool yet. A reset empties the tables and reseeds.

SQLite pragmas: foreign keys ON; WAL journal mode for the dev/perf databases.

## 5. Transactions

A request gets one SQLAlchemy session (unit of work). Read endpoints are implicit. The
following workflows are **explicit transaction boundaries** — each runs inside a single
transaction in its use case, so a mid-way failure rolls back all of its effects:

| Use case | Must be atomic |
|---|---|
| Checkout | order + items snapshot, stock reservation, payment record, audit, notification |
| Payment result processing | payment status, order transition, reservation release on failure, audit |
| Order cancellation | order transition, reservation release, refund record, audit |
| Refund | payment/refund records, order transition, audit |
| Shipment | order transition, reservation consumption, stock movement, audit |
| Inventory CSV import | row validation + stock updates + movements with all-or-nothing semantics per documented policy |

The session/transaction is owned by the application layer (use case), not by routers or
repositories.

## 6. Authentication & authorization

- **AuthN:** JWT bearer tokens (HS256, local secret from `.env`), issued by
  `POST /api/auth/login`. Pre-seeded users only — no registration, no password reset,
  no third-party auth. Passwords hashed (bcrypt).
- **AuthZ:** two cooperating levels:
  1. Router dependencies enforce the required role(s) per endpoint (vertical access).
  2. `AuthorizationPolicy` + ownership checks in the application layer enforce
     object-level rules (horizontal access: a customer sees only their own carts,
     orders, addresses, requests).
- Roles: `customer`, `warehouse_staff`, `administrator`, `support_agent`
  (see [domain-model.md](domain-model.md) and the authorization matrix in the README
  once seeded accounts exist).

Every denied attempt returns the consistent error envelope below, with a stable error
code.

## 7. Error handling

Domain and application code raises typed exceptions; one FastAPI exception handler maps
them to HTTP:

| Exception family | HTTP | `error.code` example |
|---|---|---|
| Validation / bad input (semantic) | 422 | `validation_error` |
| Not authenticated | 401 | `not_authenticated` |
| Not authorized / ownership violation | 403 | `not_authorized` |
| Resource not found (or foreign object) | 404 | `not_found` |
| Domain rule violation (state transition, stock, coupon…) | 409 | `invalid_state_transition`, `insufficient_stock`, `coupon_not_eligible` |
| Idempotency replay detected | 200 (replayed result) or 409 per endpoint contract | `duplicate_callback` |

Error envelope (all non-2xx responses):

```json
{ "error": { "code": "insufficient_stock", "message": "…", "details": {"variant_id": 42} } }
```

The frontend renders `error.message` and uses `error.code` for behavior. E2E tests assert
on user-visible messages; integration tests assert on codes.

## 8. Frontend layout

```text
frontend/
  src/
    api/          # typed API client (fetch wrapper), error envelope handling, auth token store
    components/   # reusable presentational components
    features/     # feature modules: catalog, cart, checkout, orders, warehouse, admin, support
    pages/        # route-level pages composing features
    hooks/        # shared hooks (useAuth, useApi, usePagination…)
    types/        # TypeScript types mirroring API DTOs
  e2e/            # Playwright tests + fixtures
  package.json
```

- Routing: React Router. State: React hooks plus a small context for auth and the cart
  badge; no external state library.
- The server is the single source of truth for prices, discounts, VAT, coupon
  eligibility, and stock: the frontend only displays server-computed values and re-fetches
  after mutations.
- All interactive elements carry stable `data-testid` attributes for Playwright.

## 9. Local simulated integrations

| Port | Adapter | Behavior |
|---|---|---|
| `PaymentGateway` | `SimulatedPaymentGateway` | Deterministic outcomes (authorized, declined, timeout, duplicate callback, refund) selected via a test-safe payment token, never randomness |
| `NotificationGateway` | `OutboxNotificationGateway` | Writes notifications to a DB outbox table; admin/test can list them; nothing is actually sent |
| Audit | `AuditLogService` | Append-only table of security/business-significant events |
| CSV | import/export services | Local file/streaming only |

## 10. Quality tooling map

| Concern | Tool | Where |
|---|---|---|
| Python lint/format | Ruff | `make lint` |
| Python types | mypy | `make lint` |
| Complexity metrics | Radon | `make metrics` |
| Python security | Bandit, pip-audit | `make lint` (audit manual) |
| Frontend lint | ESLint + eslint-plugin-sonarjs | `make lint` |
| Frontend types | tsc --noEmit | `make lint` |
| Unit/integration tests | pytest (+pytest-cov, pytest-mock) | `make test-unit` / `make test-integration` |
| E2E | Playwright | `make test-e2e` |
| Profiling | cProfile, tracemalloc scripts | `make profile-report` |
| Benchmark | repeatable report benchmark | `make benchmark-report` |
| Load testing | Locust scenario | manual, out of CI |

All `make` targets are thin wrappers over the cross-platform runner
`python scripts/task.py <target>` (see [../README.md](../README.md)).
