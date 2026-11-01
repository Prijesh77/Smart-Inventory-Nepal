import { useState } from "react";

import { api } from "../../api/client";
import type { Evaluation } from "../../api/types";
import { FilterSelect } from "../../components/fields";
import { EmptyState, ErrorMessage, Spinner } from "../../components/ui";
import { useApi } from "../../hooks/useApi";
import { fmtPct, humanize } from "../../lib/format";
import { MODEL_LABEL } from "./ForecastRuns";

const CLASSES = ["all", "smooth", "erratic", "intermittent", "lumpy"];
const MODEL_ORDER = ["random_forest_v1", "moving_avg_28", "moving_avg_7", "seasonal_naive_7"];

/** For each column, the model with the lowest WAPE (ties: all of them). */
export function bestModels(rows: Evaluation[]): Record<string, string[]> {
  const best: Record<string, string[]> = {};
  CLASSES.forEach((cls) => {
    const scored = rows.filter((r) => r.demand_class === cls && r.wape !== null);
    const min = Math.min(...scored.map((r) => Number(r.wape)));
    best[cls] = scored.filter((r) => Number(r.wape) === min).map((r) => r.model_name);
  });
  return best;
}

export function ModelComparison() {
  const [period, setPeriod] = useState<"test" | "validation">("test");
  const [horizon, setHorizon] = useState("28");
  const { data, error, loading, reload } = useApi(
    (signal) => api.get<Evaluation[]>("/forecasts/evaluations", { period, horizon_days: horizon }, signal),
    [period, horizon],
  );
  const rows = data ?? [];
  const best = bestModels(rows);
  const models = MODEL_ORDER.filter((m) => rows.some((r) => r.model_name === m));
  const cell = (model: string, cls: string) => rows.find((r) => r.model_name === model && r.demand_class === cls);

  return (
    <>
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <FilterSelect label="Evaluation period" value={period} onChange={(v) => setPeriod(v as "test" | "validation")}>
          <option value="test">Test year (final, untouched during development)</option>
          <option value="validation">Validation period (used to choose the model)</option>
        </FilterSelect>
        <FilterSelect label="Horizon" value={horizon} onChange={setHorizon}>
          <option value="7">Days 1–7</option>
          <option value="14">Days 1–14</option>
          <option value="28">Days 1–28</option>
        </FilterSelect>
      </div>
      {error && <ErrorMessage message={error} onRetry={reload} />}
      {loading && !data && <Spinner label="Loading accuracy results…" />}
      {data && !rows.length && <EmptyState title="No evaluation results stored" />}
      {rows.length > 0 && (
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <caption className="mb-2 text-left text-xs text-slate-500">
              WAPE = total absolute error ÷ total actual sales (lower is better). Bias = over (+) or under (−) forecasting.
              Best WAPE per column is marked ★. Scored on this shop's last 28 days of sales, held back while training.
            </caption>
            <thead className="text-left text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th scope="col" className="py-2 pr-4 font-medium">Model</th>
                {CLASSES.map((c) => <th key={c} scope="col" className="py-2 pr-4 text-right font-medium">{c === "all" ? "All items" : humanize(c)}</th>)}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {models.map((m) => (
                <tr key={m}>
                  <th scope="row" className="py-2 pr-4 text-left font-medium text-slate-800">{MODEL_LABEL[m] ?? m}</th>
                  {CLASSES.map((c) => {
                    const r = cell(m, c);
                    const isBest = best[c]?.includes(m);
                    return (
                      <td key={c} className={`py-2 pr-4 text-right tabular-nums ${isBest ? "font-semibold text-emerald-700" : ""}`}>
                        {r ? <>{isBest && <span aria-label="best">★ </span>}{fmtPct(r.wape)}
                          <span className="block text-xs font-normal text-slate-500">bias {fmtPct(r.bias_pct, true)}</span></> : "—"}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
