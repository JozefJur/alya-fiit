/**
 * E2E-01  Search & filter the catalog          (BG-01, AC-01.1)
 * E2E-02  Cart management                      (BG-01, AC-01.2)
 * E2E-03  Valid and invalid coupons            (BG-03, AC-03.2)
 */

import { expect, test } from "@playwright/test";

import { addSkuToCart, amount, openProduct, signIn, signInWithEmptyCart } from "./helpers";

test.describe("E2E-01 search and filter the catalog", () => {
  test("finds products by name, narrows by filters and shows an empty state", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByTestId("product-grid")).toBeVisible();
    const allProducts = await page.locator('[data-testid^="product-card-"]').count();
    expect(allProducts).toBeGreaterThan(0);

    // 1. search by product name
    await page.getByTestId("search-input").fill("ProBook");
    await page.getByTestId("search-submit").click();
    await expect(page.locator('[data-testid^="product-card-"]')).toHaveCount(1);
    await expect(page.getByTestId("product-grid")).toContainText("Voltex ProBook 14");

    // 2. search by brand
    await page.getByTestId("search-input").fill("LinkUp");
    await page.getByTestId("search-submit").click();
    await expect(page.locator('[data-testid^="product-card-"]')).toHaveCount(3);

    // 3. filter by category
    await page.getByTestId("search-input").fill("");
    await page.getByTestId("search-submit").click();
    await page.getByTestId("filter-category").selectOption({ label: "Keyboards" });
    await expect(page.locator('[data-testid^="product-card-"]')).toHaveCount(3);

    // 4. narrow further by price range
    await page.getByTestId("filter-price-min").fill("100");
    await page.getByTestId("filter-price-max").fill("200");
    await expect(page.locator('[data-testid^="product-card-"]')).toHaveCount(1);
    await expect(page.getByTestId("product-grid")).toContainText("Nordica ErgoSplit");

    // 5. nonsense query gives an explicit empty state
    await page.getByTestId("filter-price-min").fill("");
    await page.getByTestId("filter-price-max").fill("");
    await page.getByTestId("filter-category").selectOption("");
    await page.getByTestId("search-input").fill("definitely-not-a-product");
    await page.getByTestId("search-submit").click();
    await expect(page.getByTestId("empty-state")).toContainText("No products match");
  });

  test("in-stock filter hides sold-out products", async ({ page }) => {
    await page.goto("/");
    await page.getByTestId("filter-category").selectOption({ label: "Monitors" });
    await expect(page.getByTestId("product-grid")).toContainText("PixelForge Studio 24");

    await page.getByTestId("filter-in-stock").check();
    await expect(page.getByTestId("product-grid")).not.toContainText("PixelForge Studio 24");
  });

  test("sold-out variant cannot be added to the cart", async ({ page }) => {
    await signIn(page, "customer");
    await openProduct(page, "Studio 24");
    await expect(page.getByTestId("stock-PF24-SRGB")).toContainText("out of stock");
    await expect(page.getByTestId("add-to-cart")).toBeDisabled();
  });
});

test.describe("E2E-02 cart management", () => {
  test("add, change quantity, remove and re-add a variant", async ({ page }) => {
    await signInWithEmptyCart(page, "customer");

    // 1. add two units of a specific variant
    await addSkuToCart(page, "Mech TKL", "CPM-TKL-RED", 2);
    await expect(page.getByTestId("cart-badge")).toHaveText("2");

    // 2. the cart shows the line with server-computed totals
    await page.goto("/cart");
    await expect(page.getByTestId("cart-line-CPM-TKL-RED")).toBeVisible();
    const twoUnits = await amount(page, "summary-total");

    // 3. reduce the quantity → total drops
    await page.getByTestId("quantity-CPM-TKL-RED").fill("1");
    await expect(page.getByTestId("cart-badge")).toHaveText("1");
    const oneUnit = await amount(page, "summary-total");
    expect(oneUnit).toBeLessThan(twoUnits);
    expect(oneUnit * 2).toBeCloseTo(twoUnits, 1);

    // 4. remove the line → cart is empty
    await page.getByTestId("remove-CPM-TKL-RED").click();
    await expect(page.getByTestId("empty-state")).toBeVisible();
    await expect(page.getByTestId("cart-badge")).toHaveCount(0);

    // 5. re-add another variant and empty the whole cart
    await addSkuToCart(page, "Precision X", "CPX-BLACK", 1);
    await page.goto("/cart");
    await expect(page.getByTestId("cart-line-CPX-BLACK")).toBeVisible();
    await page.getByTestId("clear-cart").click();
    await expect(page.getByTestId("empty-state")).toBeVisible();
  });

  test("quantity above the per-line limit is refused by the server", async ({ page }) => {
    await signInWithEmptyCart(page, "customer");
    await openProduct(page, "HDMI");
    await page.getByTestId("quantity-input").fill("11");
    await page.getByTestId("add-to-cart").click();
    await expect(page.getByTestId("error-message")).toContainText("limited to 10");
  });
});

