import { useState, type FormEvent } from "react";

import { api, ApiError } from "../../api/client";
import type { PolicyDefaults } from "../../api/types";
import { TextField } from "../../components/fields";
import { Button, ErrorMessage, SimulatedTag } from "../../components/ui";
import { currencySymbol, inputToMoney, moneyToInput, toDisplay } from "../../lib/currency";
import { fmtMoney, fmtPct } from "../../lib/format";

interface Values {
  service_level: string;          // percent, e.g. "95"
  review_period_days: string;
  ordering_cost: string;
  holding_cost_rate: string;      // percent per year
  min_cycle_days: string;
  max_cycle_days: string;
  excess_cover_days: string;
  forecast_horizons: number[];
}

type Errors = Partial<Record<keyof Values, string>>;

const toValues = (p: PolicyDefaults): Values => ({
  service_level: String(+(p.service_level * 100).toFixed(1)), review_period_days: String(p.review_period_days),
  ordering_cost: moneyToInput(p.ordering_cost), holding_cost_rate: String(+(p.holding_cost_rate * 100).toFixed(1)),
  min_cycle_days: String(p.min_cycle_days), max_cycle_days: String(p.max_cycle_days),
  excess_cover_days: String(p.excess_cover_days), forecast_horizons: p.forecast_horizons,
});

const whole = (v: string, min: number, max: number) => /^\d+$/.test(v) && +v >= min && +v <= max;
const number = (v: string, min: number, max: number) => v.trim() !== "" && !Number.isNaN(+v) && +v >= min && +v <= max;

/** The same limits the API checks (app/api/v1/settings.py). */
export function validatePolicy(v: Values): Errors {
  const e: Errors = {};
  if (!number(v.service_level, 50, 99.9)) e.service_level = "Between 50 and 99.9";
  if (!whole(v.review_period_days, 1, 28)) e.review_period_days = "Whole days, 1–28";
  if (!number(v.ordering_cost, 0, toDisplay(10000))) e.ordering_cost = `Between ${fmtMoney(0)} and ${fmtMoney(10000)}`;
  if (!number(v.holding_cost_rate, 0.1, 100)) e.holding_cost_rate = "Between 0.1 and 100";
  if (!whole(v.min_cycle_days, 1, 90)) e.min_cycle_days = "Whole days, 1–90";
  if (!whole(v.max_cycle_days, 1, 180)) e.max_cycle_days = "Whole days, 1–180";
  else if (!e.min_cycle_days && +v.max_cycle_days < +v.min_cycle_days) e.max_cycle_days = "Must be at least the minimum";
  if (!whole(v.excess_cover_days, 7, 365)) e.excess_cover_days = "Whole days, 7–365";
  if (!v.forecast_horizons.length) e.forecast_horizons = "Choose at least one";
  return e;
}

export function toPolicy(v: Values): PolicyDefaults {
  return {
    service_level: +v.service_level / 100, review_period_days: +v.review_period_days, ordering_cost: +inputToMoney(v.ordering_cost),
    holding_cost_rate: +v.holding_cost_rate / 100, min_cycle_days: +v.min_cycle_days, max_cycle_days: +v.max_cycle_days,
    excess_cover_days: +v.excess_cover_days, forecast_horizons: [...v.forecast_horizons].sort((a, b) => a - b),
  };
}

export function PolicyForm({ policy, canEdit, onSaved }:
  { policy: PolicyDefaults; canEdit: boolean; onSaved: (p: PolicyDefaults) => void }) {
  const [values, setValues] = useState<Values>(() => toValues(policy));
  const [errors, setErrors] = useState<Errors>({});
  const [serverError, setServerError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const set = (field: keyof Values) => (e: { target: { value: string } }) => setValues((v) => ({ ...v, [field]: e.target.value }));

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const found = validatePolicy(values);
    setErrors(found);
    setServerError(null);
    if (Object.keys(found).length) return;
    setSaving(true);
    try {
      onSaved(await api.put<PolicyDefaults>("/settings/policy", toPolicy(values)));
    } catch (err) {
      setServerError(err instanceof ApiError ? err.message : "Could not save the settings");
    } finally {
      setSaving(false);
    }
  }

  const field = (id: keyof Values, label: string, hint: string) => (
    <TextField id={`policy-${id}`} label={label} hint={hint} inputMode="decimal" disabled={!canEdit}
               value={values[id] as string} onChange={set(id)} error={errors[id]} />
  );

  return (
    <form onSubmit={onSubmit} noValidate className="space-y-4">
      {!canEdit && <p className="rounded-md bg-slate-50 p-3 text-sm text-slate-600">Only admins can change these settings.</p>}
      {serverError && <ErrorMessage message={serverError} />}
      <fieldset className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <legend className="mb-2 text-sm font-semibold text-slate-800">Reorder policy</legend>
        {field("service_level", "Service level target (%)", "Chance of no stockout per period; higher = more safety stock")}
        {field("review_period_days", "Review period (days)", "How often stock is checked and orders placed")}
        {field("excess_cover_days", "Excess stock threshold (days of cover)", "Above this, stock is flagged as excess")}
        {field("min_cycle_days", "Smallest order (days of demand)", "Lower limit on order size")}
        {field("max_cycle_days", "Largest order (days of demand)", "Upper limit on order size, whatever EOQ says")}
      </fieldset>
      <fieldset className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <legend className="mb-2 flex items-center gap-2 text-sm font-semibold text-slate-800">Cost assumptions <SimulatedTag /></legend>
        {field("ordering_cost", `Cost per order (${currencySymbol()})`, "Fixed cost of placing one order line")}
        {field("holding_cost_rate", "Holding cost (% of unit cost per year)", "Cost of keeping stock on the shelf")}
      </fieldset>
      <fieldset>
        <legend className="text-sm font-semibold text-slate-800">Forecast lengths offered</legend>
        <div className="mt-2 flex gap-4">
          {[7, 14, 28].map((h) => (
            <label key={h} className="flex items-center gap-1.5 text-sm">
              <input type="checkbox" disabled={!canEdit} checked={values.forecast_horizons.includes(h)}
                     onChange={(e) => setValues((v) => ({ ...v, forecast_horizons: e.target.checked
                       ? [...v.forecast_horizons, h] : v.forecast_horizons.filter((x) => x !== h) }))} />
              {h} days
            </label>
          ))}
        </div>
        {errors.forecast_horizons && <p className="mt-1 text-xs text-red-700">{errors.forecast_horizons}</p>}
      </fieldset>
      <p className="text-xs text-slate-500">
        These defaults are used by new recommendation runs (currently {fmtPct(policy.service_level)} service level).
        Existing runs keep the settings they were created with.
      </p>
      {canEdit && (
        <div className="flex justify-end border-t border-slate-100 pt-4">
          <Button type="submit" disabled={saving}>{saving ? "Saving…" : "Save settings"}</Button>
        </div>
      )}
    </form>
  );
}
