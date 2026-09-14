/**
 * E2E-04  Happy-path checkout (long)           (BG-01, BG-03, AC-01.2, AC-03.1/3)
 * E2E-05  Checkout with insufficient stock     (BG-02, AC-02.2)
 * E2E-06  Declined payment (long)              (BG-05, AC-05.1)
 * E2E-12  Server is the price authority        (BG-03)
 */

import { expect, test } from "@playwright/test";

import {
  addSkuToCart,
  amount,
  availabilityOf,
  checkout,
  fillAddress,
  openProduct,
  signIn,
  signInWithEmptyCart,
} from "./helpers";

test.describe("E2E-04 happy-path checkout", () => {
  test("customer goes from catalog to a confirmed, correctly priced order", async ({ page }) => {
    await signInWithEmptyCart(page, "customer");

    // 1. find a product and check the advertised availability
    const before = await availabilityOf(page, "NVMe", "DV-NVME-1TB");
    expect(before).toBeGreaterThan(1);

    // 2. add two units of a chosen variant
    await addSkuToCart(page, "NVMe", "DV-NVME-1TB", 2);

    // 3. review the cart and apply a valid coupon
    await page.goto("/cart");
    const undiscounted = await amount(page, "summary-total");
    await page.getByTestId("coupon-input").fill("WELCOME10");
    await page.getByTestId("apply-coupon").click();
    await expect(page.getByTestId("coupon-applied")).toBeVisible();
    const cartTotal = await amount(page, "summary-total");
    expect(cartTotal).toBeLessThan(undiscounted);

    // 4. the checkout page repeats exactly the same total
    await page.getByTestId("go-checkout").click();
    await expect(page.getByTestId("place-order")).toBeVisible();
    expect(await amount(page, "checkout-total")).toBeCloseTo(cartTotal, 2);

    // 5. fill in the address and pay with the "authorized" simulated card
    await fillAddress(page);
    await page.getByTestId("pay-success").click();
    await page.getByTestId("place-order").click();

    // 6. the order confirmation shows the frozen amounts
    await expect(page.getByTestId("order-confirmation")).toBeVisible();
    await expect(page.getByTestId("status-badge").first()).toHaveText("PAID");
    const orderNumber = await page.getByTestId("order-number").innerText();
    expect(await amount(page, "order-total")).toBeCloseTo(cartTotal, 2);

    // 7. the order appears in "My orders" with the same total
    await page.goto("/orders");
    const row = page.getByTestId(`order-row-${orderNumber}`);
    await expect(row).toContainText("PAID");
    await expect(row).toContainText(cartTotal.toFixed(2));

    // 8. the reserved units are gone from the advertised availability
    expect(await availabilityOf(page, "NVMe", "DV-NVME-1TB")).toBe(before - 2);

    // 9. the cart is empty again after a successful purchase
    await page.goto("/cart");
    await expect(page.getByTestId("empty-state")).toBeVisible();
  });

  test("order detail keeps its amounts after the catalog price changes", async ({ page }) => {
    await signInWithEmptyCart(page, "customer");
    await addSkuToCart(page, "Ergo Trackball", "VET-TB", 1);
    await checkout(page, "success");
    await expect(page.getByTestId("order-confirmation")).toBeVisible();
    const orderUrl = page.url();
    const originalTotal = await amount(page, "order-total");

    await page.getByTestId("logout-button").click();
    await signIn(page, "admin");
    await page.goto("/admin/products");
    await page.getByTestId("admin-search").fill("Trackball");
    await page.getByTestId("admin-search").press("Enter");
    const adminRow = page.locator('[data-testid^="admin-product-"]').first();
    // Wait for the filtered results before reading the row id, otherwise it
    // belongs to a product the next render replaces.
    await expect(adminRow).toContainText("Voltex Ergo Trackball");
    const productId = (await adminRow.getAttribute("data-testid"))?.replace(
      "admin-product-",
      ""
    );
    await page.getByTestId(`price-input-${productId}`).fill("500.00");
    await page.getByTestId(`price-save-${productId}`).click();
    await expect(page.getByTestId("info-message")).toBeVisible();

    await page.getByTestId("logout-button").click();
    await signIn(page, "customer");
    await page.goto(orderUrl);
    expect(await amount(page, "order-total")).toBeCloseTo(originalTotal, 2);
  });
});

