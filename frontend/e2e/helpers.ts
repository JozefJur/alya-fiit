/** Shared E2E helpers: sign-in, cart setup, money parsing. */

import { expect, type Page } from "@playwright/test";

export const ACCOUNTS = {
  customer: { email: "customer1@alya.test", password: "Customer123!", demo: "demo-customer" },
  customer2: { email: "customer2@alya.test", password: "Customer123!", demo: null },
  warehouse: { email: "warehouse@alya.test", password: "Warehouse123!", demo: "demo-warehouse" },
  support: { email: "support@alya.test", password: "Support123!", demo: "demo-support" },
  admin: { email: "admin@alya.test", password: "Admin123!", demo: "demo-administrator" },
} as const;

export type AccountName = keyof typeof ACCOUNTS;

export const ADDRESS = {
  name: "Cyril Zákazník",
  street: "Ilkovičova 2",
  city: "Bratislava",
  zip: "84216",
};

/** Sign in through the real login form and wait until the session is active. */
export async function signIn(page: Page, account: AccountName): Promise<void> {
  const { email, password } = ACCOUNTS[account];
  await page.goto("/login");
  await page.getByTestId("login-email").fill(email);
  await page.getByTestId("login-password").fill(password);
  await page.getByTestId("login-submit").click();
  await expect(page.getByTestId("current-user")).toBeVisible();
}

export async function signOut(page: Page): Promise<void> {
  await page.getByTestId("logout-button").click();
  await expect(page.getByTestId("login-form")).toBeVisible();
}

/**
 * Empty the signed-in customer's cart (and with it any applied coupon).
 *
 * The suite shares one seeded database, so every test that touches the cart
 * starts by resetting it — that is what keeps the scenarios independent of
 * execution order.
 */
export async function resetCart(page: Page): Promise<void> {
  await page.goto("/cart");
  // Wait for the cart to actually render before deciding whether to clear it —
  // the page shows a spinner while the request is in flight.
  await expect(
    page.getByTestId("cart-summary").or(page.getByTestId("empty-state"))
  ).toBeVisible();
  const clear = page.getByTestId("clear-cart");
  if ((await clear.count()) > 0) {
    await clear.click();
    await expect(page.getByTestId("empty-state")).toBeVisible();
  }
}

/** Sign in as a customer with a guaranteed-empty cart. */
export async function signInWithEmptyCart(page: Page, account: AccountName): Promise<void> {
  await signIn(page, account);
  await resetCart(page);
}

/** "219.19 €" → 219.19 */
export function euros(text: string): number {
  const match = /-?\d+(\.\d+)?/.exec(text.replace(/\s/g, ""));
  if (!match) throw new Error(`no amount found in "${text}"`);
  return Number(match[0]);
}

export async function amount(page: Page, testId: string): Promise<number> {
  return euros(await page.getByTestId(testId).innerText());
}

/** Open a product's detail page by its catalog search term. */
export async function openProduct(page: Page, searchTerm: string): Promise<void> {
  await page.goto("/");
  await page.getByTestId("search-input").fill(searchTerm);
  await page.getByTestId("search-submit").click();
  await expect(page.getByTestId("product-grid")).toBeVisible();
  await page.locator('[data-testid^="product-card-"]').first().click();
  await expect(page.getByTestId("product-name")).toBeVisible();
}

/** Add a specific SKU to the cart from its product page. */
export async function addSkuToCart(
  page: Page,
  searchTerm: string,
  sku: string,
  quantity = 1
): Promise<void> {
  await openProduct(page, searchTerm);
  await page.getByTestId(`variant-${sku}`).click();
  await page.getByTestId("quantity-input").fill(String(quantity));
  await page.getByTestId("add-to-cart").click();
  await expect(page.getByTestId("info-message")).toBeVisible();
}

/** Fill the checkout address form. */
export async function fillAddress(page: Page): Promise<void> {
  await page.getByTestId("address-name").fill(ADDRESS.name);
  await page.getByTestId("address-street").fill(ADDRESS.street);
  await page.getByTestId("address-city").fill(ADDRESS.city);
  await page.getByTestId("address-zip").fill(ADDRESS.zip);
}

/** Run checkout from the cart page with the chosen simulated payment outcome. */
export async function checkout(
  page: Page,
  outcome: "success" | "declined" | "timeout" = "success"
): Promise<void> {
  await page.goto("/cart");
  await page.getByTestId("go-checkout").click();
  await expect(page.getByTestId("place-order")).toBeVisible();
  await fillAddress(page);
  await page.getByTestId(`pay-${outcome}`).click();
  await page.getByTestId("place-order").click();
}

/** Availability shown on a product page for one SKU. */
export async function availabilityOf(
  page: Page,
  searchTerm: string,
  sku: string
): Promise<number> {
  await openProduct(page, searchTerm);
  const text = await page.getByTestId(`stock-${sku}`).innerText();
  if (/out of stock/i.test(text)) return 0;
  return Number(/\d+/.exec(text)?.[0] ?? "0");
}
