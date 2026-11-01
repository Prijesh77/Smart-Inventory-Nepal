/**
 * Captures screenshots of every page for the README and report:  npm run screenshots
 *
 * Runs against the separate <main database>_e2e database (the synthetic demo shop), creates real
 * forecast, recommendation and order runs through the UI, and saves
 * full-page PNGs to docs/screenshots/. Tagged @screenshots so `npm run e2e` skips it.
 */
import { expect, test, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";

const OUT = "../docs/screenshots";

/** An AD date `days` before yesterday (the demo's last sales day), "YYYY-MM-DD". */
function adDaysAgo(days: number): string {
  const day = new Date();
  day.setDate(day.getDate() - 1 - days);
  return `${day.getFullYear()}-${String(day.getMonth() + 1).padStart(2, "0")}-${String(day.getDate()).padStart(2, "0")}`;
}
const creds = () => JSON.parse(readFileSync(new URL("./.credentials.json", import.meta.url), "utf-8")).admin as
  { email: string; password: string };

test.use({ viewport: { width: 1440, height: 900 } });

async function shot(page: Page, name: string, fullPage = true) {
  await page.waitForLoadState("networkidle");
  await page.evaluate(() => window.scrollTo(0, 0));  // sticky header and sidebar sit in place
  await page.waitForTimeout(400);                    // let charts finish drawing
  await page.screenshot({ path: `${OUT}/${name}.png`, fullPage });
}

test("capture every page @screenshots", async ({ page }) => {
  test.setTimeout(600_000);

  await page.goto("/login");
  await shot(page, "00_login", false);
  await page.getByLabel("Email").fill(creds().email);
  await page.getByLabel("Password").fill(creds().password);
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();

  // Overview after a real forecast + recommendation run
  await page.getByRole("button", { name: "Run forecast & recommendations" }).click();
  await expect(page.getByRole("group", { name: "Products to reorder" }).getByText(/Estimated order cost/))
    .toBeVisible({ timeout: 240_000 });
  await shot(page, "01_overview");

  // The fastest-selling sampled product makes the clearest sales and forecast charts.
  await page.goto("/inventory");
  await page.getByRole("button", { name: /Sales \/ day/ }).click();
  await page.getByRole("button", { name: /Sales \/ day/ }).click();          // descending
  await expect(page.getByRole("columnheader", { name: /Sales \/ day/ })).toHaveAttribute("aria-sort", "descending");
  const sku = (await page.locator("tbody tr a").first().innerText()).trim();

  // Products and that product's detail
  await page.goto("/products");
  await expect(page.locator("tbody tr").first()).toBeVisible();
  await shot(page, "02_products", false);
  await page.goto(`/products?search=${sku}`);
  await page.getByRole("link", { name: sku }).click();
  await expect(page.getByRole("img", { name: /Daily units sold/ })).toBeVisible();
  const productId = page.url().split("/").pop()!;
  await shot(page, "03_product_detail");

  // Inventory: stock levels and alerts
  await page.goto("/inventory");
  await expect(page.locator("tbody tr").first()).toBeVisible();
  await shot(page, "04_inventory", false);
  await page.goto("/inventory?tab=alerts");
  await expect(page.getByText(/will not last until a new order/)).toBeVisible();
  await shot(page, "05_inventory_alerts");

  // Forecasting: a forecast started 4 weeks back, so actual sales can be compared with it. The date is
  // typed with the AD date picker, then the page goes back to BS for the screenshot.
  await page.goto(`/forecasts?product=${productId}`);
  await page.getByLabel("Show dates as").selectOption("ad");
  await page.getByLabel("Start date (optional)").fill(adDaysAgo(28));
  await page.getByRole("button", { name: "Create forecast" }).click();
  await expect(page.getByText(/Error on this window/).locator("..")).not.toContainText("Not known yet", { timeout: 120_000 });
  await page.getByLabel("Show dates as").selectOption("bs");
  await shot(page, "06_forecasting");

  // Reorder recommendations: critical items with one explanation open
  await page.goto("/recommendations?risk=critical_stockout_risk");
  await expect(page.locator("tbody tr").first()).toBeVisible();
  await page.getByRole("button", { name: "Why?" }).first().click();
  await shot(page, "07_recommendations");

  // Approve the critical items, create draft orders, submit one and receive part of it
  // Approving removes that row's button, so always click the first one still there.
  const approve = page.getByRole("button", { name: /^Approve / });
  for (let i = 0; i < 10 && (await approve.count()) > 0; i++) {
    const before = await approve.count();
    await approve.first().click();
    await expect(approve).toHaveCount(before - 1);
  }
  await page.getByRole("button", { name: "Create draft orders from approved" }).click();
  await expect(page.getByRole("status")).toContainText("draft purchase order");
  await page.getByRole("status").getByRole("link").first().click();
  await page.getByRole("button", { name: "Submit order" }).click();
  await expect(page.getByRole("status")).toContainText("submitted");
  await page.getByRole("button", { name: "Receive delivery" }).click();
  const firstQty = page.getByRole("dialog").getByLabel(/Received now for/).first();
  const full = Number(await firstQty.inputValue());
  await firstQty.fill(String(Math.max(1, Math.floor(full / 2))));
  await page.getByRole("dialog").getByRole("button", { name: "Book delivery" }).click();
  await expect(page.getByRole("status")).toContainText(/delivery booked/i);
  await shot(page, "08_purchase_order");
  await page.goto("/purchase-orders");
  await shot(page, "09_purchase_orders", false);

  // Analytics: category performance and slow-moving stock
  await page.goto("/analytics");
  await expect(page.getByRole("heading", { name: "Slow-moving stock" })).toBeVisible();
  await shot(page, "10_analytics");

  // Settings: a CSV with mistakes shows row-by-row errors
  await page.goto("/settings");
  await page.getByRole("button", { name: "4. Sales history" }).click();
  await page.getByLabel(/Excel or CSV file/).setInputFiles({
    name: "sales.csv", mimeType: "text/csv",
    buffer: Buffer.from("sku,date,units\nNOODLES-70G,2083-07-14,40\nNOODLES-70G,23/05/2026,4\nNOT_A_SKU,2083-07-14,1\n"),
  });
  await page.getByRole("button", { name: "Check file" }).click();
  await expect(page.getByRole("alert")).toBeVisible();
  await shot(page, "11_settings_import");
});
