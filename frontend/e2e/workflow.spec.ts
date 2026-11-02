/**
 * Browser end-to-end test of the whole system: real Edge browser -> real frontend
 * -> real API -> real PostgreSQL (the separate <main database>_e2e database, freshly
 * loaded by e2e_setup.py with the synthetic demo shop of 43 products, plus a second
 * shop that must never see the demo shop's data).
 */
import { expect, test, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";

type Role = "admin" | "manager" | "viewer" | "other_shop";
type Account = { email: string; password: string };
let cached: Record<Role, Account> | null = null;

/** Test accounts written by e2e_setup.py (fresh random passwords each run). */
const accounts = new Proxy({} as Record<Role, Account>, {
  get(_target, role: Role) {
    if (!cached) {
      try {
        cached = JSON.parse(readFileSync(new URL("./.credentials.json", import.meta.url), "utf-8"));
      } catch {
        throw new Error("e2e/.credentials.json is missing: run `npm run e2e` (it prepares the test database first)");
      }
    }
    return cached![role];
  },
});

async function login(page: Page, role: Role) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(accounts[role].email);
  await page.getByLabel("Password").fill(accounts[role].password);
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
}

test.describe.configure({ mode: "serial" });

test("rejects a wrong password and protects pages", async ({ page }) => {
  await page.goto("/inventory");
  await expect(page).toHaveURL(/\/login$/);
  await page.getByLabel("Email").fill(accounts.manager.email);
  await page.getByLabel("Password").fill("definitely-wrong");
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page.getByRole("alert")).toContainText("Incorrect email or password");
});