test.describe("E2E-05 checkout with insufficient stock", () => {
  test("cart refuses more units than are available", async ({ page }) => {
    await signInWithEmptyCart(page, "customer");
    // Voltex AirLite 13 / 16 GB is seeded with 2 units.
    await openProduct(page, "AirLite");
    await expect(page.getByTestId("stock-VAL13-16-512")).toContainText("2 available");
    await page.getByTestId("variant-VAL13-16-512").click();
    await page.getByTestId("quantity-input").fill("3");
    await page.getByTestId("add-to-cart").click();

    await expect(page.getByTestId("error-message")).toContainText(/not enough stock/i);
    await page.goto("/cart");
    await expect(page.getByTestId("empty-state")).toBeVisible();
    // Availability is untouched: nothing was reserved.
    expect(await availabilityOf(page, "AirLite", "VAL13-16-512")).toBe(2);
  });

  test("stock taken by someone else blocks the checkout", async ({ page }) => {
    await signInWithEmptyCart(page, "customer");
    await addSkuToCart(page, "ErgoSplit", "NES-ERGO", 3);

    // A warehouse correction removes the stock while the cart still holds it.
    await page.getByTestId("logout-button").click();
    await signIn(page, "warehouse");
    await page.goto("/warehouse/inventory");
    await page.getByTestId("inventory-filter").fill("NES-ERGO");
    await page.getByTestId("adjust-NES-ERGO").click();
    await page.getByTestId("adjust-change").fill("-3");
    await page.getByTestId("adjust-reason").fill("Damaged in the warehouse");
    await page.getByTestId("adjust-submit").click();
    await expect(page.getByTestId("available-NES-ERGO")).toHaveText("1");

    await page.getByTestId("logout-button").click();
    await signIn(page, "customer");
    await page.goto("/cart");
    await expect(page.getByTestId("cart-problems")).toContainText("Only 1 left in stock");
    await expect(page.getByTestId("go-checkout")).toBeDisabled();
  });
});

test.describe("E2E-06 declined payment", () => {
  test("customer sees why it failed and the stock is released", async ({ page }) => {
    await signInWithEmptyCart(page, "customer");

    // 1. availability before the attempt
    const before = await availabilityOf(page, "Nova 8 Lite", "AN8L-128");

    // 2. add the item and go to checkout
    await addSkuToCart(page, "Nova 8 Lite", "AN8L-128", 1);

    // 3. pay with the card that always gets declined
    await checkout(page, "declined");

    // 4. the order page explains the failure in plain language
    await expect(page.getByTestId("payment-failed-box")).toContainText(/was not completed/i);
    await expect(page.getByTestId("status-badge").first()).toHaveText("PAYMENT FAILED");

    // 5. the reservation was released — availability is back to the start
    expect(await availabilityOf(page, "Nova 8 Lite", "AN8L-128")).toBe(before);

    // 6. the cart still holds the item so the customer can retry
    await page.goto("/cart");
    await expect(page.getByTestId("cart-line-AN8L-128")).toBeVisible();

    // 7. retrying with a working card succeeds
    await checkout(page, "success");
    await expect(page.getByTestId("order-confirmation")).toBeVisible();
    await expect(page.getByTestId("status-badge").first()).toHaveText("PAID");

    // 8. both attempts are visible in the order list
    await page.goto("/orders");
    await expect(page.getByTestId("orders-table")).toContainText("PAYMENT FAILED");
    await expect(page.getByTestId("orders-table")).toContainText("PAID");
  });
});

test.describe("E2E-12 the server is the price authority", () => {
  test("a tampered quantity field is rejected server-side", async ({ page }) => {
    await signInWithEmptyCart(page, "customer");
    await openProduct(page, "USB-C Hub");
    await page.getByTestId("variant-LU-HUB8").click();

    // Bypass the max attribute the way a curious user would (DevTools).
    await page.getByTestId("quantity-input").evaluate((element) => {
      const input = element as HTMLInputElement;
      input.removeAttribute("max");
    });
    await page.getByTestId("quantity-input").fill("999");
    await page.getByTestId("add-to-cart").click();

    await expect(page.getByTestId("error-message")).toBeVisible();
    await page.goto("/cart");
    await expect(page.getByTestId("empty-state")).toBeVisible();
  });

  test("checkout requires a complete address", async ({ page }) => {
    await signInWithEmptyCart(page, "customer");
    await addSkuToCart(page, "HDMI", "LU-HDMI21-2M", 1);
    await page.goto("/cart");
    await page.getByTestId("go-checkout").click();

    await page.getByTestId("place-order").click();
    await expect(page.getByTestId("place-order")).toBeVisible();
    await expect(page.locator(".field-error").first()).toBeVisible();

    await fillAddress(page);
    await page.getByTestId("address-zip").fill("not-a-zip");
    await page.getByTestId("place-order").click();
    await expect(page.locator(".field-error").first()).toContainText(/ZIP/i);
  });
});
