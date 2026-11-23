import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { SalesCoverage } from "../api/types";
import { mockFetch } from "../test/fetchMock";
import { meRoute, renderLoggedIn } from "../test/renderWithAuth";
import { MissingDaysNote, PartialDaysNote } from "./SalesCoverageNotes";

function coverage(overrides: Partial<SalesCoverage> = {}): SalesCoverage {
  return { window_start: "2026-10-04", window_end: "2026-10-31", recorded_days: 28, missing_days: [], partial_days: [],
           ...overrides };
}

const withCoverage = (body: SalesCoverage) => mockFetch({ ...meRoute("manager"), "GET /sales/coverage": () => ({ body }) });

describe("MissingDaysNote", () => {
  it("warns when several recent days have no sales recorded", async () => {
    withCoverage(coverage({ recorded_days: 24, missing_days: ["2026-10-10", "2026-10-11", "2026-10-12", "2026-10-20"] }));
    renderLoggedIn(<MissingDaysNote />);
    expect(await screen.findByText(/No sales are recorded for 4 of the last 28 days/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Record the missing days" })).toHaveAttribute("href", "/sales");
  });

  it("stays quiet for one or two missing days", async () => {
    const { fetchMock } = withCoverage(coverage({ missing_days: ["2026-10-10", "2026-10-11"] }));
    renderLoggedIn(<MissingDaysNote />);
    await vi.waitFor(() => expect(fetchMock.mock.calls.some(([u]) => String(u).includes("/sales/coverage"))).toBe(true));
    expect(screen.queryByText(/No sales are recorded/)).not.toBeInTheDocument();
  });
});

describe("PartialDaysNote", () => {
  it("lists partly entered days and opens one when clicked", async () => {
    withCoverage(coverage({ partial_days: [{ date: "2026-10-30", products_recorded: 3, products_expected: 43 }] }));
    const pick = vi.fn();
    renderLoggedIn(<PartialDaysNote onPickDay={pick} />);
    await userEvent.setup().click(await screen.findByRole("button", { name: /3 of 43 products/ }));
    expect(pick).toHaveBeenCalledWith("2026-10-30");
  });
});
