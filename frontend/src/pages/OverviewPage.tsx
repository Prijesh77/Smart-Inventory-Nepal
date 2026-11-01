import { useState } from "react";
import { Link } from "react-router-dom";

import { api, ApiError } from "../api/client";
import type { DashboardSummary, RiskCategory, StockStatus, TransactionRow } from "../api/types";
import { useAuth, useIsDemoShop } from "../auth/AuthContext";
import { CategoryBars } from "../components/charts/CategoryBars";
import { SalesTrendChart } from "../components/charts/SalesTrendChart";
import { StatCard } from "../components/StatCard";
import { Badge, Button, Card, EmptyState, ErrorMessage, PageHeader, SimulatedTag, Spinner } from "../components/ui";
import { useApi } from "../hooks/useApi";
import { RISK_STYLE, STOCK_STATUS_STYLE } from "../lib/colors";
import { fmtDate, fmtDateTime, fmtInt, fmtMoney, fmtPct, humanize } from "../lib/format";
import { runPlanning } from "../lib/runs";

const STOCK_ORDER: StockStatus[] = ["out_of_stock", "low", "ok", "no_recent_demand"];
const RISK_ORDER: RiskCategory[] = ["critical_stockout_risk", "reorder_soon", "healthy", "excess_inventory",
  "insufficient_data"];

export function OverviewPage({ pollMs }: { pollMs?: number }) {
  const { can } = useAuth();
  const demo = useIsDemoShop();
  const { data, error, loading, reload } = useApi((signal) => api.get<DashboardSummary>("/dashboard/summary", undefined, signal));
  const [planning, setPlanning] = useState<string | null>(null);
  const [planError, setPlanError] = useState<string | null>(null);

  async function startPlanning() {
    setPlanError(null);
    try {
      await runPlanning(setPlanning, pollMs);
      reload();
    } catch (err) {
      setPlanError(err instanceof ApiError ? err.message : "Planning failed");
    } finally {
      setPlanning(null);
    }
  }

  const header = (
    <PageHeader
      title="Overview"
      description={data?.as_of ? `Sales data up to ${fmtDate(data.as_of)}. All figures are calculated live from the database.` : undefined}
      actions={can("admin", "manager") && (
        <Button onClick={startPlanning} disabled={!!planning}>
          {planning ? "Running…" : "Run forecast & recommendations"}
        </Button>
      )}
    />
  );

  if (loading && !data) return <>{header}<Spinner label="Loading the overview…" /></>;
  if (error && !data) return <>{header}<ErrorMessage message={error} onRetry={reload} /></>;
  if (!data) return null;

  const rec = data.recommendations;
  const stockBars = STOCK_ORDER.map((s) => ({ key: s, label: STOCK_STATUS_STYLE[s].label,
    value: data.stock_status[s] ?? 0, color: STOCK_STATUS_STYLE[s].color }));
  const riskBars = RISK_ORDER.map((r) => ({ key: r, label: RISK_STYLE[r].label,
    value: rec?.counts[r] ?? 0, color: RISK_STYLE[r].color }));

  return (
    <>
      {header}
      {planning && <div className="mb-4"><Spinner label={planning} /></div>}
      {planError && <div className="mb-4"><ErrorMessage message={planError} /></div>}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Active products" value={fmtInt(data.active_products)} icon="box"
                  detail={`${fmtInt(data.units_on_hand)} units on hand`} />
        <StatCard label="Inventory value (at cost)" value={fmtMoney(data.inventory_value, true)} simulated icon="money"
                  detail={data.products_without_cost ? `${data.products_without_cost} products have no cost` : "Stock × unit cost"} />
        <StatCard label="Products to reorder" value={rec ? fmtInt(rec.products_to_reorder) : "—"} icon="cart"
                  tone={rec?.products_to_reorder ? "warning" : "default"}
                  detail={rec ? `Estimated order cost ${fmtMoney(rec.estimated_order_cost)}${demo ? " (simulated)" : ""}` : "No recommendations yet"} />
        <StatCard label="Critical stockout risk" value={rec ? fmtInt(rec.critical) : "—"} icon="alert"
                  tone={rec?.critical ? "critical" : "default"}
                  detail={rec ? `${fmtInt(rec.excess)} products with excess stock` : "Run recommendations to see risks"} />
        <StatCard label="Units sold, last 28 days" value={data.sales ? fmtInt(data.sales.last_28_days_units) : "—"} icon="chart"
                  detail={data.sales ? `${fmtPct(data.sales.change_vs_previous_28_days, true)} vs previous 28 days · ${fmtMoney(data.sales.last_28_days_revenue, true)} revenue` : undefined} />
        <StatCard label="Forecast, next 28 days" value={data.forecast?.predicted_units.next_28_days !== undefined ? fmtInt(data.forecast.predicted_units.next_28_days) : "—"} icon="trend"
                  detail={data.forecast ? `${humanize(data.forecast.model_name)} from ${fmtDate(data.forecast.origin_date)}` : "No forecast yet"} />
        <StatCard label="Open purchase orders" value={fmtInt(data.purchase_orders.open)} simulated icon="clipboard"
                  detail={`${fmtMoney(data.purchase_orders.open_order_value)} outstanding · ${data.purchase_orders.drafts} drafts`} />
        <StatCard label="Low or out of stock" value={fmtInt((data.stock_status.low ?? 0) + (data.stock_status.out_of_stock ?? 0))} icon="warehouse"
                  tone={(data.stock_status.out_of_stock ?? 0) > 0 ? "critical" : "default"} simulated
                  detail="Stock will not last the supplier lead time" />
      </div>

      <div className="mt-6 grid grid-cols-1 gap-6 xl:grid-cols-3">
        <Card title="Sales trend (all products, last 90 days)" className="xl:col-span-2">
          {data.sales?.daily_trend.length ? <SalesTrendChart points={data.sales.daily_trend} />
            : <EmptyState title="No sales data yet" />}
        </Card>
        <Card title={<span className="flex items-center gap-2">Inventory health <SimulatedTag /></span>}
              actions={<Link to="/inventory" className="text-sm text-brand-600 hover:underline">View stock</Link>}>
          <CategoryBars data={stockBars} ariaLabel="Products by stock status" />
        </Card>
      </div>

      <div className="mt-6 grid grid-cols-1 gap-6 xl:grid-cols-3">
        <Card title="Reorder status" actions={rec && <Link to="/recommendations" className="text-sm text-brand-600 hover:underline">Review</Link>}>
          {rec ? (
            <>
              <CategoryBars data={riskBars} ariaLabel="Products by reorder risk" />
              <p className="mt-2 text-xs text-slate-500">Recommendation run #{rec.run_id}, {fmtDateTime(rec.created_at)}</p>
            </>
          ) : (
            <EmptyState title="No recommendations yet">
              {can("admin", "manager") ? "Use “Run forecast & recommendations” above." : "Ask a manager to run them."}
            </EmptyState>
          )}
        </Card>
        <Card title="Recent inventory activity" className="xl:col-span-2"
              actions={<Link to="/inventory" className="text-sm text-brand-600 hover:underline">All movements</Link>}>
          <RecentActivity rows={data.recent_activity} />
        </Card>
      </div>
    </>
  );
}

