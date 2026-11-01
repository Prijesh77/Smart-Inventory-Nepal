import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { StockItem, TransactionRow } from "../../api/types";
import { mockFetch } from "../../test/fetchMock";
import { meRoute, renderLoggedIn } from "../../test/renderWithAuth";
import { signedQuantity } from "./AdjustmentForm";
import { InventoryPage } from "./InventoryPage";

function item(overrides: Partial<StockItem> = {}): StockItem {
  return {
    product_id: 13, sku: "FOODS_1_013", name: "Foods 1 - Item 013", category_code: "FOODS", on_hand: 10,
    on_order: 0, backorders: 0, inventory_position: 10, avg_daily_sales: 2, days_of_cover: 5, lead_time_days: 7,
    stock_status: "low", updated_at: null, ...overrides,
  };
}

const TXN: TransactionRow = {
  id: 500, product_id: 13, sku: "FOODS_1_013", txn_type: "adjustment", quantity: -3, balance_after: 7,
  reason: "Damaged", purchase_order_id: null, created_by_email: "manager@test.local", created_at: "2026-10-29T12:00:00Z",
};

const page = <T,>(items: T[]) => ({ items, total: items.length, page: 1, page_size: 25, pages: 1 });

function routes(role: "manager" | "viewer" = "manager", extra = {}) {
  return {
    ...meRoute(role),
    "GET /categories": () => ({ body: [{ id: 1, code: "FOODS", name: "Foods" }] }),
    "GET /suppliers": () => ({ body: [] }),
    "GET /inventory": () => ({ body: page([item(), item({ product_id: 14, sku: "HOBBIES_1_001", stock_status: "ok",
      on_hand: 50, inventory_position: 50, days_of_cover: 25 })]) }),
    "GET /inventory/alerts": () => ({ body: [item(), item({ product_id: 15, sku: "OUT_1", stock_status: "out_of_stock",
      on_hand: 0, inventory_position: 0, days_of_cover: 0 })] }),
    "GET /inventory/transactions": () => ({ body: page([TXN]) }),
    ...extra,
  };
}

const lastQuery = (calls: { url: string }[], path: string) =>
  new URL(calls.filter((c) => c.url.startsWith(`/api/v1${path}?`)).at(-1)!.url, "http://x").searchParams;

describe("InventoryPage", () => {
  it("shows stock with status and highlights cover shorter than the lead time", async () => {
    mockFetch(routes());
    renderLoggedIn(<InventoryPage />, "/inventory");
    const row = (await screen.findByRole("link", { name: "FOODS_1_013" })).closest("tr")!;
    expect(within(row).getByText("Low")).toBeInTheDocument();
    expect(within(row).getByText("(shorter than the lead time)", { exact: false })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Low-stock alerts 2/ })).toBeInTheDocument();
  });

  it("filters by stock status", async () => {
    const { calls } = mockFetch(routes());
    renderLoggedIn(<InventoryPage />, "/inventory");
    await screen.findByRole("link", { name: "FOODS_1_013" });
    await userEvent.selectOptions(screen.getByLabelText("Stock status"), "out_of_stock");
    await waitFor(() => expect(lastQuery(calls, "/inventory").get("status")).toBe("out_of_stock"));
  });

  it("lists alerts with the rule explained", async () => {
    mockFetch(routes());
    renderLoggedIn(<InventoryPage />, "/inventory?tab=alerts");
    expect(await screen.findByText("OUT_1")).toBeInTheDocument();
    expect(screen.getByText("Out of stock")).toBeInTheDocument();
    expect(screen.getByText(/will not last until a new order/)).toBeInTheDocument();
  });

  it("opens one product's movement history from the stock table", async () => {
    const { calls } = mockFetch(routes());
    renderLoggedIn(<InventoryPage />, "/inventory");
    await userEvent.click(await screen.findByRole("button", { name: "Movements for FOODS_1_013" }));
    expect(await screen.findByText("Damaged")).toBeInTheDocument();
    expect(lastQuery(calls, "/inventory/transactions").get("product_id")).toBe("13");
    expect(screen.getByRole("tab", { name: "Movement history" })).toHaveAttribute("aria-selected", "true");
  });

  it("viewers can look but not adjust", async () => {
    mockFetch(routes("viewer"));
    renderLoggedIn(<InventoryPage />, "/inventory");
    await screen.findByRole("link", { name: "FOODS_1_013" });
    expect(screen.queryByRole("button", { name: /Adjust stock for/ })).not.toBeInTheDocument();
  });

  it("checks the adjustment before sending, previews the result and records it", async () => {
    const { calls } = mockFetch(routes("manager", { "POST /inventory/adjustments": () => ({ status: 201, body: TXN }) }));
    renderLoggedIn(<InventoryPage />, "/inventory");
    await userEvent.click(await screen.findByRole("button", { name: "Adjust stock for FOODS_1_013" }));
    const dialog = screen.getByRole("dialog");

    await userEvent.type(within(dialog).getByLabelText("Units"), "12");
    expect(within(dialog).getByText(/not allowed/)).toBeInTheDocument();          // 10 - 12 < 0
    await userEvent.click(within(dialog).getByRole("button", { name: "Record movement" }));
    expect(within(dialog).getByText(/stock cannot go below 0/)).toBeInTheDocument();
    expect(within(dialog).getByText(/Explain the change/)).toBeInTheDocument();
    expect(calls.some((c) => c.init?.method === "POST")).toBe(false);

    await userEvent.clear(within(dialog).getByLabelText("Units"));
    await userEvent.type(within(dialog).getByLabelText("Units"), "3");
    expect(within(dialog).getByText("7")).toBeInTheDocument();                      // preview 10 -> 7
    await userEvent.type(within(dialog).getByLabelText("Reason"), "Damaged");
    await userEvent.click(within(dialog).getByRole("button", { name: "Record movement" }));

    expect(await screen.findByRole("status")).toHaveTextContent("FOODS_1_013 -3 (adjustment). Stock is now 7");
    const body = JSON.parse(String(calls.find((c) => c.init?.method === "POST")!.init!.body));
    expect(body).toEqual({ product_id: 13, txn_type: "adjustment", quantity: -3, reason: "Damaged" });
  });

  it("locks the direction for sales and returns", async () => {
    mockFetch(routes());
    renderLoggedIn(<InventoryPage />, "/inventory");
    await userEvent.click(await screen.findByRole("button", { name: "Adjust stock for FOODS_1_013" }));
    const dialog = screen.getByRole("dialog");
    await userEvent.selectOptions(within(dialog).getByLabelText("Type"), "return");
    expect(within(dialog).getByLabelText("Direction")).toBeDisabled();
    expect(within(dialog).getByLabelText("Direction")).toHaveValue("add");
  });

  it("shows the server's refusal", async () => {
    mockFetch(routes("manager", { "POST /inventory/adjustments": () => ({ status: 409,
      body: { detail: "Only 2 units on hand; removing 3 would make stock negative" } }) }));
    renderLoggedIn(<InventoryPage />, "/inventory");
    await userEvent.click(await screen.findByRole("button", { name: "Adjust stock for FOODS_1_013" }));
    const dialog = screen.getByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText("Units"), "3");
    await userEvent.type(within(dialog).getByLabelText("Reason"), "Count");
    await userEvent.click(within(dialog).getByRole("button", { name: "Record movement" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("would make stock negative");
  });
});

describe("signedQuantity", () => {
  it("makes removals negative", () => {
    expect(signedQuantity("remove", 4)).toBe(-4);
    expect(signedQuantity("add", 4)).toBe(4);
  });
});
