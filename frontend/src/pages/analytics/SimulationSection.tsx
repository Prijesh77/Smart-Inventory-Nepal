import { useState, type FormEvent } from "react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { api, ApiError } from "../../api/client";
import type { SimPolicy, SimulationRow, SimulationRun } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { TextField } from "../../components/fields";
import { Button, EmptyState, ErrorMessage, SimulatedTag, Spinner } from "../../components/ui";
import { useApi } from "../../hooks/useApi";
import { AXIS, GRID, SERIES } from "../../lib/colors";
import { currencySymbol, inputToMoney, moneyToInput } from "../../lib/currency";
import { fmtDateTime, fmtInt, fmtMoney, fmtPct } from "../../lib/format";
import { waitForRun } from "../../lib/runs";

export const POLICY_STYLE: Record<SimPolicy, { label: string; color: string; dash?: string }> = {
  baseline_demand_sd: { label: "Textbook baseline", color: SERIES.gray, dash: "5 4" },
  engine_ma28: { label: "Engine + 28-day average", color: SERIES.blue },
  engine_rf: { label: "Engine + Random Forest", color: SERIES.orange },
};
const POLICIES = Object.keys(POLICY_STYLE) as SimPolicy[];
const LEVELS = [0.6, 0.7, 0.8, 0.9, 0.95, 0.98, 0.99];

/** Cost-vs-service curves: x = achieved fill rate, y = total cost, one line per policy (sorted by fill rate). */
export function curves(summary: SimulationRow[]) {
  const all = summary.filter((r) => r.demand_class === "all");
  return POLICIES.map((p) => ({
    policy: p,
    points: all.filter((r) => r.policy === p && r.fill_rate !== null)
      .map((r) => ({ fill: Number((r.fill_rate! * 100).toFixed(2)), cost: r.total_cost, level: r.service_level }))
      .sort((a, b) => a.fill - b.fill),
  }));
}

function CostServiceChart({ summary }: { summary: SimulationRow[] }) {
  const lines = curves(summary);
  return (
    <div role="img" aria-label="Simulated total cost against achieved fill rate for each policy">
      <ResponsiveContainer width="100%" height={300}>
        <LineChart margin={{ top: 8, right: 16, bottom: 16, left: 8 }}>
          <CartesianGrid stroke={GRID} />
          <XAxis type="number" dataKey="fill" domain={["auto", "auto"]} tickFormatter={(v) => `${v}%`}
                 tick={{ fill: AXIS, fontSize: 12 }} label={{ value: "Fill rate (share of demand served)", position: "insideBottom", offset: -8, fill: AXIS, fontSize: 12 }} />
          <YAxis type="number" dataKey="cost" domain={["auto", "auto"]} width={64} tickFormatter={(v) => fmtMoney(v, true)}
                 tick={{ fill: AXIS, fontSize: 12 }} />
          <Tooltip formatter={(v, n) => [n === "cost" ? fmtMoney(Number(v)) : v, "Total cost"]}
                   labelFormatter={(v) => `Fill rate ${v}%`} />
          <Legend verticalAlign="top" align="right" height={28} wrapperStyle={{ fontSize: 12 }} />
          {lines.map((l) => (
            <Line key={l.policy} data={l.points} dataKey="cost" name={POLICY_STYLE[l.policy].label}
                  stroke={POLICY_STYLE[l.policy].color} strokeDasharray={POLICY_STYLE[l.policy].dash} strokeWidth={2.5}
                  dot={{ r: 4 }} isAnimationActive={false} />
          ))}
        </LineChart>
      </ResponsiveContainer>
      <p className="text-xs text-slate-500">Each dot is one service-level target. Lower and further right is better: more demand served for less cost.</p>
    </div>
  );
}

