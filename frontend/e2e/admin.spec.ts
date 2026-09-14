/**
 * E2E-09  Administrator edits a product and stock  (BG-06, AC-06.x)
 * E2E-10  Administrator opens the report (long)    (BG-06, AC-06.1/2/3)
 */

import { expect, test } from "@playwright/test";

import { addSkuToCart, checkout, signIn, signInWithEmptyCart } from "./helpers";

test.describe("E2E-09 administrator maintains the catalog and stock", () => {
  test("price change is visible in the catalog and stock changes are audited", async ({ page }) => {
    await signIn(page, "admin");

    // 1. find the product in the admin listing
    await page.goto("/admin/products");
    await page.getByTestId("admin-search").fill("Ergo Trackball");
    await page.getByTestId("admin-search").press("Enter");
    const row = page.locator('[data-testid^="admin-product-"]').first();
    await expect(row).toContainText("Voltex Ergo Trackball");
    const productId = (await row.getAttribute("data-testid"))?.replace("admin-product-", "");

    // 2. change the net price
    await page.getByTestId(`price-input-${productId}`).fill("81.00");
    await page.getByTestId(`price-save-${productId}`).click();
    await expect(page.getByTestId("info-message")).toContainText("Price updated");

    // 3. the customer-facing catalog shows the new gross price (81 + 23 % VAT)
    await page.goto("/");
    await page.getByTestId("search-input").fill("Ergo Trackball");
    await page.getByTestId("search-submit").click();
    await expect(page.getByTestId("product-grid")).toContainText("99.63");

    // 4. adjust the stock with a reason
    await page.goto("/warehouse/inventory");
    await page.getByTestId("inventory-filter").fill("VET-TB");
    const availableBefore = Number(await page.getByTestId("available-VET-TB").innerText());
    await page.getByTestId("adjust-VET-TB").click();
    await page.getByTestId("adjust-change").fill("7");
    await page.getByTestId("adjust-reason").fill("Delivery from supplier");
    await page.getByTestId("adjust-submit").click();
    await expect(page.getByTestId("available-VET-TB")).toHaveText(String(availableBefore + 7));

    // 5. the adjustment is in the audit log with its reason
    await page.goto("/admin/audit");
    await expect(page.getByTestId("audit-table")).toContainText("stock.adjusted");
    await expect(page.getByTestId("audit-table")).toContainText("Delivery from supplier");
  });

  test("an adjustment without a reason is refused", async ({ page }) => {
    await signIn(page, "admin");
    await page.goto("/warehouse/inventory");
    await page.getByTestId("inventory-filter").fill("LU-HUB8");
    await page.getByTestId("adjust-LU-HUB8").click();
    await page.getByTestId("adjust-change").fill("5");
    await page.getByTestId("adjust-submit").click();
    await expect(page.getByTestId("error-message")).toContainText(/reason is required/i);
  });

  test("deactivating a product removes it from the customer catalog", async ({ page }) => {
    await signIn(page, "admin");
    await page.goto("/admin/products");
    await page.getByTestId("admin-search").fill("32 Curved");
    await page.getByTestId("admin-search").press("Enter");
    const row = page.locator('[data-testid^="admin-product-"]').first();
    // Wait for the filtered list before reading the row — otherwise the id
    // belongs to a product that is about to be replaced by the new results.
    await expect(row).toContainText("PixelForge 32 Curved");
    const productId = (await row.getAttribute("data-testid"))?.replace("admin-product-", "");
    await page.getByTestId(`toggle-active-${productId}`).click();
    await expect(page.getByTestId("info-message")).toContainText("deactivated");

    await page.goto("/");
    await page.getByTestId("search-input").fill("32 Curved");
    await page.getByTestId("search-submit").click();
    await expect(page.getByTestId("empty-state")).toBeVisible();

    // restore it so later tests see the full catalog
    await page.goto("/admin/products");
    await page.getByTestId("admin-search").fill("32 Curved");
    await page.getByTestId("admin-search").press("Enter");
    await expect(row).toContainText("PixelForge 32 Curved");
    await page.getByTestId(`toggle-active-${productId}`).click();
    await expect(page.getByTestId("info-message")).toContainText("activated");
  });

  test("a new coupon can be created and immediately used", async ({ page }) => {
    await signIn(page, "admin");
    await page.goto("/admin/coupons");
    await page.getByTestId("coupon-code").fill("E2ETEST");
    await page.getByTestId("coupon-type").selectOption("fixed");
    await page.getByTestId("coupon-value").fill("3.00");
    await page.getByTestId("coupon-save").click();
    await expect(page.getByTestId("coupon-row-E2ETEST")).toBeVisible();

    await page.getByTestId("logout-button").click();
    await signInWithEmptyCart(page, "customer");
    await addSkuToCart(page, "HDMI", "LU-HDMI21-2M", 1);
    await page.goto("/cart");
    await page.getByTestId("coupon-input").fill("e2etest"); // codes are case-insensitive
    await page.getByTestId("apply-coupon").click();
    await expect(page.getByTestId("coupon-applied")).toContainText("E2ETEST");
    await expect(page.getByTestId("summary-discount")).toContainText("3.00");
  });
});

