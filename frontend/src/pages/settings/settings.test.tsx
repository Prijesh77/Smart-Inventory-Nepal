import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { ImportPreview, PolicyDefaults } from "../../api/types";
import { mockFetch, TEST_USER } from "../../test/fetchMock";
import { meRoute, renderLoggedIn } from "../../test/renderWithAuth";
import { toPolicy, validatePolicy } from "./PolicyForm";
import { buildForm } from "./SalesImport";
import { SettingsPage } from "./SettingsPage";

const POLICY: PolicyDefaults = { service_level: 0.95, review_period_days: 7, ordering_cost: 10, holding_cost_rate: 0.25,
  min_cycle_days: 7, max_cycle_days: 28, excess_cover_days: 60, forecast_horizons: [7, 14, 28] };

const GOOD: ImportPreview = { rows_total: 2, rows_valid: 2, rows_invalid: 0, would_add: 1, would_replace: 1, errors: [],
  errors_truncated: false, can_import: true,
  preview: [{ sku: "FOODS_1_013", sales_date: "2016-05-23", units: 4, unit_price: "1.50" }] };
const BAD: ImportPreview = { ...GOOD, rows_valid: 1, rows_invalid: 1, can_import: false,
  errors: [{ row: 3, column: "date", message: "Date '23/05/2016' is not YYYY-MM-DD" }] };

function routes(role: "admin" | "manager" | "viewer", extra = {}) {
  return {
    ...meRoute(role),
    "GET /settings/policy": () => ({ body: POLICY }),
    "GET /imports/jobs": () => ({ body: [] }),
    "GET /users": () => ({ body: [{ ...TEST_USER, role: role }, { ...TEST_USER, id: 2, email: "viewer@test.local", full_name: "Vee", role: "viewer" }] }),
    ...extra,
  };
}

const csv = () => new File(["sku,date,units\nFOODS_1_013,2016-05-23,4\n"], "sales.csv", { type: "text/csv" });

describe("policy rules", () => {
  const values = { service_level: "95", review_period_days: "7", ordering_cost: "10", holding_cost_rate: "25",
    min_cycle_days: "7", max_cycle_days: "28", excess_cover_days: "60", forecast_horizons: [28, 7] };

  it("match the API limits and convert percentages", () => {
    expect(validatePolicy(values)).toEqual({});
    expect(validatePolicy({ ...values, service_level: "100" }).service_level).toBeTruthy();
    expect(validatePolicy({ ...values, max_cycle_days: "5" }).max_cycle_days).toMatch(/at least the minimum/);
    expect(validatePolicy({ ...values, forecast_horizons: [] }).forecast_horizons).toBeTruthy();
    expect(toPolicy(values)).toMatchObject({ service_level: 0.95, holding_cost_rate: 0.25, forecast_horizons: [7, 28] });
  });

  it("sends the column mapping with the file", () => {
    const form = buildForm(csv(), { sku: "Item", date: " ", units: "Qty", price: "" });
    expect(form.get("sku_column")).toBe("Item");
    expect(form.get("date_column")).toBe("date");        // blank falls back to the default
    expect(form.get("price_column")).toBe("");
  });
});