function ResultsTable({ summary }: { summary: SimulationRow[] }) {
  const rows = summary.filter((r) => r.demand_class === "all")
    .sort((a, b) => POLICIES.indexOf(a.policy) - POLICIES.indexOf(b.policy) || a.service_level - b.service_level);
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-sm">
        <thead className="text-left text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <th scope="col" className="py-2 pr-3 font-medium">Policy</th>
            <th scope="col" className="py-2 pr-3 text-right font-medium">Target</th>
            <th scope="col" className="py-2 pr-3 text-right font-medium">Fill rate</th>
            <th scope="col" className="py-2 pr-3 text-right font-medium">Units lost</th>
            <th scope="col" className="py-2 pr-3 text-right font-medium">Avg stock value</th>
            <th scope="col" className="py-2 pr-3 text-right font-medium">Orders</th>
            <th scope="col" className="py-2 pr-3 text-right font-medium">Holding</th>
            <th scope="col" className="py-2 pr-3 text-right font-medium">Ordering</th>
            <th scope="col" className="py-2 text-right font-medium">Total cost</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.map((r) => (
            <tr key={`${r.policy}-${r.service_level}`}>
              <td className="py-1.5 pr-3">{POLICY_STYLE[r.policy].label}</td>
              <td className="py-1.5 pr-3 text-right tabular-nums">{fmtPct(r.service_level)}</td>
              <td className="py-1.5 pr-3 text-right tabular-nums">{r.fill_rate === null ? "—" : `${(r.fill_rate * 100).toFixed(2)}%`}</td>
              <td className="py-1.5 pr-3 text-right tabular-nums">{fmtInt(r.units_lost)}</td>
              <td className="py-1.5 pr-3 text-right tabular-nums">{fmtMoney(r.avg_inventory_value)}</td>
              <td className="py-1.5 pr-3 text-right tabular-nums">{fmtInt(r.n_orders)}</td>
              <td className="py-1.5 pr-3 text-right tabular-nums">{fmtMoney(r.holding_cost)}</td>
              <td className="py-1.5 pr-3 text-right tabular-nums">{fmtMoney(r.ordering_cost)}</td>
              <td className="py-1.5 text-right font-medium tabular-nums">{fmtMoney(r.total_cost)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Comparisons({ run }: { run: SimulationRun }) {
  const items = run.results?.matched_comparisons.filter((m) => m.pct_diff !== null) ?? [];
  if (!items.length) return <p className="text-sm text-slate-500">Choose at least two service levels to compare policies at the same fill rate.</p>;
  return (
    <ul className="space-y-2 text-sm">
      {items.map((m) => (
        <li key={`${m.policy}-${m.reference}`} className="rounded-md bg-slate-50 p-3">
          At the same fill rate ({(m.fill_rate! * 100).toFixed(2)}%), <strong>{POLICY_STYLE[m.policy].label}</strong> costs{" "}
          <strong className={m.pct_diff! < 0 ? "text-emerald-700" : "text-red-700"}>
            {fmtPct(Math.abs(m.pct_diff!))} {m.pct_diff! < 0 ? "less" : "more"}
          </strong>{" "}than {POLICY_STYLE[m.reference].label} ({fmtMoney(m.policy_value)} vs {fmtMoney(m.reference_value)}).
        </li>
      ))}
    </ul>
  );
}

function RunForm({ onDone, pollMs }: { onDone: (run: SimulationRun) => void; pollMs?: number }) {
  const [levels, setLevels] = useState<number[]>([0.8, 0.9, 0.95, 0.98]);
  const [ordering, setOrdering] = useState(() => moneyToInput(10));
  const [holding, setHolding] = useState("25");
  const [uncertain, setUncertain] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const oc = ordering.trim() === "" ? NaN : Number(inputToMoney(ordering));     // dollars, like the API
    const hr = Number(holding);
    if (!levels.length) return setError("Choose at least one service level");
    if (!(oc >= 0 && oc <= 1000)) return setError(`Ordering cost must be between ${fmtMoney(0)} and ${fmtMoney(1000)}`);
    if (!(hr >= 1 && hr <= 100)) return setError("Holding cost must be between 1% and 100% per year");
    setError(null);
    setStatus("Simulating 267 products over the test year (about 10–30 seconds)…");
    try {
      const run = await api.post<SimulationRun>("/simulations", {
        name: "Run from the app", service_levels: levels, ordering_cost: oc, holding_cost_rate: hr / 100, uncertain_lead_time: uncertain });
      await waitForRun("/simulations", run.id, pollMs, 300_000);
      onDone(await api.get<SimulationRun>(`/simulations/${run.id}`));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The simulation could not run");
    } finally {
      setStatus(null);
    }
  }

  return (
    <form onSubmit={onSubmit} noValidate className="space-y-3">
      {error && <ErrorMessage message={error} />}
      <fieldset>
        <legend className="text-sm font-medium text-slate-700">Service-level targets</legend>
        <div className="mt-1 flex flex-wrap gap-3">
          {LEVELS.map((l) => (
            <label key={l} className="flex items-center gap-1.5 text-sm">
              <input type="checkbox" checked={levels.includes(l)}
                     onChange={(e) => setLevels((all) => e.target.checked ? [...all, l].sort() : all.filter((x) => x !== l))} />
              {fmtPct(l)}
            </label>
          ))}
        </div>
      </fieldset>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <TextField id="sim-ordering" label={`Ordering cost per order (${currencySymbol()})`} inputMode="decimal" value={ordering} onChange={(e) => setOrdering(e.target.value)} />
        <TextField id="sim-holding" label="Holding cost (% of unit cost per year)" inputMode="decimal" value={holding} onChange={(e) => setHolding(e.target.value)} />
      </div>
      <label className="flex items-center gap-2 text-sm text-slate-700">
        <input type="checkbox" checked={uncertain} onChange={(e) => setUncertain(e.target.checked)} />
        Real lead times vary around each supplier's average (policies still plan with the average)
      </label>
      <div className="flex items-center gap-3">
        <Button type="submit" disabled={!!status}>{status ? "Running…" : "Run simulation"}</Button>
        {status && <Spinner label={status} />}
      </div>
    </form>
  );
}

export function SimulationSection({ pollMs }: { pollMs?: number }) {
  const { can } = useAuth();
  const runs = useApi((signal) => api.get<SimulationRun[]>("/simulations", { limit: 20 }, signal));
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const completed = runs.data?.filter((r) => r.status === "completed") ?? [];
  const run = completed.find((r) => r.id === selectedId) ?? completed[0] ?? null;
  const failed = runs.data?.find((r) => r.status === "failed" && (!run || r.id > run.id));

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start gap-3 rounded-md bg-violet-50 p-3 text-sm text-violet-900 ring-1 ring-violet-200">
        <SimulatedTag />
        <p className="flex-1">
          These are <strong>simulation results</strong>, not results from a real store. Demand is real M5 sales for 267
          products over the test year (25 May 2015 – 22 May 2016); stock, costs and supplier lead times are generated
          assumptions. Unmet demand counts as a lost sale.
        </p>
      </div>
      {runs.error && <ErrorMessage message={runs.error} onRetry={runs.reload} />}
      {runs.loading && !runs.data && <Spinner />}
      {failed && <ErrorMessage message={`Latest simulation failed: ${failed.error_message ?? "unknown reason"}`} />}
      {runs.data && !run && <EmptyState title="No simulation results yet">{can("admin", "manager") ? "Run one below." : "Ask a manager to run one."}</EmptyState>}
      {run?.results && (
        <>
          <div className="flex flex-wrap items-center gap-3 text-sm text-slate-600">
            <label>
              <span className="sr-only">Simulation run</span>
              <select aria-label="Simulation run" value={run.id} onChange={(e) => setSelectedId(Number(e.target.value))}
                      className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm">
                {completed.map((r) => <option key={r.id} value={r.id}>Run #{r.id} · {fmtDateTime(r.created_at)}</option>)}
              </select>
            </label>
            <span>Ordering {fmtMoney(run.params.ordering_cost)}/order · holding {fmtPct(run.params.holding_cost_rate)}/year ·
              {run.params.uncertain_lead_time ? " uncertain" : " fixed"} lead times · {run.results.items} products, {run.results.days} days</span>
          </div>
          <CostServiceChart summary={run.results.summary} />
          <Comparisons run={run} />
          <details>
            <summary className="cursor-pointer text-sm font-medium text-slate-700">All figures (all products)</summary>
            <div className="mt-3"><ResultsTable summary={run.results.summary} /></div>
          </details>
        </>
      )}
      {can("admin", "manager") && (
        <div className="border-t border-slate-100 pt-4">
          <h3 className="mb-2 text-sm font-semibold text-slate-800">Run a new simulation</h3>
          <RunForm pollMs={pollMs} onDone={(r) => { runs.reload(); setSelectedId(r.id); }} />
        </div>
      )}
    </div>
  );
}
