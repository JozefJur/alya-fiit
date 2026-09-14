# API overview

59 endpoints, all under `/api`. The interactive OpenAPI documentation is served
by the backend itself:

- Swagger UI — <http://localhost:8000/docs>
- ReDoc — <http://localhost:8000/redoc>
- Schema — <http://localhost:8000/openapi.json>

## Conventions

- **Auth:** `Authorization: Bearer <jwt>` from `POST /api/auth/login`. Only
  `/api/health`, `/api/auth/login`, the public catalog and the payment callback
  are open.
- **Money** is serialised as a string with two decimals (`"219.19"`) so nothing
  is lost to floating point. All prices in requests are **net** (excluding VAT);
  responses carry both.
- **Errors** always use one envelope:

  ```json
  { "error": { "code": "insufficient_stock", "message": "…", "details": {} } }
  ```

  | Status | Typical codes |
  |---|---|
  | 401 | `not_authenticated`, `invalid_credentials`, `invalid_token` |
  | 403 | `not_authorized` |
  | 404 | `not_found` |
  | 422 | `validation_error`, `invalid_quantity`, `csv_import_error` |
  | 409 | `insufficient_stock`, `product_not_available`, `coupon_not_eligible`, `invalid_state_transition`, `duplicate_callback_conflict`, `conflict` |

- **Roles:** C = customer, W = warehouse staff, S = support agent,
  A = administrator, — = public.

## Public / authentication

| Method | Path | Role | Purpose |
|---|---|---|---|
| GET | `/api/health` | — | Liveness probe |
| POST | `/api/auth/login` | — | Exchange e-mail + password for a JWT |
| GET | `/api/auth/me` | any | Current user |
| GET | `/api/auth/addresses` | C | The customer's saved addresses |
| POST | `/api/auth/addresses` | C | Add an address |
| GET | `/api/notifications/mine` | any | The caller's notification outbox entries |

## Catalog (public, active items only)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/catalog/categories` | Active categories |
| GET | `/api/catalog/brands` | Brands for the filter |
| GET | `/api/catalog/products` | Search, filter, sort, paginate |
| GET | `/api/catalog/products/{id}` | Product detail with variants and availability |

`GET /api/catalog/products` query parameters:

| Parameter | Meaning |
|---|---|
| `search` | Matches the product name or brand |
| `category_id`, `brand` | Exact filters |
| `price_min`, `price_max` | Net base-price range |
| `in_stock_only` | Only products with an available variant |
| `sort` | `name` (default), `price_asc`, `price_desc`, `newest` |
| `page`, `page_size` | 1-based paging, `page_size` ≤ 60 |

Response: `{ items: [...], total, page, page_size }`.

## Cart (customer)

Every cart endpoint returns the **complete, freshly priced cart**, so the client
never computes totals itself.

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/cart` | The active cart with totals and per-item problems |
| POST | `/api/cart/items` | Add `{variant_id, quantity}` |
| PATCH | `/api/cart/items/{variant_id}` | Set a quantity (`0` removes the line) |
| DELETE | `/api/cart/items/{variant_id}` | Remove a line |
| DELETE | `/api/cart` | Empty the cart |
| POST | `/api/cart/coupon` | Attach `{code}` |
| DELETE | `/api/cart/coupon` | Detach the coupon |

The cart response carries `subtotal`, `discount_total`, `vat_total`,
`grand_total`, `coupon_code`, `coupon_error` and a `problems` array (per
variant: out of stock, no longer available).

## Orders (customer)

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/orders/checkout` | Cart → paid order, in one transaction |
| GET | `/api/orders` | The customer's own orders |
| GET | `/api/orders/{id}` | Order detail (owner, or any staff role) |
| POST | `/api/orders/{id}/cancel` | Cancel while allowed (refunds if paid) |
| POST | `/api/orders/{id}/request-cancel` | Ask support to cancel during picking |
| POST | `/api/orders/{id}/request-return` | Ask to return a delivered order |

Checkout request:

```json
{
  "payment_token": "tok-success",
  "address": {"name": "…", "street": "…", "city": "…", "zip_code": "84216", "country": "SK"},
  "coupon_code": "WELCOME10"
}
```

Payment tokens select the simulated outcome deterministically:
`tok-success` → authorized, `tok-declined` → declined, `tok-timeout` → timeout.
Any other token is treated as a decline — the simulation never authorises by
accident.

The response is the full order detail, including `allowed_events` (what the
current user may do next) and `status_history`.

## Payments (simulated gateway callback)

