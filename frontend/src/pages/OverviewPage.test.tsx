import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { DashboardSummary } from "../api/types";
import { withRollingAverage } from "../components/charts/SalesTrendChart";
import { mockFetch, TEST_USER } from "../test/fetchMock";
import { meRoute, renderLoggedIn } from "../test/renderWithAuth";
import { OverviewPage } from "./OverviewPage";

const EMPTY: DashboardSummary = {
  as_of: "2016-05-22",
  active_products: 267,
  units_on_hand: 15368,
  inventory_value: 30235.04,
  products_without_cost: 0,
  stock_status: { ok: 252, low: 4, out_of_stock: 1, no_recent_demand: 10 },
  sales: {
    last_28_days_units: 14103, last_28_days_revenue: 44687.3, change_vs_previous_28_days: -0.0004,
    daily_trend: [{ date: "2016-05-21", units: 520, revenue: 1600 }, { date: "2016-05-22", units: 610, revenue: 1900 }],
  },
  recommendations: null,
  forecast: null,
  purchase_orders: { open: 0, open_order_value: 0, drafts: 0 },
  recent_activity: [{ id: 1, product_id: 13, sku: "FOODS_1_013", txn_type: "initial", quantity: 93, balance_after: 93,
    reason: "Opening balance", purchase_order_id: null, created_by_email: null, created_at: "2026-10-29T10:00:00Z" }],
  simulated_fields: ["inventory_value"],
};

const WITH_RUNS: DashboardSummary = {
  ...EMPTY,
  recommendations: { run_id: 3, created_at: "2026-10-29T12:00:00Z", products_to_reorder: 53, critical: 5, excess: 39,
    estimated_order_cost: 8216.03, counts: { critical_stockout_risk: 5, reorder_soon: 48, healthy: 175, excess_inventory: 39 } },
  forecast: { run_id: 2, model_name: "random_forest_v1", origin_date: "2016-05-23", horizon_days: 28,
    predicted_units: { next_7_days: 3500, next_14_days: 7000, next_28_days: 14144 } },
};

function card(label: string) {
  return screen.getByRole("group", { name: label });
}

describe("OverviewPage", () => {
  it("labels made-up figures as simulated only in a demo shop", async () => {
    const demoUser = { ...TEST_USER, shop: { id: 2, name: "Demo Kirana Pasal (synthetic data)", is_demo: true } };
    mockFetch({ "GET /auth/me": () => ({ body: demoUser }), "GET /dashboard/summary": () => ({ body: EMPTY }) });
    renderLoggedIn(<OverviewPage />);
    expect(await screen.findByText("267")).toBeInTheDocument();
    expect(await within(card("Inventory value (at cost)")).findByText("Simulated")).toBeInTheDocument();
  });

  it("shows live figures and says when nothing has been run yet", async () => {
    mockFetch({ ...meRoute("manager"), "GET /dashboard/summary": () => ({ body: EMPTY }) });
    renderLoggedIn(<OverviewPage />);
    expect(await screen.findByText("267")).toBeInTheDocument();
    expect(within(card("Inventory value (at cost)")).getByText("Rs 30,235.04")).toBeInTheDocument();
    expect(within(card("Inventory value (at cost)")).queryByText("Simulated")).toBeNull();   // a real shop's own figures
    expect(within(card("Units sold, last 28 days")).getByText("14,103")).toBeInTheDocument();
    expect(within(card("Products to reorder")).getByText("No recommendations yet")).toBeInTheDocument();
    expect(within(card("Low or out of stock")).getByText("5")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /Products by stock status: Out of stock 1, Low 4, OK 252/ })).toBeInTheDocument();
    expect(screen.getByText("FOODS_1_013")).toBeInTheDocument();
    expect(screen.getByText("System (setup)")).toBeInTheDocument();
  });

  it("shows recommendation and forecast results when they exist", async () => {
    mockFetch({ ...meRoute("viewer"), "GET /dashboard/summary": () => ({ body: WITH_RUNS }) });
    renderLoggedIn(<OverviewPage />);
    expect(await screen.findByText("53")).toBeInTheDocument();
    expect(within(card("Critical stockout risk")).getByText("5")).toBeInTheDocument();
    expect(within(card("Forecast, next 28 days")).getByText("14,144")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /Products by reorder risk: Critical stockout risk 5, Reorder soon 48/ }))
      .toBeInTheDocument();
  });

  it("hides the planning button from viewers", async () => {
    mockFetch({ ...meRoute("viewer"), "GET /dashboard/summary": () => ({ body: EMPTY }) });
    renderLoggedIn(<OverviewPage />);
    await screen.findByText("267");
    expect(screen.queryByRole("button", { name: /Run forecast/ })).not.toBeInTheDocument();
  });

  it("runs forecast then recommendations, then reloads the figures", async () => {
    let summary = EMPTY;
    const { calls } = mockFetch({
      ...meRoute("manager"),
      "GET /dashboard/summary": () => ({ body: summary }),
      "POST /forecasts/runs": () => ({ status: 202, body: { id: 2, status: "pending", error_message: null } }),
      "GET /forecasts/runs/2": () => ({ body: { id: 2, status: "completed", error_message: null } }),
      "POST /recommendations/runs": () => {
        summary = WITH_RUNS;
        return { status: 202, body: { id: 3, status: "pending", error_message: null } };
      },
      "GET /recommendations/runs/3": () => ({ body: { id: 3, status: "completed", error_message: null } }),
    });
    renderLoggedIn(<OverviewPage pollMs={0} />);
    await userEvent.click(await screen.findByRole("button", { name: "Run forecast & recommendations" }));
    expect(await screen.findByText("53")).toBeInTheDocument();
    const recBody = calls.find((c) => c.url.endsWith("/recommendations/runs"))?.init?.body;
    expect(JSON.parse(String(recBody))).toEqual({ forecast_run_id: 2 });
  });

  it("shows a failed run's reason", async () => {
    mockFetch({
      ...meRoute("manager"),
      "GET /dashboard/summary": () => ({ body: EMPTY }),
      "POST /forecasts/runs": () => ({ status: 202, body: { id: 9, status: "pending", error_message: null } }),
      "GET /forecasts/runs/9": () => ({ body: { id: 9, status: "failed", error_message: "Model file not found" } }),
    });
    renderLoggedIn(<OverviewPage pollMs={0} />);
    await userEvent.click(await screen.findByRole("button", { name: "Run forecast & recommendations" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Model file not found");
  });

  it("shows an error with retry when the summary cannot load", async () => {
    mockFetch({ ...meRoute(), "GET /dashboard/summary": () => ({ status: 500, body: "boom" }) });
    renderLoggedIn(<OverviewPage />);
    expect(await screen.findByRole("alert")).toHaveTextContent(/server had a problem/);
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });
});

describe("withRollingAverage", () => {
  it("averages the last 7 days and leaves the first 6 empty", () => {
    const points = Array.from({ length: 8 }, (_, i) => ({ date: `d${i}`, units: i + 1 }));
    const out = withRollingAverage(points);
    expect(out.slice(0, 6).every((p) => p.avg === null)).toBe(true);
    expect(out[6].avg).toBe(4);          // (1..7) / 7
    expect(out[7].avg).toBe(5);          // (2..8) / 7
  });
});
