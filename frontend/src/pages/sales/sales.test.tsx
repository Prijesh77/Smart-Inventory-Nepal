import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { SalesDay } from "../../api/types";
import { mockFetch } from "../../test/fetchMock";
import { meRoute, renderLoggedIn } from "../../test/renderWithAuth";
import { SalesPage, todayIso, validUnits } from "./SalesPage";

const RICE = { product_id: 7, sku: "RICE-25KG", name: "Rice 25 kg", units: 4, unit_price: "1800.00", amount: "7200.00", on_hand: 16 };

function dayOf(overrides: Partial<SalesDay> = {}): SalesDay {
  return { sales_date: todayIso(), items: [], total_units: 0, total_amount: "0", products_recorded: 0, active_products: 3,
           zero_rows_added: null, ...overrides };
}

const PRODUCT = { id: 7, sku: "RICE-25KG", name: "Rice 25 kg", unit_cost: "1500.00" };

function routes(role: "manager" | "viewer" = "manager", extra = {}) {
  return {
    ...meRoute(role),
    "GET /sales": () => ({ body: dayOf() }),
    "GET /products": () => ({ body: { items: [PRODUCT], total: 1, page: 1, page_size: 8, pages: 1 } }),
    ...extra,
  };
}

const posted = (calls: { url: string; init?: RequestInit }[]) =>
  calls.filter((c) => c.init?.method === "POST").map((c) => JSON.parse(String(c.init!.body)));

async function pickRice(user: ReturnType<typeof userEvent.setup>) {
  await user.type(await screen.findByRole("combobox", { name: "Product" }), "rice");
  await user.click(await screen.findByRole("option", { name: /RICE-25KG/ }));
}

describe("SalesPage", () => {
  it("saves the units for each picked product and reloads the day", async () => {
    let saved = false;
    const { calls } = mockFetch(routes("manager", {
      "GET /sales": () => ({ body: saved ? dayOf({ items: [RICE], total_units: 4, total_amount: "7200.00", products_recorded: 1 }) : dayOf() }),
      "POST /sales": () => { saved = true; return { status: 201, body: dayOf({ items: [RICE], total_units: 4 }) }; },
    }));
    const user = userEvent.setup();
    renderLoggedIn(<SalesPage />, "/sales");
    expect(await screen.findByText("No sales recorded for this day")).toBeInTheDocument();

    await pickRice(user);
    const units = screen.getByRole("textbox", { name: "Units sold, RICE-25KG" });
    await user.clear(units);
    await user.type(units, "4");
    await user.click(screen.getByRole("button", { name: "Save 1 sale" }));

    expect(await screen.findByText(/Recorded 4 units across 1 product/)).toBeInTheDocument();
    expect(posted(calls)).toEqual([{ sales_date: todayIso(), items: [{ product_id: 7, units: 4 }] }]);
    const row = (await screen.findByRole("button", { name: "Correct RICE-25KG" })).closest("tr")!;
    expect(within(row).getByText("16")).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Sales to save" })).not.toBeInTheDocument();
  });

  it("refuses bad units before sending and shows the server's reason when stock is short", async () => {
    const { calls } = mockFetch(routes("manager", {
      "POST /sales": () => ({ status: 409, body: { detail: "Only 2 units on hand; removing 5 would make stock negative" } }),
    }));
    const user = userEvent.setup();
    renderLoggedIn(<SalesPage />, "/sales");
    await pickRice(user);
    const units = screen.getByRole("textbox", { name: "Units sold, RICE-25KG" });
    await user.clear(units);
    await user.type(units, "0");
    await user.click(screen.getByRole("button", { name: "Save 1 sale" }));
    expect(await screen.findByText("Units must be whole numbers of at least 1")).toBeInTheDocument();
    expect(posted(calls)).toEqual([]);

    await user.clear(units);
    await user.type(units, "5");
    await user.click(screen.getByRole("button", { name: "Save 1 sale" }));
    expect(await screen.findByText(/Only 2 units on hand/)).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Sales to save" })).toBeInTheDocument();      // the entry is kept to fix
  });

  it("corrects a recorded sale with a negative entry", async () => {
    const { calls } = mockFetch(routes("manager", {
      "GET /sales": () => ({ body: dayOf({ items: [RICE], total_units: 4, total_amount: "7200.00", products_recorded: 1 }) }),
      "POST /sales": () => ({ status: 201, body: dayOf() }),
    }));
    const user = userEvent.setup();
    renderLoggedIn(<SalesPage />, "/sales");
    await user.click(await screen.findByRole("button", { name: "Correct RICE-25KG" }));
    const dialog = screen.getByRole("dialog", { name: "Correct a sale" });
    await user.type(within(dialog).getByLabelText("Units to remove"), "9");
    await user.click(within(dialog).getByRole("button", { name: "Remove units" }));
    expect(within(dialog).getByText("Enter a whole number from 1 to 4")).toBeInTheDocument();

    await user.clear(within(dialog).getByLabelText("Units to remove"));
    await user.type(within(dialog).getByLabelText("Units to remove"), "1");
    await user.click(within(dialog).getByRole("button", { name: "Remove units" }));
    await waitFor(() => expect(posted(calls)).toEqual([{ sales_date: todayIso(), items: [{ product_id: 7, units: -1 }] }]));
    expect(await screen.findByText(/Removed 1 from RICE-25KG/)).toBeInTheDocument();
  });

  it("marks the day complete and hides the button once every product has a figure", async () => {
    let closed = false;
    const { calls } = mockFetch(routes("manager", {
      "GET /sales": () => ({ body: dayOf({ products_recorded: closed ? 3 : 1 }) }),
      "POST /sales": () => { closed = true; return { status: 201, body: dayOf({ products_recorded: 3, zero_rows_added: 2 }) }; },
    }));
    const user = userEvent.setup();
    renderLoggedIn(<SalesPage />, "/sales");
    expect(await screen.findByText(/1 of 3 products have a figure/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Mark day complete" }));
    expect(await screen.findByText(/2 products recorded as 0 sold/)).toBeInTheDocument();
    expect(posted(calls)).toEqual([{ sales_date: todayIso(), items: [], close_day: true }]);
    expect(await screen.findByText(/Day complete/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Mark day complete" })).not.toBeInTheDocument();
  });

  it("is read-only for viewers", async () => {
    mockFetch(routes("viewer", {
      "GET /sales": () => ({ body: dayOf({ items: [RICE], total_units: 4, total_amount: "7200.00", products_recorded: 1 }) }),
    }));
    renderLoggedIn(<SalesPage />, "/sales");
    expect(await screen.findByText("RICE-25KG")).toBeInTheDocument();
    expect(screen.getByText(/Recording them needs a manager or admin account/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Correct RICE-25KG" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Mark day complete" })).not.toBeInTheDocument();
  });
});

describe("sales helpers", () => {
  it("formats today in local time and checks units", () => {
    expect(todayIso(new Date(2026, 10, 5, 23, 30))).toBe("2026-11-05");
    expect([validUnits("3"), validUnits("0"), validUnits("-2"), validUnits("1.5"), validUnits("")]).toEqual([true, false, false, false, false]);
  });
});
