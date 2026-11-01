import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";

import type { Product } from "../../api/types";
import { mockFetch } from "../../test/fetchMock";
import { meRoute, renderLoggedIn } from "../../test/renderWithAuth";
import { ProductDetailPage } from "./ProductDetailPage";
import { toInput, validate } from "./ProductForm";
import { ProductsPage } from "./ProductsPage";

const SUPPLIER = { id: 1, code: "SUP_B", name: "Supplier B", lead_time_days: 5, lead_time_sd_days: "1.00", contact_email: null };
const CATEGORIES = [{ id: 1, code: "FOODS", name: "Foods" }, { id: 2, code: "HOBBIES", name: "Hobbies" }];

function product(overrides: Partial<Product> = {}): Product {
  return {
    id: 13, sku: "FOODS_1_013", name: "Foods 1 - Item 013", category: CATEGORIES[0], department: "FOODS_1",
    supplier: SUPPLIER, unit_price: "1.50", unit_cost: "0.98", lead_time_days: null, effective_lead_time_days: 5,
    min_order_qty: 6, pack_size: 6, demand_class: "lumpy", is_active: true, on_hand: 93,
    created_at: "2026-10-29T10:00:00Z", updated_at: "2026-10-29T10:00:00Z", ...overrides,
  };
}

const page = (items: Product[]) => ({ items, total: items.length, page: 1, page_size: 25, pages: 1 });

function routes(role: "manager" | "viewer" = "manager", extra = {}) {
  return {
    ...meRoute(role),
    "GET /categories": () => ({ body: CATEGORIES }),
    "GET /suppliers": () => ({ body: [SUPPLIER] }),
    "GET /products": () => ({ body: page([product(), product({ id: 14, sku: "HOBBIES_1_001", name: "Hobby item",
      category: CATEGORIES[1], demand_class: null, on_hand: 0 })]) }),
    ...extra,
  };
}

const lastProductsQuery = (calls: { url: string }[]) =>
  new URL(calls.filter((c) => c.url.startsWith("/api/v1/products?")).at(-1)!.url, "http://x").searchParams;

