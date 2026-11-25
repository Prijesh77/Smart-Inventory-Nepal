import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { Product, Shelf } from "../../api/types";
import { mockFetch } from "../../test/fetchMock";
import { meRoute, renderLoggedIn } from "../../test/renderWithAuth";
import { groupByArea, ShelvesPage } from "./ShelvesPage";

const SHELVES: Shelf[] = [
  { id: 1, code: "A-1", name: "Aisle A: rice, dal and flour", area: "Front shop", product_count: 2 },
  { id: 2, code: "STORE", name: "Back storeroom", area: "Storeroom", product_count: 0 },
];

function product(id: number, sku: string, name: string, onHand: number, shelf: Shelf | null = SHELVES[0]): Product {
  return {
    id, sku, name, category: { id: 1, code: "GRAINS", name: "Rice, dal & flour" }, department: null, supplier: null,
    shelf: shelf && { id: shelf.id, code: shelf.code, name: shelf.name, area: shelf.area },
    unit_price: "100.00", unit_cost: "90.00", lead_time_days: null, effective_lead_time_days: 3, min_order_qty: 1,
    pack_size: 1, demand_class: null, is_active: true, on_hand: onHand, created_at: "2026-11-01T00:00:00Z",
    updated_at: "2026-11-01T00:00:00Z",
  };
}

const RICE = product(7, "RICE-25KG", "Rice 25 kg", 12);
const DAL = product(8, "DAL-1KG", "Masoor dal 1 kg", 0);
const page = (items: Product[]) => ({ items, total: items.length, page: 1, page_size: 100, pages: 1 });

function routes(role: "manager" | "viewer" = "manager", extra = {}) {
  return {
    ...meRoute(role),
    "GET /shelves": () => ({ body: SHELVES }),
    "GET /products": (url: string) => {
      const q = new URL(url, "http://x").searchParams;
      if (q.get("shelf_id") === "0") return { body: page([]) };
      if (q.get("shelf_id") === "1") return { body: page([RICE, DAL]) };
      if (q.get("search")) return { body: page([RICE]) };
      return { body: page([]) };
    },
    ...extra,
  };
}

describe("ShelvesPage", () => {
  it("groups shelves by area and shows what is on a shelf", async () => {
    mockFetch(routes());
    renderLoggedIn(<ShelvesPage />, "/shelves");
    expect(await screen.findByRole("region", { name: "Front shop" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Storeroom" })).toBeInTheDocument();

    await userEvent.setup().click(screen.getByRole("button", { name: /A-1/ }));
    expect(await screen.findByText("Masoor dal 1 kg")).toBeInTheDocument();
    const table = screen.getByRole("table");
    expect(within(table).getByText("12")).toBeInTheDocument();
    expect(within(table).getByText("Out of stock")).toBeInTheDocument();
  });

  it("finds which shelf a product is on", async () => {
    mockFetch(routes());
    renderLoggedIn(<ShelvesPage />, "/shelves");
    await userEvent.setup().type(await screen.findByLabelText("Product"), "rice");
    const results = await screen.findByRole("list", { name: "Where the products are" });
    expect(within(results).getByText("A-1")).toBeInTheDocument();
    expect(within(results).getByText("Aisle A: rice, dal and flour")).toBeInTheDocument();
  });

  it("lets managers add a shelf, and checks the code first", async () => {
    let posted: unknown = null;
    mockFetch(routes("manager", {
      "POST /shelves": (_url: string, init?: RequestInit) => {
        posted = JSON.parse(String(init?.body));
        return { status: 201, body: { id: 3, code: "B-1", name: "Aisle B", area: null, product_count: 0 } };
      },
    }));
    renderLoggedIn(<ShelvesPage />, "/shelves");
    const user = userEvent.setup();
    await user.click((await screen.findAllByRole("button", { name: "Add shelf" }))[0]);
    await user.type(screen.getByLabelText("Shelf code"), "B 1");
    await user.type(screen.getByLabelText("Name"), "Aisle B");
    await user.click(screen.getByRole("button", { name: "Save shelf" }));
    expect(await screen.findByText("Use letters, digits, '-' or '_', e.g. A-1")).toBeInTheDocument();
    expect(posted).toBeNull();

    await user.clear(screen.getByLabelText("Shelf code"));
    await user.type(screen.getByLabelText("Shelf code"), "B-1");
    await user.click(screen.getByRole("button", { name: "Save shelf" }));
    await screen.findByText("Shelf B-1 saved.");
    expect(posted).toEqual({ code: "B-1", name: "Aisle B", area: null });
  });

  it("does not offer changes to viewers", async () => {
    mockFetch(routes("viewer"));
    renderLoggedIn(<ShelvesPage />, "/shelves");
    await screen.findByRole("region", { name: "Front shop" });
    expect(screen.queryByRole("button", { name: "Add shelf" })).not.toBeInTheDocument();
  });

  it("puts shelves with no area in their own group", () => {
    const groups = groupByArea([...SHELVES, { id: 9, code: "X", name: "Loose", area: null, product_count: 0 }]);
    expect(groups.map(([area]) => area)).toEqual(["Front shop", "Storeroom", "Other shelves"]);
  });
});