| Method | Path | Role | Purpose |
|---|---|---|---|
| POST | `/api/payments/callback` | — | Deliver a payment result |

```json
{"idempotency_key": "AF-2026-000001-p1", "status": "authorized"}
```

This models the *provider* calling back, so it carries no user token. It is
idempotent: replaying the same key returns `{"replayed": true}` without new
side effects; a contradicting status for a settled payment is rejected with
409 `duplicate_callback_conflict`.

## Warehouse (W, A)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/warehouse/orders` | Work queue (orders needing attention) |
| POST | `/api/warehouse/orders/{id}/start-picking` | `PAID → PICKING` |
| POST | `/api/warehouse/orders/{id}/mark-ready` | `PICKING → READY_TO_SHIP` |
| POST | `/api/warehouse/orders/{id}/ship` | `READY_TO_SHIP → SHIPPED`, consumes stock |
| POST | `/api/warehouse/orders/{id}/mark-delivered` | `SHIPPED → DELIVERED` |
| POST | `/api/warehouse/orders/{id}/receive-return` | `RETURN_APPROVED → RETURNED`, restocks |
| GET | `/api/warehouse/inventory` | Stock levels with low-stock flags |
| POST | `/api/warehouse/inventory/adjust` | `{variant_id, quantity_change, reason}` — reason required |
| POST | `/api/warehouse/inventory/threshold` | Set a per-variant low-stock threshold |
| GET | `/api/warehouse/inventory/{variant_id}/movements` | Movement history |

## Support (S, A)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/support/orders` | All orders |
| GET | `/api/support/orders/{id}` | Order detail |
| POST | `/api/support/orders/{id}/cancel` | Cancel an unshipped order |
| POST | `/api/support/orders/{id}/refund` | `RETURNED → REFUNDED` |
| GET | `/api/support/requests` | Pending cancellation/return requests |
| POST | `/api/support/requests/{id}/approve` | Approve a request |
| POST | `/api/support/requests/{id}/reject` | Reject a request |

## Administration (A)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/admin/categories` | All categories, including inactive |
| GET | `/api/admin/products` | Product list including inactive items |
| POST | `/api/admin/products` | Create a product |
| PATCH | `/api/admin/products/{id}` | Update price, texts, category, activation |
| POST | `/api/admin/products/{id}/variants` | Add a variant with initial stock |
| PATCH | `/api/admin/variants/{id}` | Update or deactivate a variant |
| POST | `/api/admin/products/import` | CSV product import |
| GET | `/api/admin/coupons` · POST · PATCH `/{id}` | Coupon management |
| GET | `/api/admin/users` · PATCH `/{id}` | Role and activation management |
| POST | `/api/admin/inventory/import` | CSV stock import (all-or-nothing) |
| GET | `/api/admin/inventory/export.csv` | CSV stock export |
| GET | `/api/admin/reports/inventory-sales` | The combined report (see below) |
| GET | `/api/admin/reports/inventory-sales.csv` | The same data as CSV |
| GET | `/api/admin/audit-log` | Audit trail, filterable by entity |
| GET | `/api/admin/notifications` | The whole notification outbox |

### Inventory & sales report

```text
GET /api/admin/reports/inventory-sales?from=2026-08-01&to=2026-08-31&category_id=3&top_limit=10
```

```json
{
  "period": {"from": "2026-08-01", "to": "2026-08-31"},
  "summary": {
    "orders_total": 12, "orders_revenue": 9, "orders_cancelled": 2, "orders_refunded": 1,
    "revenue": "4210.55", "discount_total": "120.00", "average_order_value": "467.84",
    "total_on_hand": 450, "total_reserved": 12, "total_available": 438
  },
  "variants": [{"sku": "…", "quantity_sold": 3, "revenue": "…", "on_hand": 18,
                "reserved": 3, "available": 15, "is_low_stock": false}],
  "low_stock": [{"sku": "…", "available": 3, "low_stock_threshold": 4}],
  "top_products": [{"product_name": "…", "quantity_sold": 3, "revenue": "…"}],
  "high_cancellation_products": [{"product_name": "…", "orders": 5, "cancelled": 2, "ratio": "0.40"}]
}
```

CSV import formats:

```text
inventory:  sku,on_hand[,low_stock_threshold]      # on_hand is the new absolute quantity
products:   category_slug,name,brand,base_price[,vat_rate][,description]
```

Both validate every row first; if any row is invalid the whole file is rejected
with `csv_import_error` and a `details.row_errors` list (line, field, message),
and nothing is applied.
