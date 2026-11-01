import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { SimulationRow, SimulationRun } from "../../api/types";
import { mockFetch } from "../../test/fetchMock";
import { meRoute, renderLoggedIn } from "../../test/renderWithAuth";
import { AnalyticsPage } from "./AnalyticsPage";
import { pivotWeekly } from "./CategorySection";
import { curves } from "./SimulationSection";

function row(policy: SimulationRow["policy"], level: number, fill: number, cost: number): SimulationRow {
  return { policy, service_level: level, demand_class: "all", fill_rate: fill, stockout_rate: 0.001, units_lost: 500,
    avg_inventory_value: 29000, n_orders: 2300, holding_cost: 7000, ordering_cost: 23000, total_cost: cost, lost_margin: 400 };
}

const SIM: SimulationRun = {
  id: 2, name: "Run from the app", status: "completed",
  params: { service_levels: [0.9, 0.95], ordering_cost: 10, holding_cost_rate: 0.25, uncertain_lead_time: false },
  results: {
    note: "SIMULATED results", items: 267, days: 364,
    summary: [row("engine_rf", 0.95, 0.9964, 30232), row("engine_rf", 0.9, 0.995, 29656),
      row("baseline_demand_sd", 0.9, 0.9892, 28991), row("baseline_demand_sd", 0.95, 0.9907, 29405)],
    matched_comparisons: [{ policy: "engine_rf", reference: "baseline_demand_sd", fill_rate: 0.9878,
      policy_value: 28800, reference_value: 29330, pct_diff: -0.0181 }],
  },
  error_message: null, created_at: "2026-10-29T12:00:00Z", completed_at: "2026-10-29T12:00:25Z",
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
    "GET /simulations": () => ({ body: [SIM] }),
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

  it("builds one cost-vs-fill curve per policy, ordered by fill rate", () => {
    const rf = curves(SIM.results!.summary).find((c) => c.policy === "engine_rf")!;
    expect(rf.points).toEqual([{ fill: 99.5, cost: 29656, level: 0.9 }, { fill: 99.64, cost: 30232, level: 0.95 }]);
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

  it("labels simulation results as simulated and states the comparison in words", async () => {
    mockFetch(routes("viewer"));
    renderLoggedIn(<AnalyticsPage />, "/analytics");
    expect(await screen.findByText(/not results from a real store/)).toBeInTheDocument();
    expect(screen.getByText(/At the same fill rate/).closest("li")).toHaveTextContent(
      "At the same fill rate (98.78%), Engine + Random Forest costs 1.8% less than Textbook baseline (Rs 28,800.00 vs Rs 29,330.00).");
    expect(screen.queryByRole("button", { name: "Run simulation" })).not.toBeInTheDocument();
  });

  it("runs a simulation with the chosen settings", async () => {
    const sim3 = { ...SIM, id: 3 };
    let list = [SIM];
    const { calls } = mockFetch(routes("manager", {
      "GET /simulations": () => ({ body: list }),
      "POST /simulations": () => { list = [sim3, SIM]; return { status: 202, body: { ...sim3, status: "pending" } }; },
      "GET /simulations/3": () => ({ body: sim3 }),
    }));
    renderLoggedIn(<AnalyticsPage pollMs={0} />, "/analytics");
    await screen.findByText(/not results from a real store/);
    await userEvent.click(screen.getByRole("checkbox", { name: "80%" }));       // untick 80%
    await userEvent.clear(screen.getByLabelText("Ordering cost per order (Rs)"));
    await userEvent.type(screen.getByLabelText("Ordering cost per order (Rs)"), "2");
    await userEvent.click(screen.getByRole("checkbox", { name: /Real lead times vary/ }));
    await userEvent.click(screen.getByRole("button", { name: "Run simulation" }));
    await waitFor(() => expect(screen.getByLabelText("Simulation run")).toHaveValue("3"));
    const body = JSON.parse(String(calls.find((c) => c.init?.method === "POST")!.init!.body));
    expect(body).toEqual({ name: "Run from the app", service_levels: [0.9, 0.95, 0.98], ordering_cost: 2,
      holding_cost_rate: 0.25, uncertain_lead_time: true });
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

  it("explains when there are no simulation results", async () => {
    mockFetch(routes("viewer", { "GET /simulations": () => ({ body: [] }) }));
    renderLoggedIn(<AnalyticsPage />, "/analytics");
    expect(await screen.findByText("No simulation results yet")).toBeInTheDocument();
  });
});
