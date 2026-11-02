import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { setDateStyle } from "../lib/nepaliDate";
import { mockFetch, TEST_USER } from "../test/fetchMock";
import { renderLoggedIn } from "../test/renderWithAuth";
import { DateField } from "./DateField";
import { Layout } from "./Layout";

describe("DateField", () => {
  it("takes a BS date, shows the AD date, and sends AD", async () => {
    setDateStyle("bs", false);
    const onChange = vi.fn();
    render(<DateField id="d" label="Expected delivery" value="" onChange={onChange} />);
    await userEvent.type(screen.getByLabelText("Expected delivery (BS)"), "2083-07-15");
    expect(onChange).toHaveBeenLastCalledWith("2026-11-01");
    expect(screen.getByText("= 1 Nov 2026 (AD)")).toBeInTheDocument();
  });

  it("refuses a BS date that does not exist, or one after the limit", async () => {
    setDateStyle("bs", false);
    const onChange = vi.fn();
    render(<DateField id="d" label="Start" value="" max="2026-10-31" onChange={onChange} />);
    const input = screen.getByLabelText("Start (BS)");
    await userEvent.type(input, "2083-07-31");                          // Kartik 2083 has 30 days
    expect(onChange).toHaveBeenLastCalledWith(null);
    expect(screen.getByText(/Not a real BS date/)).toBeInTheDocument();
    await userEvent.clear(input);
    expect(onChange).toHaveBeenLastCalledWith("");                       // empty is allowed
    await userEvent.type(input, "2083-07-15");                          // 1 Nov 2026, after the limit
    expect(onChange).toHaveBeenLastCalledWith(null);
    expect(screen.getByText("Must be on or before 14 Kartik 2083")).toBeInTheDocument();   // the limit in BS too
  });

  it("starts from an existing AD value shown in BS, and is a normal date picker in AD style", () => {
    setDateStyle("bs", false);
    const { unmount } = render(<DateField id="d" label="Start" value="2026-11-01" onChange={() => undefined} />);
    expect(screen.getByLabelText("Start (BS)")).toHaveValue("2083-07-15");
    unmount();
    setDateStyle("ad", false);
    render(<DateField id="d" label="Start" value="2026-11-01" onChange={() => undefined} />);
    expect(screen.getByLabelText("Start")).toHaveAttribute("type", "date");
  });
});

describe("date style switch", () => {
  it("is in the header and is remembered in this browser", async () => {
    mockFetch({ "GET /auth/me": () => ({ body: TEST_USER }) });
    renderLoggedIn(<Layout />);
    await userEvent.click(await screen.findByRole("button", { name: /Test Manager/ }));      // the user menu holds it
    const select = screen.getByLabelText("Show dates as");
    expect(select).toHaveValue("ad");                                    // tests start in AD (test/setup.ts)
    await userEvent.selectOptions(select, "bs_np");
    expect(localStorage.getItem("smart-inventory.date-style")).toBe("bs_np");
    localStorage.removeItem("smart-inventory.date-style");
  });
});
