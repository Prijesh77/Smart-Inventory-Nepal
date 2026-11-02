import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { api } from "../../api/client";
import type { DashboardSummary, ForecastRun, ProductForecast } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { ForecastChart, windowWape } from "../../components/charts/ForecastChart";
import { ProductPicker } from "../../components/ProductPicker";
import { Card, EmptyState, ErrorMessage, PageHeader, Skeleton } from "../../components/ui";
import { useApi } from "../../hooks/useApi";
import { fmtDate, fmtDecimal, fmtPct } from "../../lib/format";
import { ModelComparison } from "./ModelComparison";
import { MODEL_LABEL, NewRunForm, RunsTable, testScoreText } from "./ForecastRuns";
import { ShopModelCard } from "./ShopModelCard";

export function ForecastsPage({ pollMs }: { pollMs?: number }) {
  const { can } = useAuth();
  const [params, setParams] = useSearchParams();
  const productId = params.get("product");
  const runParam = params.get("run");
  const [product, setProduct] = useState<{ id: number; sku: string } | null>(null);
  const [trainedCount, setTrainedCount] = useState(0);     // refreshes the accuracy table after training

  const runs = useApi((signal) => api.get<ForecastRun[]>("/forecasts/runs", { limit: 20 }, signal));
  const summary = useApi((signal) => api.get<DashboardSummary>("/dashboard/summary", undefined, signal));
  const selectedRun = runs.data?.find((r) => String(r.id) === runParam)
    ?? runs.data?.find((r) => r.status === "completed") ?? null;

  // Default product: the first one in the list, so the chart is never empty without reason.
  const fallback = useApi((signal) => productId ? Promise.resolve(null)
    : api.get<{ items: { id: number; sku: string }[] }>("/products", { page_size: 1 }, signal), [productId]);
  const chosenId = productId ? Number(productId) : fallback.data?.items[0]?.id ?? null;

  const forecast = useApi(
    (signal) => chosenId && selectedRun
      ? api.get<ProductForecast>(`/forecasts/products/${chosenId}`, { run_id: selectedRun.id }, signal)
      : Promise.resolve(null),
    [chosenId, selectedRun?.id],
  );

  function setParam(key: string, value: string) {
    const next = new URLSearchParams(params);
    next.set(key, value);
    setParams(next, { replace: true });
  }

  const f = forecast.data;
  const wape = f ? windowWape(f) : null;
  const days = f?.forecast.length ?? 0;

  return (
    <>
      <PageHeader title="Demand forecasting"
                  description="Actual sales and predicted demand per product, plus how accurate each model has been." />

      <Card title="Actual sales vs forecast">
        <div className="mb-4 flex flex-wrap items-end gap-4">
          <ProductPicker label="Product" selected={product ?? (f ? { id: f.product_id, sku: f.sku } : null)}
                         onSelect={(p) => { setProduct(p); setParam("product", String(p.id)); }} />
          {selectedRun && (
            <p className="text-sm text-slate-600">
              Run #{selectedRun.id}: {MODEL_LABEL[selectedRun.model_name]}, {selectedRun.horizon_days} days from{" "}
              {fmtDate(selectedRun.origin_date)}
            </p>
          )}
        </div>
        {runs.loading && !runs.data && <Skeleton label="Loading forecast runs…" />}
        {runs.data && !selectedRun && (
          <EmptyState icon="trend" title="No completed forecast yet">
            {can("admin", "manager") ? "Create one below." : "Ask a manager to create one."}
          </EmptyState>
        )}
        {forecast.error && <ErrorMessage message={forecast.error} onRetry={forecast.reload} />}
        {forecast.loading && selectedRun && !f && <Skeleton label="Loading forecast…" />}
        {f && f.forecast.length === 0 && (
          <EmptyState title={`No forecast for ${f.sku} in this run`}>The product may be inactive or have no sales history.</EmptyState>
        )}
        {f && f.forecast.length > 0 && (
          <>
            <div className="mb-3 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
              <Figure label={`Predicted, next ${days} days`} value={`${fmtDecimal(f.total_forecast)} units`} />
              <Figure label="Predicted per day" value={fmtDecimal(f.total_forecast / days)} />
              <Figure label="Actual per day, last 8 weeks" value={fmtDecimal(
                f.history.filter((d) => d.is_available).reduce((s, d) => s + d.units, 0)
                / Math.max(1, f.history.filter((d) => d.is_available).length))} />
              <Figure label="Error on this window (WAPE)" value={wape === null ? "Not known yet" : fmtPct(wape)} />
            </div>
            <ForecastChart data={f} />
            <p className="mt-2 text-xs text-slate-500">
              Blue = what actually sold; dashed orange = forecast; shaded area = forecast period.
              {f.actual_in_window.length > 0 && " Green = what actually sold during the forecast period (back-dated run)."}
              {" "}<Link to={`/products/${f.product_id}`} className="text-brand-600 hover:underline">Product details</Link>
            </p>
            {f.run.params?.model_choice && <p className="mt-1 text-xs text-slate-500">{f.run.params.model_choice}</p>}
            {testScoreText(f.run) && <p className="mt-1 text-xs text-slate-500">{testScoreText(f.run)}</p>}
            {f.run.params?.assumptions && (
              <details className="mt-2 text-xs text-slate-500">
                <summary className="cursor-pointer">Assumptions behind this forecast</summary>
                <ul className="ml-4 mt-1 list-disc">{f.run.params.assumptions.map((a) => <li key={a}>{a}</li>)}</ul>
              </details>
            )}
          </>
        )}
      </Card>

      <div className="mt-6 grid grid-cols-1 gap-6 xl:grid-cols-5">
        <Card title="Forecast runs" className="xl:col-span-3">
          {runs.error && <ErrorMessage message={runs.error} onRetry={runs.reload} />}
          {runs.data && <RunsTable runs={runs.data} selectedId={selectedRun?.id ?? null}
                                   onSelect={(r) => setParam("run", String(r.id))} />}
        </Card>
        {can("admin", "manager") && (
          <Card title="Create a forecast" className="xl:col-span-2">
            <NewRunForm lastSalesDate={summary.data?.as_of ?? null} pollMs={pollMs}
                        onDone={(run) => { runs.reload(); setParam("run", String(run.id)); }} />
          </Card>
        )}
      </div>

      <Card title="This shop's forecast model" className="mt-6">
        <ShopModelCard canTrain={can("admin", "manager")} onTrained={() => setTrainedCount((n) => n + 1)} />
      </Card>

      <Card title="Model accuracy comparison" className="mt-6">
        <ModelComparison key={trainedCount} />
      </Card>
    </>
  );
}

function Figure({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md bg-slate-50 p-3">
      <p className="text-xs text-slate-500">{label}</p>
      <p className="font-semibold tabular-nums text-slate-800">{value}</p>
    </div>
  );
}
