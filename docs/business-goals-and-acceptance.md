# Business goals and acceptance criteria

Product requirements for Alya-FIIT, written as:

```text
Business goal → user story → acceptance criterion
```

Acceptance criteria are phrased so they can be checked without asking the author what
was meant.

## 1. Business goals

| ID | Business goal |
|---|---|
| BG-01 | A customer can find and order available products without an administrator's help |
| BG-02 | The system must never sell or reserve more units of a variant than are available |
| BG-03 | Price, discount, VAT, and total are transparent to the customer and server-side correct |
| BG-04 | Orders are processed only through allowed state transitions and authorized roles |
| BG-05 | A failed payment or a cancellation must not block stock long-term |
| BG-06 | The administrator has a consistent report of stock, sales, and low-stock items |

## 2. User stories and acceptance criteria

### BG-01 — self-service ordering

- **US-01.1** As a *customer*, I want to search and filter the catalog (name, brand,
  category, price range, availability) so that I can find a suitable product without help.
- **US-01.2** As a *customer*, I want to add a specific variant to my cart, adjust
  quantities, and check out with a simulated payment so that I can complete a purchase
  end-to-end on my own.

| AC | Criterion (measurable) |
|---|---|
| AC-01.1 | Searching "laptop" and filtering by an in-stock category returns only matching, active, available products within 1 page load; an empty result shows an explicit empty state |
| AC-01.2 | A logged-in customer can go from catalog to order confirmation in ≤ 8 UI steps; the order then appears in "My orders" with state `PAID` |
| AC-01.3 | Inactive products/variants are never shown in the catalog and cannot be added to a cart even by direct API call (server returns 409/404) |

### BG-02 — no overselling

- **US-02.1** As the *shop owner*, I want reservations and sales capped by availability so
  that I never promise stock I don't have.

| AC | Criterion |
|---|---|
| AC-02.1 | Adding more units than `available` to a cart is rejected with a clear message; the cart quantity never exceeds current availability |
| AC-02.2 | Checkout of quantities exceeding availability fails atomically: no order in a paid state, no partial reservation remains |
| AC-02.3 | After a successful checkout, `available` drops by the ordered quantity; concurrent second checkout of the remaining stock +1 fails |

### BG-03 — transparent, server-correct pricing

- **US-03.1** As a *customer*, I want to see subtotal, discount, VAT, and total before
  paying so that I know exactly what I will be charged.
- **US-03.2** As a *customer*, I want coupon eligibility explained (valid/invalid and why)
  so that pricing never surprises me.

| AC | Criterion |
|---|---|
| AC-03.1 | Cart and checkout show subtotal (net), discount, VAT, and grand total; the values equal the server calculation to the cent (the server is the source of truth) |
| AC-03.2 | A valid coupon reduces the total per its rules; an invalid one (expired, below minimum, wrong category, exhausted) is rejected with a reason and the total is unchanged |
| AC-03.3 | Order confirmation and order detail show the same frozen amounts as the checkout summary (snapshot), even if catalog prices change afterwards |

### BG-04 — controlled workflow

- **US-04.1** As *warehouse staff*, I want a queue of paid orders that I move through
  picking → ready → shipped so that fulfillment is orderly.
- **US-04.2** As the *shop owner*, I want state transitions restricted by role and current
  state so that nobody can corrupt an order's lifecycle.

| AC | Criterion |
|---|---|
| AC-04.1 | Warehouse staff can execute `PAID → PICKING → READY_TO_SHIP → SHIPPED`; each step is visible to the customer in order detail |
| AC-04.2 | A customer attempting a fulfillment transition (UI or direct API) gets 403; an invalid transition (e.g. `PAID → SHIPPED`) gets 409 |
| AC-04.3 | A customer sees only their own orders; requesting another customer's order returns 404/403 |
| AC-04.4 | Every executed transition creates an order-history entry with actor and time, visible to authorized roles |

### BG-05 — failed payments don't block stock

- **US-05.1** As the *shop owner*, I want reservations released on payment failure or
  cancellation so that stock returns to sale quickly.

| AC | Criterion |
|---|---|
| AC-05.1 | After a declined payment, the order is `PAYMENT_FAILED`, the customer sees an explanation, and `available` for the items returns to the pre-checkout value |
| AC-05.2 | Cancelling a `PAID` (not yet shipped) order refunds the payment and releases the reservation; both effects are visible (order detail + admin stock view) |
| AC-05.3 | A replayed payment callback changes nothing: one payment, one state change, one notification, one set of stock movements |

### BG-06 — consistent reporting

- **US-06.1** As an *administrator*, I want an inventory & sales report (sold quantities,
  revenue, stock levels, low-stock, cancellations, top products) for a date range so that
  I can run the shop from one screen.

| AC | Criterion |
|---|---|
| AC-06.1 | The report for a chosen period shows sold quantity per product/variant, revenue, discounts, average order value, current `on_hand`/`reserved`/`available`, low-stock list, cancelled/refunded counts, and top products — consistent with the underlying orders |
| AC-06.2 | Report numbers reconcile: e.g. revenue equals the sum of grand totals of the included orders; a variant flagged low-stock satisfies `available ≤ threshold` |
| AC-06.3 | The report is exportable as CSV with the same values |