describe("ProductsPage", () => {
  it("lists products with stock, lead time and demand pattern", async () => {
    mockFetch(routes());
    renderLoggedIn(<ProductsPage />, "/products");
    const row = (await screen.findByRole("link", { name: "FOODS_1_013" })).closest("tr")!;
    expect(within(row).getByText("$1.50")).toBeInTheDocument();
    expect(within(row).getByText("93")).toBeInTheDocument();
    expect(within(row).getByText("5 d")).toBeInTheDocument();
    expect(within(row).getByText("Lumpy")).toBeInTheDocument();
    expect(screen.getByText("1–2 of 2")).toBeInTheDocument();
  });

  it("sends filters and sorting to the API", async () => {
    const { calls } = mockFetch(routes());
    renderLoggedIn(<ProductsPage />, "/products");
    await screen.findByRole("link", { name: "FOODS_1_013" });
    await userEvent.selectOptions(screen.getByLabelText("Category"), "HOBBIES");
    await waitFor(() => expect(lastProductsQuery(calls).get("category")).toBe("HOBBIES"));
    await userEvent.click(screen.getByRole("button", { name: /On hand/ }));
    await waitFor(() => expect(lastProductsQuery(calls).get("sort")).toBe("on_hand"));
    await userEvent.click(screen.getByRole("button", { name: /On hand/ }));
    await waitFor(() => expect(lastProductsQuery(calls).get("order")).toBe("desc"));
    expect(screen.getByRole("columnheader", { name: /On hand/ })).toHaveAttribute("aria-sort", "descending");
  });

  it("searches after typing stops", async () => {
    const { calls } = mockFetch(routes());
    renderLoggedIn(<ProductsPage />, "/products");
    await screen.findByRole("link", { name: "FOODS_1_013" });
    await userEvent.type(screen.getByLabelText("Search products"), "hob");
    await waitFor(() => expect(lastProductsQuery(calls).get("search")).toBe("hob"));
  });

  it("hides 'Add product' from viewers", async () => {
    mockFetch(routes("viewer"));
    renderLoggedIn(<ProductsPage />, "/products");
    await screen.findByRole("link", { name: "FOODS_1_013" });
    expect(screen.queryByRole("button", { name: "Add product" })).not.toBeInTheDocument();
  });

  it("shows field errors before sending, and the duplicate-SKU message on the SKU field", async () => {
    const { calls } = mockFetch(routes("manager", {
      "POST /products": () => ({ status: 409, body: { detail: "A product with SKU 'FOODS_1_013' already exists" } }),
    }));
    renderLoggedIn(<ProductsPage />, "/products");
    await userEvent.click(await screen.findByRole("button", { name: "Add product" }));
    const dialog = screen.getByRole("dialog", { name: "Add product" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Create product" }));
    expect(within(dialog).getByText("SKU is required")).toBeInTheDocument();
    expect(calls.some((c) => c.init?.method === "POST")).toBe(false);          // nothing sent yet

    await userEvent.type(within(dialog).getByLabelText("SKU"), "foods_1_013");
    await userEvent.type(within(dialog).getByLabelText("Name"), "Duplicate");
    await userEvent.selectOptions(within(dialog).getByLabelText("Category"), "FOODS");
    await userEvent.type(within(dialog).getByLabelText("Unit price ($)"), "2.50");
    await userEvent.click(within(dialog).getByRole("button", { name: "Create product" }));
    expect(await within(dialog).findByText(/already exists/)).toBeInTheDocument();
    expect(within(dialog).getByLabelText("SKU")).toHaveAttribute("aria-invalid", "true");
  });

  it("creates a product and confirms", async () => {
    mockFetch(routes("manager", {
      "POST /products": () => ({ status: 201, body: product({ id: 99, sku: "NEW_1", on_hand: 0 }) }),
    }));
    renderLoggedIn(<ProductsPage />, "/products");
    await userEvent.click(await screen.findByRole("button", { name: "Add product" }));
    const dialog = screen.getByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText("SKU"), "new_1");
    await userEvent.type(within(dialog).getByLabelText("Name"), "New item");
    await userEvent.selectOptions(within(dialog).getByLabelText("Category"), "FOODS");
    await userEvent.type(within(dialog).getByLabelText("Unit price ($)"), "3");
    await userEvent.click(within(dialog).getByRole("button", { name: "Create product" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Product NEW_1 created");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});

describe("product form rules", () => {
  const base = { sku: "A_1", name: "x", category_code: "FOODS", department: "", supplier_id: "", unit_price: "1.00",
    unit_cost: "", lead_time_days: "", min_order_qty: "1", pack_size: "1", is_active: true };

  it("matches the API's rules", () => {
    expect(validate(base, true)).toEqual({});
    expect(validate({ ...base, sku: "bad sku!" }, true).sku).toBeTruthy();
    expect(validate({ ...base, unit_price: "1.234" }, true).unit_price).toBeTruthy();
    expect(validate({ ...base, unit_price: "-1" }, true).unit_price).toBeTruthy();
    expect(validate({ ...base, pack_size: "0" }, true).pack_size).toBeTruthy();
    expect(validate({ ...base, lead_time_days: "0" }, true).lead_time_days).toBeTruthy();
    expect(validate({ ...base, sku: "" }, false)).toEqual({});        // SKU not checked when editing
  });

  it("builds the request body: empty optional fields become null; SKU only on create", () => {
    expect(toInput({ ...base, supplier_id: "2", lead_time_days: "9" }, true)).toMatchObject(
      { sku: "A_1", supplier_id: 2, lead_time_days: 9, unit_cost: null, department: null });
    expect(toInput(base, false)).not.toHaveProperty("sku");
    expect(toInput(base, false)).toHaveProperty("is_active", true);
  });
});

describe("ProductDetailPage", () => {
  const history = {
    product_id: 13, sku: "FOODS_1_013", start: "2016-02-23", end: "2016-05-22", total_units: 6,
    points: [
      { sales_date: "2016-05-20", units: 4, unit_price: "1.50", is_available: true },
      { sales_date: "2016-05-21", units: 0, unit_price: "1.50", is_available: true },
      { sales_date: "2016-05-22", units: 2, unit_price: "1.50", is_available: true },
    ],
  };

  function renderDetail(role: "manager" | "viewer" = "manager", extra = {}) {
    const mocks = mockFetch({
      ...routes(role), "GET /products/13": () => ({ body: product() }),
      "GET /products/13/sales": () => ({ body: history }), ...extra,
    });
    renderLoggedIn(<Routes><Route path="/products/:id" element={<ProductDetailPage />} /></Routes>, "/products/13");
    return mocks;
  }

  it("shows settings, sales summary and the chart", async () => {
    renderDetail();
    expect(await screen.findByRole("heading", { name: /FOODS_1_013/ })).toBeInTheDocument();
    expect(screen.getByText("93 units")).toBeInTheDocument();
    expect(screen.getByText("5 days")).toBeInTheDocument();
    const valueOf = async (label: string) => (await screen.findByText(label)).nextElementSibling?.textContent;
    expect(await valueOf("Units sold")).toBe("6");
    expect(await valueOf("Per available day")).toBe("2");                       // 6 units / 3 days
    expect(await valueOf("Days with no sales")).toBe("1");
    expect(screen.getByRole("img", { name: /Daily units sold for FOODS_1_013/ })).toBeInTheDocument();
  });

  it("asks for a longer period with explicit dates", async () => {
    const { calls } = renderDetail();
    await screen.findByRole("img", { name: /Daily units/ });
    await userEvent.selectOptions(screen.getByLabelText("Period"), "365");
    await waitFor(() => expect(calls.some((c) => c.url.includes("start=2015-05-24&end=2016-05-22"))).toBe(true));
  });

  it("edits a product (managers only)", async () => {
    const { calls } = renderDetail("manager", {
      "PATCH /products/13": () => ({ body: product({ name: "Renamed" }) }),
    });
    await userEvent.click(await screen.findByRole("button", { name: "Edit product" }));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByLabelText("SKU")).toBeDisabled();
    await userEvent.clear(within(dialog).getByLabelText("Name"));
    await userEvent.type(within(dialog).getByLabelText("Name"), "Renamed");
    await userEvent.click(within(dialog).getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    const body = JSON.parse(String(calls.find((c) => c.init?.method === "PATCH")!.init!.body));
    expect(body).toMatchObject({ name: "Renamed", category_code: "FOODS", supplier_id: 1, is_active: true });
    expect(body).not.toHaveProperty("sku");
  });

  it("viewers cannot edit", async () => {
    renderDetail("viewer");
    await screen.findByRole("heading", { name: /FOODS_1_013/ });
    expect(screen.queryByRole("button", { name: "Edit product" })).not.toBeInTheDocument();
  });
});
