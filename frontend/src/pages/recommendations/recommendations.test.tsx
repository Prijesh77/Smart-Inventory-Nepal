import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { Recommendation, RecommendationPage, RecommendationRun } from "../../api/types";
import { mockFetch } from "../../test/fetchMock";
import { meRoute, renderLoggedIn } from "../../test/renderWithAuth";
import { RecommendationsPage } from "./RecommendationsPage";

const POLICY = { service_level: 0.95, review_period_days: 7, ordering_cost: 10, holding_cost_rate: 0.25,
  min_cycle_days: 7, max_cycle_days: 28, excess_cover_days: 60 };

const RUN: RecommendationRun = {
  id: 3, forecast_run_id: 7, policy_settings: POLICY, status: "completed", error_message: null,
  created_at: "2026-10-29T12:00:00Z", completed_at: "2026-10-29T12:00:10Z",
  summary: { counts: { critical_stockout_risk: 5, reorder_soon: 48, healthy: 175, excess_inventory: 39 }, total_suggested_order_cost: 8216.03 },
};

function rec(overrides: Partial<Recommendation> = {}): Recommendation {
  return {
    id: 101, product_id: 50, sku: "FOODS_2_219", name: "Foods 2 - Item 219", on_hand: "21", inventory_position: "21",
    lead_time_days: 14, forecast_lead_time_demand: "24.0", forecast_protection_demand: "36.2", safety_stock: "19.0",
    reorder_point: "55.1", order_up_to: "104.2", suggested_qty: 83, estimated_order_cost: "131.14",
    stockout_probability: "0.62", days_of_cover: "12.2", risk_category: "critical_stockout_risk",
    explanation: "Position is below expected lead-time demand, so a stockout is likely before new stock arrives. Order 83 units now and consider expediting.",
    warnings: ["Safety stock sized from measured protection-period forecast errors"],
    review_status: "pending", reviewed_at: null, ...overrides,
  };
}

const page = (items: Recommendation[]): RecommendationPage =>
  ({ run: RUN, items, total: items.length, page: 1, page_size: 25, pages: 1 });

function routes(role: "manager" | "viewer" = "manager", extra = {}) {
  return {
    ...meRoute(role),
    "GET /recommendations": (url: string) => ({
      body: url.includes("review_status=approved") ? page([rec({ review_status: "approved" })])
        : page([rec(), rec({ id: 102, sku: "HOBBIES_1_001", risk_category: "healthy", suggested_qty: 0,
          estimated_order_cost: "0.00", explanation: "No order needed this review." })]),
    }),
    "GET /recommendations/runs": () => ({ body: [RUN] }),
    "GET /settings/policy": () => ({ body: POLICY }),
    ...extra,
  };
}

const lastQuery = (calls: { url: string }[]) =>
  new URL(calls.filter((c) => c.url.startsWith("/api/v1/recommendations?")).at(-1)!.url, "http://x").searchParams;

