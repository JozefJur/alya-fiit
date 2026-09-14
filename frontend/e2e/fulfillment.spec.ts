/**
 * E2E-07  Warehouse processes an order (long)  (BG-04, AC-04.1)
 * E2E-08  A customer sees only own orders      (BG-04, AC-04.3)
 * E2E-11  Cancelling a paid order (long)       (BG-04, BG-05, AC-05.2)
 */

import { expect, test, type Page } from "@playwright/test";

import {
  addSkuToCart,
  availabilityOf,
  checkout,
  signIn,
  signInWithEmptyCart,
} from "./helpers";

/** Place a paid order as the customer and return its number and URL. */
async function placePaidOrder(
  page: Page,
  searchTerm: string,
  sku: string,
  quantity = 1
): Promise<{ number: string; url: string }> {
  await addSkuToCart(page, searchTerm, sku, quantity);
  await checkout(page, "success");
  await expect(page.getByTestId("order-confirmation")).toBeVisible();
  return {
    number: await page.getByTestId("order-number").innerText(),
    url: page.url(),
  };
}

test.describe("E2E-07 warehouse fulfillment", () => {
  test("an order travels from paid to delivered and the customer follows it", async ({ page }) => {
    // 1. the customer pays for an order
    await signInWithEmptyCart(page, "customer");
    const before = await availabilityOf(page, "Slim Wireless", "CPS-WL-GRY");
    const order = await placePaidOrder(page, "Slim Wireless", "CPS-WL-GRY", 2);
    expect(await availabilityOf(page, "Slim Wireless", "CPS-WL-GRY")).toBe(before - 2);

    // 2. warehouse staff find it in the work queue
    await page.getByTestId("logout-button").click();
    await signIn(page, "warehouse");
    await page.goto("/warehouse");
    const row = page.getByTestId(`queue-row-${order.number}`);
    await expect(row).toContainText("PAID");

    // 3. start picking
    await page.getByTestId(`start-picking-${order.number}`).click();
    await expect(row).toContainText("PICKING");

    // 4. mark it ready to ship
    await page.getByTestId(`mark-ready-${order.number}`).click();
    await expect(row).toContainText("READY TO SHIP");

    // 5. ship it
    await page.getByTestId(`ship-${order.number}`).click();
    await expect(row).toContainText("SHIPPED");

    // 6. shipping consumed the reservation, availability stays where it was
    expect(await availabilityOf(page, "Slim Wireless", "CPS-WL-GRY")).toBe(before - 2);
    await page.goto("/warehouse/inventory");
    await page.getByTestId("inventory-filter").fill("CPS-WL-GRY");
    await expect(page.getByTestId("stock-row-CPS-WL-GRY")).toContainText(String(before - 2));

    // 7. confirm the delivery
    await page.goto("/warehouse");
    await page.getByTestId(`mark-delivered-${order.number}`).click();
    await expect(page.getByTestId(`queue-row-${order.number}`)).toHaveCount(0);

    // 8. the customer sees the whole history on the order
    await page.getByTestId("logout-button").click();
    await signIn(page, "customer");
    await page.goto(order.url);
    await expect(page.getByTestId("status-badge").first()).toHaveText("DELIVERED");
    const history = page.getByTestId("order-history");
    await expect(history).toContainText("PICKING");
    await expect(history).toContainText("READY_TO_SHIP");
    await expect(history).toContainText("SHIPPED");
    await expect(history).toContainText("DELIVERED");
  });

  test("a customer cannot reach the warehouse screens", async ({ page }) => {
    await signIn(page, "customer");
    await page.goto("/warehouse");
    await expect(page.getByTestId("forbidden")).toBeVisible();
    await expect(page.getByTestId("nav-warehouse")).toHaveCount(0);
  });
});

test.describe("E2E-08 customers see only their own orders", () => {
  test("another customer's order is neither listed nor reachable by URL", async ({ page }) => {
    await signInWithEmptyCart(page, "customer");
    const order = await placePaidOrder(page, "Buds Mini", "ASB-MINI", 1);

    await page.getByTestId("logout-button").click();
    // Sign in as the second customer (no demo button for this one).
    await page.getByTestId("login-email").fill("customer2@alya.test");
    await page.getByTestId("login-password").fill("Customer123!");
    await page.getByTestId("login-submit").click();
    await expect(page.getByTestId("current-user")).toContainText("Zuzana");

    await page.goto("/orders");
    await expect(page.getByTestId(`order-row-${order.number}`)).toHaveCount(0);

    // Direct URL access shows an error instead of another customer's data.
    await page.goto(order.url);
    await expect(page.getByTestId("error-message")).toBeVisible();
    await expect(page.locator("body")).not.toContainText(order.number);
  });

  test("support staff may open any order", async ({ page }) => {
    await signInWithEmptyCart(page, "customer");
    const order = await placePaidOrder(page, "Buds Mini", "ASB-MINI", 1);

    await page.getByTestId("logout-button").click();
    await signIn(page, "support");
    await page.goto("/support");
    await expect(page.getByTestId(`support-order-${order.number}`)).toBeVisible();
  });
});

