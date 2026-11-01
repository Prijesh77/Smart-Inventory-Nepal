import { useState, type FormEvent } from "react";

import { api, ApiError } from "../../api/client";
import type { ForecastModel, ForecastRun } from "../../api/types";
import { SelectField, TextField } from "../../components/fields";
import { Badge, Button, EmptyState, ErrorMessage, Spinner } from "../../components/ui";
import { fmtDate, fmtDateTime, fmtInt, fmtPct } from "../../lib/format";
import { waitForRun } from "../../lib/runs";

export const MODEL_LABEL: Record<string, string> = {
  random_forest_v1: "Random Forest",
  moving_avg_28: "28-day moving average",
  moving_avg_7: "7-day moving average",
  seasonal_naive_7: "Seasonal naive (same weekday last week)",
  naive: "Naive (repeat last day)",
};

const STATUS_TONE = { pending: "gray", running: "blue", completed: "green", failed: "red" } as const;

export function RunsTable({ runs, selectedId, onSelect }:
  { runs: ForecastRun[]; selectedId: number | null; onSelect: (run: ForecastRun) => void }) {
  if (!runs.length) return <EmptyState title="No forecast runs yet" />;
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-sm">
        <thead className="text-left text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <th scope="col" className="py-2 pr-4 font-medium">Run</th>
            <th scope="col" className="py-2 pr-4 font-medium">Model</th>
            <th scope="col" className="py-2 pr-4 font-medium">Forecast from</th>
            <th scope="col" className="py-2 pr-4 text-right font-medium">Days</th>
            <th scope="col" className="py-2 pr-4 font-medium">Status</th>
            <th scope="col" className="py-2 pr-4 text-right font-medium">Units predicted</th>
            <th scope="col" className="py-2 pr-4 font-medium">Created</th>
            <th scope="col" className="py-2 font-medium"><span className="sr-only">Show</span></th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {runs.map((r) => (
            <tr key={r.id} className={r.id === selectedId ? "bg-brand-50" : ""}>
              <td className="py-2 pr-4 font-medium">#{r.id}</td>
              <td className="py-2 pr-4">{MODEL_LABEL[r.model_name] ?? r.model_name}</td>
              <td className="py-2 pr-4">{fmtDate(r.origin_date)}</td>
              <td className="py-2 pr-4 text-right tabular-nums">{r.horizon_days}</td>
              <td className="py-2 pr-4">
                <Badge tone={STATUS_TONE[r.status]}>{r.status}</Badge>
                {r.error_message && <p className="mt-1 max-w-xs text-xs text-red-700">{r.error_message}</p>}
              </td>
              <td className="py-2 pr-4 text-right tabular-nums">{fmtInt(r.metrics?.total_units)}</td>
              <td className="whitespace-nowrap py-2 pr-4 text-slate-500" title={`Completed ${fmtDateTime(r.completed_at)}`}>
                {fmtDateTime(r.created_at)}
              </td>
              <td className="py-2 text-right">
                {r.status === "completed" && r.id !== selectedId &&
                  <Button variant="ghost" onClick={() => onSelect(r)}>Show</Button>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Start a forecast run and wait for it in the background. */
export function NewRunForm({ lastSalesDate, onDone, pollMs }:
  { lastSalesDate: string | null; onDone: (run: ForecastRun) => void; pollMs?: number }) {
  const [model, setModel] = useState<ForecastModel>("auto");
  const [horizon, setHorizon] = useState("28");
  const [origin, setOrigin] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setStatus("Forecasting every product…");
    try {
      const run = await api.post<ForecastRun>("/forecasts/runs", {
        model_name: model, horizon_days: Number(horizon), origin_date: origin || null });
      await waitForRun("/forecasts/runs", run.id, pollMs);
      onDone(await api.get<ForecastRun>(`/forecasts/runs/${run.id}`));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The forecast could not be created");
    } finally {
      setStatus(null);
    }
  }

  return (
    <form onSubmit={onSubmit} className="space-y-3">
      {error && <ErrorMessage message={error} />}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <SelectField id="model" label="Model" value={model} onChange={(e) => setModel(e.target.value as ForecastModel)}>
          <option value="auto">Best available (recommended)</option>
          <option value="random_forest_v1">Random Forest (trained on this shop's sales)</option>
          <option value="moving_avg_28">28-day moving average (baseline)</option>
        </SelectField>
        <SelectField id="horizon" label="Forecast length" value={horizon} onChange={(e) => setHorizon(e.target.value)}>
          <option value="7">7 days</option>
          <option value="14">14 days</option>
          <option value="28">28 days</option>
        </SelectField>
        <TextField id="origin" label="Start date (optional)" type="date" value={origin} max={lastSalesDate ?? undefined}
                   onChange={(e) => setOrigin(e.target.value)}
                   hint="Empty = day after the last sales data. An earlier date lets you compare with what really sold." />
      </div>
      <div className="flex items-center gap-3">
        <Button type="submit" disabled={!!status}>{status ? "Running…" : "Create forecast"}</Button>
        {status && <Spinner label={status} />}
      </div>
    </form>
  );
}

export function testScoreText(run: ForecastRun): string | null {
  const m = run.metrics;
  if (m?.test_wape_28d === undefined) return null;
  return `Test-year accuracy of this model (all items, 28 days): WAPE ${fmtPct(m.test_wape_28d)}, bias ${fmtPct(m.test_bias_pct_28d, true)}`;
}