test("manager: forecast -> recommendations -> approve -> order -> receive -> stock updated", async ({ page }) => {
  test.setTimeout(240_000);
  await login(page, "manager");
  await expect(page.getByText("43", { exact: true }).first()).toBeVisible();       // the demo shop's products
  await expect(page.getByRole("region", { name: "Shop" })).toContainText("Demo Kirana Pasal");
  await expect(page.getByText("No recommendations yet").first()).toBeVisible();

  // 1. Forecast and recommendations from the overview (background jobs)
  await page.getByRole("button", { name: "Run forecast & recommendations" }).click();
  const toReorder = page.getByRole("group", { name: "Products to reorder" });
  await expect(toReorder.getByText(/Estimated order cost/)).toBeVisible({ timeout: 180_000 });
  const reorderCount = Number((await toReorder.getByTestId("stat-value").innerText()).replace(/,/g, ""));
  expect(reorderCount).toBeGreaterThan(0);

  // 2. Reorder page: most urgent first, read the explanation, approve it
  await nav(page, "Reorder");
  await page.getByLabel("Only items to order").check();
  const firstRow = page.locator("tbody tr").first();
  const sku = (await firstRow.locator("a").first().innerText()).trim();
  await firstRow.getByRole("button", { name: "Why?" }).click();
  await expect(page.getByText(/Inventory position is/).first()).toBeVisible();
  await page.getByRole("button", { name: `Approve ${sku}` }).click();
  await expect(firstRow.getByText("Approved")).toBeVisible();

  // 3. Draft order from the approved item
  await page.getByRole("button", { name: "Create draft orders from approved" }).click();
  await expect(page.getByRole("status")).toContainText("Nothing has been sent to any supplier");
  await page.getByRole("status").getByRole("link").first().click();
  await expect(page.getByText("Draft", { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: sku })).toBeVisible();       // the approved item is on this order
  const orderUrl = page.url();
  const ordered = Number(await page.locator("tfoot td").nth(1).innerText());

  // 4. Stock before receiving
  const stockBefore = await onHand(page, sku);

  // 5. Submit and receive the full delivery
  await page.goto(orderUrl);
  await page.getByRole("button", { name: "Submit order" }).click();
  await expect(page.getByRole("status")).toContainText("Nothing was sent to the supplier");
  await page.getByRole("button", { name: "Receive delivery" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Book delivery" }).click();
  await expect(page.getByRole("status")).toContainText("fully received");

  // 6. Stock went up by exactly the ordered amount, with an audit record by this user
  expect(await onHand(page, sku)).toBe(stockBefore + ordered);
  await page.getByRole("button", { name: `Movements for ${sku}` }).click();
  const receipt = page.locator("tbody tr", { hasText: "Receipt" }).first();
  await expect(receipt).toContainText(`+${ordered}`);
  await expect(receipt).toContainText(accounts.manager.email);
});

test("manager: stock adjustment needs a reason and is logged", async ({ page }) => {
  await login(page, "manager");
  await nav(page, "Inventory");
  const row = page.locator("tbody tr").first();
  const sku = (await row.locator("a").first().innerText()).trim();
  await page.getByRole("button", { name: `Adjust stock for ${sku}` }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Units").fill("1");
  await dialog.getByRole("button", { name: "Record movement" }).click();
  await expect(dialog.getByText(/Explain the change/)).toBeVisible();
  await dialog.getByLabel("Reason").fill("E2E test: damaged item");
  await dialog.getByRole("button", { name: "Record movement" }).click();
  await expect(page.getByRole("status")).toContainText(`${sku} -1 (adjustment)`);
});

test("manager: an invalid sales file is rejected with row errors", async ({ page }) => {
  await login(page, "manager");
  await nav(page, "Settings & import");
  await page.getByRole("button", { name: "4. Sales history" }).click();
  await page.getByLabel(/Excel or CSV file/).setInputFiles({
    name: "bad.csv", mimeType: "text/csv",
    buffer: Buffer.from("sku,date,units\nNOODLES-70G,23/05/2026,4\nNOT_A_SKU,2083-07-01,1\nNOODLES-70G,2083-07-31,2\n"),
  });
  await page.getByRole("button", { name: "Check file" }).click();
  const alert = page.getByRole("alert");
  await expect(alert).toContainText("Nothing will be imported");
  await expect(alert).toContainText("is not YYYY-MM-DD");
  await expect(alert).toContainText("Unknown SKU 'NOT_A_SKU'");
  await expect(alert).toContainText("not a real BS date");                       // Kartik 2083 has 30 days
  await expect(page.getByRole("button", { name: /^Import \d+ rows/ })).toHaveCount(0);
});

test("viewer: can read everything but change nothing", async ({ page }) => {
  await login(page, "viewer");
  await expect(page.getByRole("button", { name: "Run forecast & recommendations" })).toHaveCount(0);
  await nav(page, "Reorder");
  await expect(page.locator("tbody tr").first()).toBeVisible();
  await expect(page.getByRole("button", { name: /^Approve / })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /Create draft orders/ })).toHaveCount(0);
  await nav(page, "Products");
  await expect(page.getByRole("button", { name: "Add product" })).toHaveCount(0);
  await nav(page, "Settings & import");
  await expect(page.getByText("Only managers and admins can import data.")).toBeVisible();
});

test("another shop sees only its own data", async ({ page }) => {
  await login(page, "other_shop");
  await expect(page.getByRole("region", { name: "Shop" })).toContainText("E2E Second Shop");
  await nav(page, "Products");
  await expect(page.getByRole("link", { name: "ONLY-IN-SHOP-B" })).toBeVisible();
  await expect(page.getByRole("link", { name: "NOODLES-70G" })).toHaveCount(0);     // a demo-shop product
  await nav(page, "Purchase orders");
  await expect(page.getByText("No purchase orders yet")).toBeVisible();            // the demo shop's order is not here
  // Opening a demo-shop product by its address is refused, not shown.
  await page.goto("/products/1");
  await expect(page.getByRole("alert")).toContainText(/not found/i);
});

/** Click a page in the sidebar menu (exact name: the Overview cards are links too, e.g. "Products to reorder"). */
async function nav(page: Page, label: string) {
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: label, exact: true }).click();
}

/** On-hand stock for one SKU, read from the Inventory page. */
async function onHand(page: Page, sku: string): Promise<number> {
  await page.goto(`/inventory?search=${encodeURIComponent(sku)}`);
  const row = page.locator("tbody tr", { hasText: sku }).first();
  await expect(row).toBeVisible();
  return Number((await row.locator("td").nth(2).innerText()).replace(/,/g, ""));
}
