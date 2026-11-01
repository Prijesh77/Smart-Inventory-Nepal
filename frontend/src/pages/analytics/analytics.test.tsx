import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { mockFetch } from "../../test/fetchMock";
import { meRoute, renderLoggedIn } from "../../test/renderWithAuth";
import { AnalyticsPage } from "./AnalyticsPage";
import { pivotWeekly } from "./CategorySection";

const SLOW = {
  as_of: "2026-10-31", days: 60, total_value: 1650, products_without_cost: 1,
  items: [
    { product_id: 7, sku: "GHEE-500ML", name: "Cow ghee 500 ml", category: "Oil, ghee & spices", on_hand: 3, unit_cost: 550,
      stock_value: 1650, last_sold: "2026-07-20", days_since_sale: 103 },
    { product_id: 9, sku: "DIYO-12", name: "Clay diyo", category: "Household & puja", on_hand: 40, unit_cost: null,
      stock_value: null, last_sold: null, days_since_sale: null },
  ],
};

function routes(role: "manager" | "viewer" = "manager", extra = {}) {
  return {
    ...meRoute(role),
    "GET /analytics/categories": () => ({ body: [{ category: "FOODS", name: "Foods", products: 115, units_sold: 7955,
      revenue: 24576.63, avg_daily_units: 284.1, units_on_hand: 8800, inventory_value: 12000, days_of_cover: 31.0 }] }),
    "GET /analytics/weekly-trend": () => ({ body: [
      { week_start: "2016-05-09", category: "FOODS", units: 2000 }, { week_start: "2016-05-16", category: "FOODS", units: 1900 },
      { week_start: "2016-05-16", category: "HOBBIES", units: 700 }, { week_start: "2016-05-23", category: "FOODS", units: 50 }] }),
    "GET /forecasts/evaluations": () => ({ body: [] }),
    "GET /analytics/slow-movers": (url: string) => ({ body: url.includes("days=90") ? { ...SLOW, days: 90, items: [], total_value: 0 } : SLOW }),
    ...extra,
  };
}

describe("helpers", () => {
  it("pivots weekly points into one row per week", () => {
    const { rows, categories } = pivotWeekly([
      { week_start: "2016-05-16", category: "HOBBIES", units: 7 }, { week_start: "2016-05-09", category: "FOODS", units: 2 },
      { week_start: "2016-05-16", category: "FOODS", units: 3 }]);
    expect(categories).toEqual(["FOODS", "HOBBIES"]);
    expect(rows).toEqual([{ week_start: "2016-05-09", FOODS: 2 }, { week_start: "2016-05-16", FOODS: 3, HOBBIES: 7 }]);
  });
});

describe("AnalyticsPage", () => {
  it("shows category performance", async () => {
    mockFetch(routes());
    renderLoggedIn(<AnalyticsPage />, "/analytics");
    const foods = (await screen.findByRole("rowheader", { name: "Foods" })).closest("tr")!;
    expect(within(foods).getByText("7,955")).toBeInTheDocument();
    expect(within(foods).getByText("31 d")).toBeInTheDocument();
  });

  it("lists slow-moving stock with the money tied up in it", async () => {
    const { calls } = mockFetch(routes("viewer"));
    renderLoggedIn(<AnalyticsPage />, "/analytics");
    const ghee = (await screen.findByRole("link", { name: "GHEE-500ML" })).closest("tr")!;
    expect(within(ghee).getByText("Rs 1,650.00")).toBeInTheDocument();
    expect(within(ghee).getByText("20 Jul 2026 (103 days ago)")).toBeInTheDocument();
    expect(screen.getByText("Never in the data")).toBeInTheDocument();
    expect(screen.getByText(/1 without a cost are not counted/)).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("No sale for"), "90");
    expect(await screen.findByText("Everything in stock has sold in the last 90 days")).toBeInTheDocument();
    expect(calls.some((c) => c.url.includes("/analytics/slow-movers?days=90"))).toBe(true);
  });

  it("downloads a CSV report with the login token", async () => {
    const { calls } = mockFetch(routes("viewer", { "GET /exports/products.csv": () => ({ body: "sku,name" }) }));
    const createUrl = vi.fn(() => "blob:test");
    vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: createUrl, revokeObjectURL: vi.fn() }));
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    renderLoggedIn(<AnalyticsPage />, "/analytics");
    await userEvent.click(await screen.findByRole("button", { name: "⬇ Products" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Downloaded products.csv");
    const request = calls.find((c) => c.url.includes("/exports/products.csv"))!;
    expect((request.init?.headers as Record<string, string>).Authorization).toBe("Bearer test-token");
    expect(click).toHaveBeenCalled();
  });
});