test.describe("E2E-03 coupons", () => {
  test("valid coupon discounts the total, invalid ones are explained", async ({ page }) => {
    await signInWithEmptyCart(page, "customer");
    await addSkuToCart(page, "Quiet 700", "ASQ700-BLK", 1);
    await page.goto("/cart");

    const original = await amount(page, "summary-total");

    // 1. expired coupon is rejected and leaves the total untouched
    await page.getByTestId("coupon-input").fill("EXPIRED10");
    await page.getByTestId("apply-coupon").click();
    await expect(page.getByTestId("error-message")).toContainText("expired");
    expect(await amount(page, "summary-total")).toBeCloseTo(original, 2);

    // 2. exhausted coupon is rejected too
    await page.getByTestId("coupon-input").fill("EXHAUSTED");
    await page.getByTestId("apply-coupon").click();
    await expect(page.getByTestId("error-message")).toContainText("usage limit");

    // 3. valid percentage coupon reduces the total
    await page.getByTestId("coupon-input").fill("WELCOME10");
    await page.getByTestId("apply-coupon").click();
    await expect(page.getByTestId("coupon-applied")).toContainText("WELCOME10");
    const discounted = await amount(page, "summary-total");
    expect(discounted).toBeLessThan(original);
    expect(await amount(page, "summary-discount")).toBeGreaterThan(0);

    // 4. removing the coupon restores the original total
    await page.getByTestId("remove-coupon").click();
    await expect(page.getByTestId("coupon-input")).toBeVisible();
    expect(await amount(page, "summary-total")).toBeCloseTo(original, 2);
  });

  test("coupon below its minimum cart value is refused with the reason", async ({ page }) => {
    await signInWithEmptyCart(page, "customer");
    await addSkuToCart(page, "USB-C Charge", "LU-USBC-1M", 1); // 9 € net, minimum is 50 €
    await page.goto("/cart");
    await page.getByTestId("coupon-input").fill("FIIT5");
    await page.getByTestId("apply-coupon").click();
    // Attaching passes the cheap checks; pricing reports the unmet minimum.
    await expect(
      page.getByTestId("coupon-error").or(page.getByTestId("error-message"))
    ).toContainText(/at least|minimum/i);
  });

  test("category-restricted coupon only discounts matching items", async ({ page }) => {
    await signInWithEmptyCart(page, "customer");
    await addSkuToCart(page, "AirLite", "VAL13-8-256", 1); // Laptops → eligible
    await page.goto("/cart");
    await page.getByTestId("coupon-input").fill("LAPTOP50");
    await page.getByTestId("apply-coupon").click();
    await expect(page.getByTestId("coupon-applied")).toBeVisible();
    expect(await amount(page, "summary-discount")).toBeCloseTo(50, 2);

    await addSkuToCart(page, "HDMI", "LU-HDMI21-2M", 1); // Cables → not eligible
    await page.goto("/cart");
    // The discount is still exactly 50 € — the cable line is not discounted.
    expect(await amount(page, "summary-discount")).toBeCloseTo(50, 2);
  });
});
