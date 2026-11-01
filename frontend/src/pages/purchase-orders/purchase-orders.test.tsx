import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";

import type { PurchaseOrder } from "../../api/types";
import { mockFetch } from "../../test/fetchMock";
import { meRoute, renderLoggedIn } from "../../test/renderWithAuth";
import { lineErrors, linesBody, type DraftLine } from "./OrderForm";
import { PurchaseOrderDetailPage } from "./PurchaseOrderDetailPage";
import { PurchaseOrdersPage } from "./PurchaseOrdersPage";
import { receiveLines } from "./ReceiveForm";

const SUPPLIER = { id: 4, code: "SUP_D", name: "Supplier D", lead_time_days: 10, lead_time_sd_days: "2.00", contact_email: null };

function order(overrides: Partial<PurchaseOrder> = {}): PurchaseOrder {
  return {
    id: 1, po_number: "PO-000001", supplier_id: 4, supplier_code: "SUP_D", supplier_name: "Supplier D", status: "draft",
    expected_date: "2016-06-02", submitted_at: null, received_at: null, notes: null, created_at: "2026-10-29T12:00:00Z",
    lines: [
      { id: 11, product_id: 50, sku: "HOBBIES_2_147", name: "Hobbies 2 - Item 147", quantity_ordered: 12, quantity_received: 0,
        quantity_outstanding: 12, unit_cost: "1.50", line_total: "18.00", recommendation_id: 101 },
      { id: 12, product_id: 51, sku: "HOBBIES_2_148", name: "Hobbies 2 - Item 148", quantity_ordered: 6, quantity_received: 0,
        quantity_outstanding: 6, unit_cost: "2.00", line_total: "12.00", recommendation_id: null },
    ],
    total_units: 18, total_cost: "30.00", note: "Orders are only recorded in this app; nothing is sent to suppliers.",
    ...overrides,
  };
}

const lines: DraftLine[] = [{ product_id: 50, sku: "A", name: "a", quantity: "3", unit_cost: "" }];

describe("order helpers", () => {
  it("checks lines like the API", () => {
    expect(lineErrors([])).toMatch(/at least one/);
    expect(lineErrors([{ ...lines[0], quantity: "0" }])).toMatch(/at least 1/);
    expect(lineErrors([{ ...lines[0], unit_cost: "1.234" }])).toMatch(/unit cost/);
    expect(lineErrors(lines)).toBeNull();
    expect(linesBody(lines)).toEqual([{ product_id: 50, quantity: 3, unit_cost: null }]);
  });

  it("builds receipt lines and refuses over-receiving", () => {
    const po = order({ status: "submitted" });
    expect(receiveLines(po, { 11: "5", 12: "0" })).toEqual({ lines: [{ item_id: 11, quantity: 5 }], error: null });
    expect(receiveLines(po, { 11: "13" }).error).toMatch(/only 12 still expected/);
    expect(receiveLines(po, { 11: "", 12: "0" }).error).toMatch(/at least one line/);
  });
});

describe("PurchaseOrdersPage", () => {
  const listRoutes = (role: "manager" | "viewer" = "manager") => ({
    ...meRoute(role),
    "GET /categories": () => ({ body: [] }),
    "GET /suppliers": () => ({ body: [SUPPLIER] }),
    "GET /purchase-orders": () => ({ body: { items: [order()], total: 1, page: 1, page_size: 25, pages: 1 } }),
  });

  it("lists orders with totals and a status filter", async () => {
    const { calls } = mockFetch(listRoutes());
    renderLoggedIn(<PurchaseOrdersPage />, "/purchase-orders");
    const row = (await screen.findByRole("link", { name: "PO-000001" })).closest("tr")!;
    expect(within(row).getByText("Draft")).toBeInTheDocument();
    expect(within(row).getByText("Rs 30.00")).toBeInTheDocument();
    expect(screen.getByText(/Nothing is ever sent to a supplier/)).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Order status"), "submitted");
    await waitFor(() => expect(calls.at(-1)!.url).toContain("status=submitted"));
  });

  it("creates a draft by hand from the supplier's products", async () => {
    const { calls } = mockFetch({
      ...listRoutes(),
      "GET /products": () => ({ body: { items: [{ id: 50, sku: "HOBBIES_2_147", name: "Item 147", unit_cost: "1.50" }], total: 1 } }),
      "POST /purchase-orders": () => ({ status: 201, body: order({ id: 9 }) }),
      "GET /purchase-orders/9": () => ({ body: order({ id: 9 }) }),
    });
    renderLoggedIn(
      <Routes>
        <Route path="/purchase-orders" element={<PurchaseOrdersPage />} />
        <Route path="/purchase-orders/:id" element={<p>Order page</p>} />
      </Routes>, "/purchase-orders");
    await userEvent.click(await screen.findByRole("button", { name: "New draft order" }));
    const dialog = screen.getByRole("dialog");
    await userEvent.selectOptions(within(dialog).getByLabelText("Supplier"), "4");
    await userEvent.type(within(dialog).getByLabelText("Add a product from this supplier"), "147");
    await userEvent.click(await within(dialog).findByRole("option", { name: /HOBBIES_2_147/ }));
    expect(calls.some((c) => c.url.includes("supplier_id=4") && c.url.includes("search=147"))).toBe(true);
    await userEvent.clear(within(dialog).getByLabelText("Quantity for HOBBIES_2_147"));
    await userEvent.type(within(dialog).getByLabelText("Quantity for HOBBIES_2_147"), "24");
    expect(within(dialog).getByText("Rs 36.00", { selector: "tfoot td" })).toBeInTheDocument();     // 24 x 1.50
    await userEvent.click(within(dialog).getByRole("button", { name: "Create draft" }));
    expect(await screen.findByText("Order page")).toBeInTheDocument();
    const body = JSON.parse(String(calls.find((c) => c.init?.method === "POST")!.init!.body));
    expect(body).toEqual({ supplier_id: 4, notes: null, expected_date: null,
      lines: [{ product_id: 50, quantity: 24, unit_cost: "1.50" }] });
  });

  it("viewers cannot create orders", async () => {
    mockFetch(listRoutes("viewer"));
    renderLoggedIn(<PurchaseOrdersPage />, "/purchase-orders");
    await screen.findByRole("link", { name: "PO-000001" });
    expect(screen.queryByRole("button", { name: "New draft order" })).not.toBeInTheDocument();
  });
});