describe("SettingsPage", () => {
  it("admins edit and save policy settings", async () => {
    const { calls } = mockFetch(routes("admin", { "PUT /settings/policy": () => ({ body: { ...POLICY, service_level: 0.98 } }) }));
    renderLoggedIn(<SettingsPage />, "/settings");
    const level = await screen.findByLabelText("Service level target (%)");
    await userEvent.clear(level);
    await userEvent.type(level, "98");
    await userEvent.click(screen.getByRole("button", { name: "Save settings" }));
    expect(await screen.findByText(/Settings saved/)).toBeInTheDocument();
    const body = JSON.parse(String(calls.find((c) => c.init?.method === "PUT")!.init!.body));
    expect(body.service_level).toBe(0.98);
  });

  it("managers see settings read-only and no user admin", async () => {
    mockFetch(routes("manager"));
    renderLoggedIn(<SettingsPage />, "/settings");
    expect(await screen.findByLabelText("Service level target (%)")).toBeDisabled();
    expect(screen.getByText("Only admins can change these settings.")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "User accounts" })).not.toBeInTheDocument();
  });

  it("viewers cannot import", async () => {
    mockFetch(routes("viewer"));
    renderLoggedIn(<SettingsPage />, "/settings");
    expect(await screen.findByText("Only managers and admins can import data.")).toBeInTheDocument();
  });

  it("lists row errors and does not offer to import a bad file", async () => {
    mockFetch(routes("manager", { "POST /imports/sales/preview": () => ({ body: BAD }) }));
    renderLoggedIn(<SettingsPage />, "/settings");
    await userEvent.upload(await screen.findByLabelText(/CSV file/), csv());
    await userEvent.click(screen.getByRole("button", { name: "Check file" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Nothing will be imported while any row has an error");
    expect(within(alert).getByText("Date '23/05/2016' is not YYYY-MM-DD")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Import/ })).not.toBeInTheDocument();
  });

  it("checks a good file, then imports it", async () => {
    let imported = false;
    const { calls } = mockFetch(routes("manager", {
      "POST /imports/sales/preview": () => ({ body: GOOD }),
      "POST /imports/sales": () => { imported = true; return { status: 201, body: { id: 1, filename: "sales.csv", import_type: "sales",
        status: "completed", rows_total: 2, rows_valid: 2, rows_invalid: 0, errors: { added: 1, replaced: 1 }, created_at: "2026-10-29T12:00:00Z" } }; },
      "GET /imports/jobs": () => ({ body: imported ? [{ id: 1, filename: "sales.csv", import_type: "sales", status: "completed",
        rows_total: 2, rows_valid: 2, rows_invalid: 0, errors: { added: 1, replaced: 1 }, created_at: "2026-10-29T12:00:00Z" }] : [] }),
    }));
    renderLoggedIn(<SettingsPage />, "/settings");
    await userEvent.upload(await screen.findByLabelText(/CSV file/), csv());
    await userEvent.click(screen.getByRole("button", { name: "Check file" }));
    expect(await screen.findByText(/1 existing day\(s\) will be replaced/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Import 2 rows" }));
    expect(await screen.findByText("Imported sales.csv: 1 rows added, 1 replaced.")).toBeInTheDocument();
    expect(await screen.findByText("1 added, 1 replaced")).toBeInTheDocument();        // history refreshed
    const upload = calls.find((c) => c.url.endsWith("/imports/sales/preview"))!;
    expect((upload.init!.body as FormData).get("file")).toBeInstanceOf(File);
  });

  it("refuses files over 5 MB before uploading", async () => {
    const { calls } = mockFetch(routes("manager"));
    renderLoggedIn(<SettingsPage />, "/settings");
    const big = new File([new Uint8Array(5 * 1024 * 1024 + 1)], "big.csv", { type: "text/csv" });
    await userEvent.upload(await screen.findByLabelText(/CSV file/), big);
    expect(await screen.findByRole("alert")).toHaveTextContent("larger than 5 MB");
    expect(screen.getByRole("button", { name: "Check file" })).toBeDisabled();
    expect(calls.some((c) => c.url.includes("/imports"))).toBe(calls.some((c) => c.url.endsWith("/imports/jobs")));
  });

  it("admins manage accounts but cannot change their own role", async () => {
    const { calls } = mockFetch(routes("admin", { "PATCH /users/2": () => ({ body: {} }) }));
    renderLoggedIn(<SettingsPage />, "/settings");
    expect(await screen.findByLabelText(`Role for ${TEST_USER.email}`)).toBeDisabled();
    await userEvent.selectOptions(screen.getByLabelText("Role for viewer@test.local"), "manager");
    await waitFor(() => expect(calls.some((c) => c.init?.method === "PATCH")).toBe(true));
    expect(JSON.parse(String(calls.find((c) => c.init?.method === "PATCH")!.init!.body))).toEqual({ role: "manager" });
    expect(await screen.findByText("viewer@test.local is now manager.")).toBeInTheDocument();
  });
});
