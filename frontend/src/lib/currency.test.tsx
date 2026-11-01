import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";

import { AppRoutes } from "../App";
import { AuthProvider } from "../auth/AuthContext";
import { CurrencyProvider } from "../auth/CurrencyContext";
import { mockFetch, TEST_USER } from "../test/fetchMock";
import { inputToMoney, moneyToInput, setDisplayCurrency } from "./currency";
import { fmtLocalMoney, fmtMoney } from "./format";

afterEach(() => {
  setDisplayCurrency("USD", 1);
  localStorage.clear();
});

describe("money formatting and conversion", () => {
  it("shows dollars unchanged", () => {
    setDisplayCurrency("USD", 152.66);
    expect(fmtMoney("8216.03")).toBe("$8,216.03");
    expect(fmtMoney(30200, true)).toBe("$30.2K");
  });

  it("converts dollars to rupees with lakh/crore grouping", () => {
    setDisplayCurrency("NPR", 152.66);
    expect(fmtMoney(1)).toBe("Rs 152.66");
    expect(fmtMoney("8216.03")).toBe("Rs 12,54,259.14");        // 8,216.03 x 152.66
    expect(fmtMoney(30200, true)).toBe("Rs 46.1L");
    expect(fmtMoney(300000, true)).toBe("Rs 4.6Cr");
    expect(fmtMoney(-2)).toBe("-Rs 305.32");
    expect(fmtLocalMoney(500)).toBe("Rs 500.00");               // already in rupees: not converted again
  });

  it("turns typed rupees into dollars for the API, and back", () => {
    setDisplayCurrency("NPR", 152.66);
    expect(inputToMoney("1000")).toBe("6.55");
    expect(moneyToInput("6.55")).toBe("999.92");                // saved to the cent, so within Re 1
    expect(inputToMoney("")).toBe("");
    setDisplayCurrency("USD", 152.66);
    expect(inputToMoney("2.50")).toBe("2.50");
  });
});

describe("currency switch", () => {
  it("shows rupees by default at the saved rate and switches to dollars", async () => {
    sessionStorage.setItem("smart-inventory.token", "stored");
    mockFetch({
      "GET /auth/me": () => ({ body: TEST_USER }),
      "GET /settings/currency": () => ({ body: { npr_per_usd: 100, rate_date: "2026-10-29", rate_source: "Test bank" } }),
      "GET /dashboard/summary": () => ({ body: SUMMARY }),
    });
    render(
      <AuthProvider>
        <CurrencyProvider>
          <MemoryRouter initialEntries={["/"]}><AppRoutes /></MemoryRouter>
        </CurrencyProvider>
      </AuthProvider>,
    );
    const value = async () => within(await screen.findByRole("group", { name: "Inventory value (at cost)" }, { timeout: 5000 }));
    expect(await (await value()).findByText("Rs 30.2L")).toBeInTheDocument();      // $30,200 x 100

    await userEvent.click(screen.getByRole("button", { name: "Show amounts in US dollars" }));
    expect(await (await value()).findByText("$30.2K")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Show amounts in US dollars" })).toHaveAttribute("aria-pressed", "true");
    expect(localStorage.getItem("smart-inventory.currency")).toBe("USD");
  });
});

const SUMMARY = {
  as_of: "2016-05-22", active_products: 267, units_on_hand: 15368, inventory_value: "30200.00", products_without_cost: 0,
  stock_status: { ok: 267 }, sales: null, forecast: null, recommendations: null,
  purchase_orders: { open: 0, open_order_value: "0", drafts: 0 }, recent_activity: [],
};