test.describe("E2E-11 cancelling a paid order", () => {
  test("cancellation refunds the payment and frees the reserved stock", async ({ page }) => {
    // 1. the customer pays for an order
    await signInWithEmptyCart(page, "customer");
    const before = await availabilityOf(page, "View 27", "NV27-4K");
    const order = await placePaidOrder(page, "View 27", "NV27-4K", 2);

    // 2. the stock is reserved
    expect(await availabilityOf(page, "View 27", "NV27-4K")).toBe(before - 2);

    // 3. the order offers cancellation while it is not shipped yet
    await page.goto(order.url);
    await expect(page.getByTestId("cancel-order")).toBeVisible();

    // 4. cancel it with a reason
    await page.getByTestId("action-reason").fill("Ordered the wrong size");
    await page.getByTestId("cancel-order").click();

    // 5. the order is cancelled and the action is gone
    await expect(page.getByTestId("status-badge").first()).toHaveText("CANCELLED");
    await expect(page.getByTestId("cancel-order")).toHaveCount(0);

    // 6. the reservation was released
    expect(await availabilityOf(page, "View 27", "NV27-4K")).toBe(before);

    // 7. the history records who cancelled it and why
    await page.goto(order.url);
    await expect(page.getByTestId("order-history")).toContainText("CANCELLED");
    await expect(page.getByTestId("order-history")).toContainText("Ordered the wrong size");

    // 8. an administrator can see the refund in the audit trail
    await page.getByTestId("logout-button").click();
    await signIn(page, "admin");
    await page.goto("/admin/audit");
    await expect(page.getByTestId("audit-table")).toContainText("payment.refunded");
  });

  test("a shipped order can no longer be cancelled by the customer", async ({ page }) => {
    await signInWithEmptyCart(page, "customer");
    const order = await placePaidOrder(page, "Precision X", "CPX-WHITE", 1);

    await page.getByTestId("logout-button").click();
    await signIn(page, "warehouse");
    await page.goto("/warehouse");
    await page.getByTestId(`start-picking-${order.number}`).click();
    await page.getByTestId(`mark-ready-${order.number}`).click();
    await page.getByTestId(`ship-${order.number}`).click();

    await page.getByTestId("logout-button").click();
    await signIn(page, "customer");
    await page.goto(order.url);
    await expect(page.getByTestId("status-badge").first()).toHaveText("SHIPPED");
    await expect(page.getByTestId("cancel-order")).toHaveCount(0);
    await expect(page.getByTestId("request-cancel")).toHaveCount(0);
  });

  test("cancelling during picking goes through a support decision", async ({ page }) => {
    await signInWithEmptyCart(page, "customer");
    const order = await placePaidOrder(page, "USB-C Hub", "LU-HUB8", 1);

    await page.getByTestId("logout-button").click();
    await signIn(page, "warehouse");
    await page.goto("/warehouse");
    await page.getByTestId(`start-picking-${order.number}`).click();

    // The customer can only *request* a cancellation now.
    await page.getByTestId("logout-button").click();
    await signIn(page, "customer");
    await page.goto(order.url);
    await expect(page.getByTestId("cancel-order")).toHaveCount(0);
    await page.getByTestId("action-reason").fill("Changed my mind");
    await page.getByTestId("request-cancel").click();

    // Support approves it; the order ends up cancelled.
    await page.getByTestId("logout-button").click();
    await signIn(page, "support");
    await page.goto("/support");
    const request = page.locator('[data-testid^="request-row-"]').first();
    await expect(request).toContainText(order.number);
    const requestId = (await request.getAttribute("data-testid"))?.replace("request-row-", "");
    await page.getByTestId(`approve-${requestId}`).click();
    await expect(page.getByTestId(`support-order-${order.number}`)).toContainText("CANCELLED");
  });
});