describe("RecommendationsPage", () => {
  it("shows the run summary, risk counts and the table", async () => {
    mockFetch(routes());
    renderLoggedIn(<RecommendationsPage />, "/recommendations");
    expect(await screen.findByText("$8,216.03")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Critical stockout risk 5/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /All 267/ })).toHaveAttribute("aria-pressed", "true");
    const row = screen.getByRole("link", { name: "FOODS_2_219" }).closest("tr")!;
    expect(within(row).getByText("83")).toBeInTheDocument();
    expect(within(row).getByText("$131.14")).toBeInTheDocument();
    expect(within(row).getByText("To review")).toBeInTheDocument();
  });

  it("filters by risk with the chips", async () => {
    const { calls } = mockFetch(routes());
    renderLoggedIn(<RecommendationsPage />, "/recommendations");
    await userEvent.click(await screen.findByRole("button", { name: /Critical stockout risk 5/ }));
    await waitFor(() => expect(lastQuery(calls).get("risk")).toBe("critical_stockout_risk"));
    expect(screen.getByRole("button", { name: /Critical stockout risk 5/ })).toHaveAttribute("aria-pressed", "true");
  });

  it("explains each recommendation on request", async () => {
    mockFetch(routes());
    renderLoggedIn(<RecommendationsPage />, "/recommendations");
    const why = (await screen.findAllByRole("button", { name: "Why?" }))[0];
    await userEvent.click(why);
    expect(why).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText(/stockout is likely before new stock arrives/)).toBeInTheDocument();
    expect(screen.getByText("Stockout chance over lead time (model estimate)").nextElementSibling).toHaveTextContent("62%");
    expect(screen.getByText(/measured protection-period forecast errors/)).toBeInTheDocument();
  });

  it("approves a recommendation; items with nothing to order cannot be approved", async () => {
    const { calls } = mockFetch(routes("manager", {
      "PATCH /recommendations/101": () => ({ body: rec({ review_status: "approved" }) }),
    }));
    renderLoggedIn(<RecommendationsPage />, "/recommendations");
    await userEvent.click(await screen.findByRole("button", { name: "Approve FOODS_2_219" }));
    await waitFor(() => expect(calls.some((c) => c.init?.method === "PATCH")).toBe(true));
    const patch = calls.find((c) => c.init?.method === "PATCH")!;
    expect(JSON.parse(String(patch.init!.body))).toEqual({ review_status: "approved" });
    expect(screen.queryByRole("button", { name: "Approve HOBBIES_1_001" })).not.toBeInTheDocument();
  });

  it("creates draft orders from this run's approved items only and links to them", async () => {
    const { calls } = mockFetch(routes("manager", {
      "POST /purchase-orders/from-recommendations": () => ({ status: 201, body: [{
        id: 1, po_number: "PO-000001", lines: [{ id: 1 }], supplier_name: "Supplier D" }] }),
    }));
    renderLoggedIn(<RecommendationsPage />, "/recommendations");
    await userEvent.click(await screen.findByRole("button", { name: "Create draft orders from approved" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Created 1 draft purchase order(s) with 1 line(s). Nothing has been sent");
    expect(screen.getByRole("link", { name: "PO-000001" })).toHaveAttribute("href", "/purchase-orders/1");
    const post = calls.find((c) => c.init?.method === "POST")!;
    expect(JSON.parse(String(post.init!.body))).toEqual({ recommendation_ids: [101] });
  });

  it("viewers can read explanations but not decide or order", async () => {
    mockFetch(routes("viewer"));
    renderLoggedIn(<RecommendationsPage />, "/recommendations");
    await screen.findByRole("link", { name: "FOODS_2_219" });
    expect(screen.queryByRole("button", { name: /Approve/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Create draft orders/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "New recommendations" })).not.toBeInTheDocument();
  });

  it("creates a new run with a different service level", async () => {
    const run4 = { ...RUN, id: 4 };
    const { calls } = mockFetch(routes("manager", {
      "GET /forecasts/runs": () => ({ body: [] }),
      "POST /recommendations/runs": () => ({ status: 202, body: { ...run4, status: "pending" } }),
      "GET /recommendations/runs/4": () => ({ body: run4 }),
    }));
    renderLoggedIn(<RecommendationsPage pollMs={0} />, "/recommendations");
    await userEvent.click(await screen.findByRole("button", { name: "New recommendations" }));
    const dialog = screen.getByRole("dialog");
    await userEvent.clear(within(dialog).getByLabelText("Service level target (%)"));
    await userEvent.type(within(dialog).getByLabelText("Service level target (%)"), "98");
    await userEvent.click(within(dialog).getByRole("button", { name: "Create recommendations" }));
    await waitFor(() => expect(lastQuery(calls).get("run_id")).toBe("4"));
    const post = calls.find((c) => c.init?.method === "POST")!;
    expect(JSON.parse(String(post.init!.body))).toEqual({ forecast_run_id: null, service_level: 0.98, review_period_days: 7 });
  });

  it("explains when there are no recommendations yet", async () => {
    mockFetch(routes("viewer", {
      "GET /recommendations": () => ({ status: 404, body: { detail: "No completed recommendation run yet" } }),
    }));
    renderLoggedIn(<RecommendationsPage />, "/recommendations");
    expect(await screen.findByText("No recommendations yet")).toBeInTheDocument();
  });
});