describe("PurchaseOrderDetailPage", () => {
  function renderDetail(po: PurchaseOrder, role: "manager" | "viewer" = "manager", extra = {}) {
    const mocks = mockFetch({
      ...meRoute(role), "GET /categories": () => ({ body: [] }), "GET /suppliers": () => ({ body: [SUPPLIER] }),
      "GET /purchase-orders/1": () => ({ body: po }), ...extra,
    });
    renderLoggedIn(<Routes><Route path="/purchase-orders/:id" element={<PurchaseOrderDetailPage />} /></Routes>, "/purchase-orders/1");
    return mocks;
  }

  it("submits a draft", async () => {
    renderDetail(order(), "manager", {
      "POST /purchase-orders/1/submit": () => ({ body: order({ status: "submitted", submitted_at: "2026-10-29T13:00:00Z" }) }),
    });
    await userEvent.click(await screen.findByRole("button", { name: "Submit order" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Nothing was sent to the supplier");
    expect(screen.getByText("Submitted", { selector: "span" })).toBeInTheDocument();     // the status badge
    expect(screen.getByRole("button", { name: "Receive delivery" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit draft" })).not.toBeInTheDocument();
  });

  it("books a partial delivery", async () => {
    const after = order({ status: "partially_received", lines: order().lines.map((l) => l.id === 11
      ? { ...l, quantity_received: 5, quantity_outstanding: 7 } : l) });
    const { calls } = renderDetail(order({ status: "submitted" }), "manager", {
      "POST /purchase-orders/1/receive": () => ({ body: after }),
    });
    await userEvent.click(await screen.findByRole("button", { name: "Receive delivery" }));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByLabelText("Received now for HOBBIES_2_147")).toHaveValue("12");    // prefilled
    await userEvent.clear(within(dialog).getByLabelText("Received now for HOBBIES_2_147"));
    await userEvent.type(within(dialog).getByLabelText("Received now for HOBBIES_2_147"), "5");
    await userEvent.clear(within(dialog).getByLabelText("Received now for HOBBIES_2_148"));
    await userEvent.type(within(dialog).getByLabelText("Received now for HOBBIES_2_148"), "0");
    await userEvent.click(within(dialog).getByRole("button", { name: "Book delivery" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Partial delivery booked");
    expect(screen.getByText("Partly received")).toBeInTheDocument();
    const body = JSON.parse(String(calls.find((c) => c.url.endsWith("/receive"))!.init!.body));
    expect(body).toEqual({ lines: [{ item_id: 11, quantity: 5 }] });
  });

  it("asks before cancelling and hides cancel once something was received", async () => {
    renderDetail(order({ status: "submitted" }), "manager", {
      "POST /purchase-orders/1/cancel": () => ({ body: order({ status: "cancelled" }) }),
    });
    await userEvent.click(await screen.findByRole("button", { name: "Cancel order" }));
    const dialog = screen.getByRole("dialog", { name: "Cancel PO-000001?" });
    expect(within(dialog).getByText(/go back to "approved"/)).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole("button", { name: "Cancel order" }));
    expect(await screen.findByText("Cancelled")).toBeInTheDocument();
  });

  it("no cancel after a delivery; viewers have no actions", async () => {
    const partial = order({ status: "partially_received", lines: order().lines.map((l) => ({ ...l, quantity_received: 1, quantity_outstanding: l.quantity_ordered - 1 })) });
    renderDetail(partial, "viewer");
    await screen.findByRole("heading", { name: "PO-000001" });
    expect(screen.queryByRole("button", { name: /Receive|Cancel|Submit/ })).not.toBeInTheDocument();
    expect(screen.getByText("from a reorder recommendation", { exact: false })).toBeInTheDocument();
  });
});
