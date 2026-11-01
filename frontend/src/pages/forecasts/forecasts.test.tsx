import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { Evaluation, ForecastRun, ProductForecast } from "../../api/types";
import { mergeForecast, windowWape } from "../../components/charts/ForecastChart";
import { mockFetch } from "../../test/fetchMock";
import { meRoute, renderLoggedIn } from "../../test/renderWithAuth";
import { ForecastsPage } from "./ForecastsPage";
import { bestModels } from "./ModelComparison";

const RUN: ForecastRun = {
  id: 7, model_name: "random_forest_v1", model_version: "v1-final", origin_date: "2016-05-23", horizon_days: 28,
  status: "completed", params: { assumptions: ["Prices after the last sales day are assumed unchanged."] },
  metrics: { products: 267, total_units: 14144, test_wape_28d: 0.721, test_bias_pct_28d: 0.003 },
  error_message: null, created_at: "2026-10-29T12:00:00Z", completed_at: "2026-10-29T12:00:09Z",
};

const FORECAST: ProductForecast = {
  product_id: 13, sku: "FOODS_1_013", run: RUN,
  history: [{ date: "2016-05-21", units: 4, is_available: true }, { date: "2016-05-22", units: 2, is_available: true }],
  actual_in_window: [],
  forecast: [{ date: "2016-05-23", horizon: 1, predicted_units: 3 }, { date: "2016-05-24", horizon: 2, predicted_units: 5 }],
  total_forecast: 8,
};

function evaluation(model: string, cls: string, wape: number): Evaluation {
  return { model_name: model, model_version: "v1", period: "test", horizon_days: 28, demand_class: cls,
    n_observations: 100, mae: "1", rmse: "2", wape: String(wape), bias_pct: "0.01" };
}

const EVALS = [
  evaluation("random_forest_v1", "all", 0.721), evaluation("moving_avg_28", "all", 0.733),
  evaluation("random_forest_v1", "intermittent", 0.898), evaluation("moving_avg_28", "intermittent", 0.888),
];

function routes(role: "manager" | "viewer" = "manager", extra = {}) {
  return {
    ...meRoute(role),
    "GET /forecasts/runs": () => ({ body: [RUN] }),
    "GET /dashboard/summary": () => ({ body: { as_of: "2016-05-22" } }),
    "GET /products": () => ({ body: { items: [{ id: 13, sku: "FOODS_1_013", name: "Foods 1 - Item 013" }], total: 1 } }),
    "GET /forecasts/products/13": () => ({ body: FORECAST }),
    "GET /forecasts/evaluations": () => ({ body: EVALS }),
    ...extra,
  };
}

describe("chart data helpers", () => {
  it("keeps actuals and forecasts in separate fields, and leaves unavailable days empty", () => {
    const rows = mergeForecast({ ...FORECAST, history: [...FORECAST.history, { date: "2016-05-20", units: 0, is_available: false }] });
    expect(rows.map((r) => r.date)).toEqual(["2016-05-20", "2016-05-21", "2016-05-22", "2016-05-23", "2016-05-24"]);
    expect(rows[0].actual).toBeNull();                 // not on sale: not drawn as zero demand
    expect(rows[1]).toEqual({ date: "2016-05-21", actual: 4, later: null, forecast: null });
    expect(rows[3]).toEqual({ date: "2016-05-23", actual: null, later: null, forecast: 3 });
  });

  it("scores a back-dated forecast against what really sold", () => {
    const backdated = { ...FORECAST, actual_in_window: [
      { date: "2016-05-23", units: 4, is_available: true }, { date: "2016-05-24", units: 4, is_available: true }] };
    expect(windowWape(backdated)).toBeCloseTo((1 + 1) / 8);   // |3-4| + |5-4| over 8 units
    expect(windowWape(FORECAST)).toBeNull();                   // future: nothing to compare yet
  });

  it("finds the best model per demand class", () => {
    expect(bestModels(EVALS)).toMatchObject({ all: ["random_forest_v1"], intermittent: ["moving_avg_28"] });
  });
});

describe("ForecastsPage", () => {
  it("shows the latest forecast for the first product, with figures and assumptions", async () => {
    renderPage();
    expect(await screen.findByRole("img", { name: /FOODS_1_013: actual daily sales before 23 May 2016/ })).toBeInTheDocument();
    expect(screen.getByText("8 units")).toBeInTheDocument();
    expect(screen.getByText("Not known yet")).toBeInTheDocument();
    expect(screen.getByText(/WAPE 72.1%/)).toBeInTheDocument();
    expect(screen.getByText(/Prices after the last sales day/)).toBeInTheDocument();
  });

  it("marks the best model in the accuracy table", async () => {
    renderPage();
    const table = await screen.findByRole("table", { name: /WAPE = total absolute error/ });
    const rf = within(table).getByRole("row", { name: /Random Forest/ });
    expect(within(rf).getByText("72.1%").parentElement).toHaveTextContent("★");
    const ma = within(table).getByRole("row", { name: /28-day moving average/ });
    expect(within(ma).getByText("88.8%").parentElement).toHaveTextContent("★");
  });

  it("creates a back-dated forecast run and shows it", async () => {
    const run8: ForecastRun = { ...RUN, id: 8, model_name: "moving_avg_28", origin_date: "2016-04-01" };
    let runs = [RUN];
    const { calls } = renderPage("manager", {
      "GET /forecasts/runs": () => ({ body: runs }),
      "POST /forecasts/runs": () => {
        runs = [run8, RUN];                         // the API lists the new run from now on
        return { status: 202, body: { ...run8, status: "pending" } };
      },
      "GET /forecasts/runs/8": () => ({ body: run8 }),
    });
    await screen.findByRole("img", { name: /FOODS_1_013/ });
    await userEvent.selectOptions(screen.getByLabelText("Model"), "moving_avg_28");
    await userEvent.type(screen.getByLabelText("Start date (optional)"), "2016-04-01");
    await userEvent.click(screen.getByRole("button", { name: "Create forecast" }));
    await waitFor(() => expect(calls.some((c) => c.url.includes("run_id=8"))).toBe(true));
    const body = JSON.parse(String(calls.find((c) => c.init?.method === "POST")!.init!.body));
    expect(body).toEqual({ model_name: "moving_avg_28", horizon_days: 28, origin_date: "2016-04-01" });
  });

  it("viewers see results but cannot create runs", async () => {
    renderPage("viewer");
    await screen.findByRole("img", { name: /FOODS_1_013/ });
    expect(screen.queryByRole("button", { name: "Create forecast" })).not.toBeInTheDocument();
  });

  it("explains when there is no forecast yet", async () => {
    renderPage("viewer", { "GET /forecasts/runs": () => ({ body: [] }) });
    expect(await screen.findByText("No completed forecast yet")).toBeInTheDocument();
    expect(screen.getByText("Ask a manager to create one.")).toBeInTheDocument();
  });

  function renderPage(role: "manager" | "viewer" = "manager", extra = {}) {
    const mocks = mockFetch(routes(role, extra));
    renderLoggedIn(<ForecastsPage pollMs={0} />, "/forecasts");
    return mocks;
  }
});
