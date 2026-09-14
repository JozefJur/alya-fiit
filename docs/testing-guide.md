# Testing guide

Everything runs locally, offline, with no external services.

## The three levels

| Level | Location | Runs against | Command |
|---|---|---|---|
| Unit | `backend/app/tests/unit/` | pure objects, fakes/mocks | `python scripts/task.py test-unit` |
| Integration | `backend/app/tests/integration/` | real FastAPI + isolated SQLite | `python scripts/task.py test-integration` |
| E2E | `frontend/e2e/` | the whole system through the browser | `python scripts/task.py test-e2e` |

```bash
python scripts/task.py test        # all three, in that order
python scripts/task.py coverage    # unit + integration with a coverage report
```

Current baseline: **178 unit**, **56 integration**, **29 E2E** — all green.

## Backend tests (pytest)

### Running

```bash
cd backend
.venv/bin/python -m pytest app/tests/unit            # one level
.venv/bin/python -m pytest -k coupon                 # by name
.venv/bin/python -m pytest app/tests/unit/test_money.py::TestMoneyAllocation
.venv/bin/python -m pytest -x -vv                    # stop at the first failure, verbose
```

On Windows use `backend\.venv\Scripts\python -m pytest …`, or simply
`python scripts/task.py test-unit` everywhere.

### Fixtures

Defined once in `backend/app/tests/conftest.py`:

| Fixture | Gives you |
|---|---|
| `client` | `TestClient` on a fresh database seeded with `seed-small` |
| `session_factory` | Sessions on that same database — inspect or modify state directly |
| `services` | The wired service container on an empty database |
| `seeded_services` | The same, with `seed-small` loaded |
| `auth_headers` | `auth_headers("admin@alya.test")` → `{"Authorization": "Bearer …"}` |
| `fixed_now` | A stable timestamp for date-dependent rules |

Every integration test gets its **own database file** (pytest's `tmp_path`), so
tests never share state and can run in any order.

### Test doubles

`backend/app/tests/fixtures/doubles.py` holds hand-written fakes that need no
database: `FakeCategory`, `FakeProduct`, `FakeVariant`, `FakeStockLevel`,
`FakeCoupon`, `FakeOrder`, `FakeAuditLog`, `FakeClock`, and a `line()` builder
for pricing inputs. Prefer these over `unittest.mock.Mock` when you need
realistic attributes; use `pytest-mock`'s `mocker` when you want to assert on
calls.

```python
def test_expired_coupon_is_rejected():
    coupon = FakeCoupon(valid_until=datetime(2026, 6, 1))
    with pytest.raises(CouponNotEligibleError) as error:
        CouponValidator().validate(coupon, [line()], datetime(2026, 6, 15))
    assert error.value.reason == "expired"
```

Time is always injected (`Clock` / `FixedClock`), so no test depends on the
real clock.

### Writing good tests here

- **Name the behavior, not the method:**
  `test_reservation_is_released_when_the_payment_is_declined`, not `test_pay2`.
- **One behavior per test**, with the assertion that would actually fail if the
  behavior regressed.
- **Prepare your own data.** Do not rely on what an earlier test left behind.
- **Assert on the error contract** (`error.code`, HTTP status), not on message
  wording — messages are user-facing and may be reworded.
- **Cover the boundary**, not just the happy path: exactly at a limit, one
  above, zero, empty, and the negative case.

### Coverage

```bash
python scripts/task.py coverage      # terminal summary + backend/htmlcov/index.html
```

A line executed by no assertion is not tested, so read the report by branch,
not by percentage.

## E2E tests (Playwright)

### Running

```bash
python scripts/task.py test-e2e
cd frontend && npx playwright test --ui          # interactive runner
cd frontend && npx playwright test -g "coupon"   # by title
cd frontend && npx playwright show-report        # last HTML report
```

Playwright starts **both** processes itself on dedicated ports (backend 8001,
frontend 5174) so a run never touches your own dev servers on 8000/5173, and
`e2e/global-setup.ts` reseeds a dedicated `backend/data/e2e.db` before the
suite. First run needs the browser binary:

```bash
cd frontend && npx playwright install chromium
```

On failure Playwright keeps a screenshot, a video and a trace under
`frontend/test-results/`:

```bash
npx playwright show-trace test-results/<folder>/trace.zip
```

### Selectors

Use `data-testid` only:

```ts
await page.getByTestId("add-to-cart").click();
await expect(page.getByTestId("summary-total")).toContainText("219.19");
```

Never select by CSS class, DOM position or visible text — those change with
every styling or copy edit. Every interactive element in the app already has a
stable `data-testid`.

### Helpers

`frontend/e2e/helpers.ts` provides `signIn`, `signInWithEmptyCart`, `resetCart`,
`openProduct`, `addSkuToCart`, `fillAddress`, `checkout`, `availabilityOf` and
`amount`. The suite shares one database, so **any test that touches the cart
starts with `signInWithEmptyCart`** — that is what keeps the scenarios
order-independent.

### Two traps worth knowing

1. **Wait for the state you assert on, not for a timeout.** After a search,
   assert the filtered row's content before reading its id — otherwise you read
   a row the next render replaces.
2. **`page.goto` returns before the data arrives.** Wait for a rendered element
   (`cart-summary` or `empty-state`) before deciding what the page shows.

## Quality tools

```bash
python scripts/task.py lint        # ruff, ruff format --check, mypy, bandit, eslint, tsc
python scripts/task.py metrics     # radon cc + mi
python scripts/task.py audit       # pip-audit + npm audit (needs network)
```

| Tool | Checks |
|---|---|
| Ruff | Python style, imports, bugbear, complexity (`C901`) |
| mypy | Python types |
| Bandit | common Python security issues |
| pip-audit / npm audit | known vulnerabilities in dependencies |
| ESLint + sonarjs | JS/TS correctness, cognitive complexity |
| tsc | TypeScript types |
| Radon | cyclomatic complexity, maintainability index |

## Continuous integration

`.github/workflows/ci.yml` runs on every push and pull request:

1. Python lint (Ruff, format check) and type check (mypy)
2. Frontend lint (ESLint) and type check (tsc)
3. Backend unit tests
4. Backend integration tests
5. Playwright E2E tests

CI runs on **`seed-small` only**. The large performance dataset and
`benchmark-report` are run manually, not on every push.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| E2E fails but the app works by hand | A stale dev server or database. E2E uses its own ports and `e2e.db`; check `frontend/test-results/` for the screenshot. |
| `sqlite3.OperationalError: no such table` | Schema missing — `python scripts/task.py seed-small`. |
| Integration tests are slow | Each test seeds its own database (~0.3 s). Use `-k` while iterating. |
| `playwright: command not found` | `cd frontend && npm install && npx playwright install chromium`. |
| Tests pass alone but fail in the suite | Shared state. Reset what your test needs (`signInWithEmptyCart`, own SKUs). |