const TXN_TONE = { initial: "gray", receipt: "green", sale: "blue", adjustment: "amber", return: "purple" } as const;

function RecentActivity({ rows }: { rows: TransactionRow[] }) {
  if (!rows.length) return <EmptyState title="No stock movements yet" />;
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-sm">
        <thead className="text-left text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <th className="py-2 pr-4 font-medium">When</th>
            <th className="py-2 pr-4 font-medium">Product</th>
            <th className="py-2 pr-4 font-medium">Type</th>
            <th className="py-2 pr-4 text-right font-medium">Change</th>
            <th className="py-2 pr-4 text-right font-medium">Stock after</th>
            <th className="py-2 font-medium">By</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.map((t) => (
            <tr key={t.id}>
              <td className="whitespace-nowrap py-2 pr-4 text-slate-500">{fmtDateTime(t.created_at)}</td>
              <td className="py-2 pr-4 font-medium text-slate-800">{t.sku}</td>
              <td className="py-2 pr-4"><Badge tone={TXN_TONE[t.txn_type]}>{humanize(t.txn_type)}</Badge></td>
              <td className={`py-2 pr-4 text-right tabular-nums ${t.quantity < 0 ? "text-red-700" : "text-emerald-700"}`}>
                {t.quantity > 0 ? `+${fmtInt(t.quantity)}` : fmtInt(t.quantity)}
              </td>
              <td className="py-2 pr-4 text-right tabular-nums">{fmtInt(t.balance_after)}</td>
              <td className="py-2 text-slate-500">{t.created_by_email ?? "System (setup)"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