test.describe("E2E-10 inventory and sales report", () => {
  test("the report reconciles with the orders behind it and exports to CSV", async ({ page }) => {
    // 1. create a fresh paid order so the report has something to show
    await signInWithEmptyCart(page, "customer");
    await addSkuToCart(page, "Quiet 700", "ASQ700-BLK", 1);
    await checkout(page, "success");
    await expect(page.getByTestId("order-confirmation")).toBeVisible();
    const orderTotal = await page.getByTestId("order-total").innerText();

    // 2. open the report as the administrator
    await page.getByTestId("logout-button").click();
    await signIn(page, "admin");
    await page.goto("/admin/report");
    await expect(page.getByTestId("report-summary")).toBeVisible();

    // 3. the period covers today, so the new order is included
    const revenue = Number(
      (await page.getByTestId("summary-revenue").innerText()).replace(/[^\d.]/g, "")
    );
    expect(revenue).toBeGreaterThanOrEqual(Number(orderTotal.replace(/[^\d.]/g, "")));

    // 4. the sold variant appears with its quantity
    await expect(page.getByTestId("report-variants")).toContainText("ASQ700-BLK");

    // 5. top products and low stock lists are populated
    await expect(page.getByTestId("top-products")).toContainText("AeroSound Quiet 700");
    await expect(page.getByTestId("low-stock")).toBeVisible();

    // 6. filtering by category narrows the table
    await page.getByTestId("report-category").selectOption({ label: "Headphones" });
    await page.getByTestId("report-run").click();
    await expect(page.getByTestId("report-variants")).toContainText("ASQ700-BLK");
    await expect(page.getByTestId("report-variants")).not.toContainText("LU-HUB8");

    // 7. an empty period reports no revenue
    await page.getByTestId("report-category").selectOption("");
    await page.getByTestId("report-from").fill("2020-01-01");
    await page.getByTestId("report-to").fill("2020-01-31");
    await page.getByTestId("report-run").click();
    await expect(page.getByTestId("summary-revenue")).toHaveText("0.00 €");

    // 8. the CSV export downloads with the report data
    await page.getByTestId("report-from").fill("2020-01-01");
    await page.getByTestId("report-to").fill("2035-12-31");
    await page.getByTestId("report-run").click();
    await expect(page.getByTestId("report-summary")).toBeVisible();
    const download = page.waitForEvent("download");
    await page.getByTestId("report-csv").click();
    const file = await download;
    expect(file.suggestedFilename()).toContain("inventory-sales");
  });

  test("only administrators can open the report", async ({ page }) => {
    await signIn(page, "warehouse");
    await page.goto("/admin/report");
    await expect(page.getByTestId("forbidden")).toBeVisible();

    await page.getByTestId("logout-button").click();
    await signIn(page, "support");
    await page.goto("/admin/report");
    await expect(page.getByTestId("forbidden")).toBeVisible();
  });

  test("the notification outbox records what would have been e-mailed", async ({ page }) => {
    await signInWithEmptyCart(page, "customer");
    await addSkuToCart(page, "Charge Cable", "LU-USBC-1M", 1);
    await checkout(page, "success");
    await expect(page.getByTestId("order-confirmation")).toBeVisible();
    const orderNumber = await page.getByTestId("order-number").innerText();

    await page.getByTestId("logout-button").click();
    await signIn(page, "admin");
    await page.goto("/admin/audit");
    await page.getByTestId("tab-outbox").click();
    await expect(page.getByTestId("outbox-table")).toContainText(orderNumber);
    await expect(page.getByTestId("outbox-table")).toContainText("payment_confirmed");
  });
});
