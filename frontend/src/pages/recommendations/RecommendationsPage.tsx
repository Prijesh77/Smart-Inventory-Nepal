import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { api, ApiError } from "../../api/client";
import type { PurchaseOrder, Recommendation, RecommendationPage, RecommendationRun, ReviewStatus, RiskCategory } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { Dialog } from "../../components/Dialog";
import { FilterSelect } from "../../components/fields";
import { Pagination } from "../../components/Pagination";
import { Button, Card, EmptyState, ErrorMessage, PageHeader, SimulatedTag, Spinner } from "../../components/ui";
import { useApi } from "../../hooks/useApi";
import { useDebounce } from "../../hooks/useDebounce";
import { RISK_STYLE } from "../../lib/colors";
import { fmtDateTime, fmtInt, fmtMoney, fmtPct } from "../../lib/format";
import { createDraftOrders } from "./actions";
import { NewRunForm } from "./NewRunForm";
import { RecommendationTable } from "./RecommendationTable";

const PAGE_SIZE = 25;
const RISKS: RiskCategory[] = ["critical_stockout_risk", "reorder_soon", "excess_inventory", "healthy", "insufficient_data"];

export function RecommendationsPage({ pollMs }: { pollMs?: number }) {
  const { can } = useAuth();
  const canReview = can("admin", "manager");
  const [params, setParams] = useSearchParams();
  const get = (k: string, fallback = "") => params.get(k) ?? fallback;
  const [searchText, setSearchText] = useState(get("search"));
  const search = useDebounce(searchText);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [message, setMessage] = useState<{ kind: "ok" | "error"; text: string; orders?: PurchaseOrder[] } | null>(null);
  const [creatingRun, setCreatingRun] = useState(false);
  const [ordering, setOrdering] = useState(false);

  const query = {
    run_id: get("run"), risk: get("risk"), review_status: get("review"), only_orders: get("orders") === "1" || undefined,
    sort: get("sort", "risk"), order: get("order", "asc"), page: Number(get("page", "1")), search,
  };
  const list = useApi(
    (signal) => api.get<RecommendationPage>("/recommendations", { ...query, page_size: PAGE_SIZE }, signal),
    [query.run_id, query.risk, query.review_status, query.only_orders, query.sort, query.order, query.page, search],
  );
  const runs = useApi((signal) => api.get<RecommendationRun[]>("/recommendations/runs", { limit: 20 }, signal));
  const policy = useApi((signal) => api.get<RecommendationRun["policy_settings"]>("/settings/policy", undefined, signal));

  function update(changes: Record<string, string>, resetPage = true) {
    const next = new URLSearchParams(params);
    Object.entries(changes).forEach(([k, v]) => (v ? next.set(k, v) : next.delete(k)));
    if (resetPage) next.delete("page");
    setParams(next, { replace: true });
  }

  async function review(rec: Recommendation, status: ReviewStatus) {
    setBusyId(rec.id);
    setMessage(null);
    try {
      await api.patch(`/recommendations/${rec.id}`, { review_status: status });
      list.reload();
    } catch (err) {
      setMessage({ kind: "error", text: err instanceof ApiError ? err.message : "Could not save the decision" });
    } finally {
      setBusyId(null);
    }
  }

  async function makeOrders(runId: number) {
    setOrdering(true);
    setMessage(null);
    try {
      const orders = await createDraftOrders(runId);
      if (!orders.length) setMessage({ kind: "error", text: "Approve at least one recommendation first." });
      else setMessage({ kind: "ok", orders, text: `Created ${orders.length} draft purchase order(s) with ${fmtInt(
        orders.reduce((s, o) => s + o.lines.length, 0))} line(s). Nothing has been sent to any supplier.` });
      list.reload();
    } catch (err) {
      setMessage({ kind: "error", text: err instanceof ApiError ? err.message : "Could not create the orders" });
    } finally {
      setOrdering(false);
    }
  }

  const run = list.data?.run;
  const counts = run?.summary?.counts ?? {};

  return (
    <>
      <PageHeader
        title="Reorder recommendations"
        description="What to order, how much and why, for every product. Approve the ones you agree with, then turn them into draft purchase orders."
        actions={canReview && <Button onClick={() => setCreatingRun(true)}>New recommendations</Button>}
      />

      {message && (
        <div role={message.kind === "error" ? "alert" : "status"}
             className={`mb-4 rounded-md p-3 text-sm ${message.kind === "error" ? "bg-red-50 text-red-800" : "bg-emerald-50 text-emerald-800"}`}>
          {message.text}{" "}
          {message.orders?.map((o) => (
            <Link key={o.id} to={`/purchase-orders/${o.id}`} className="mr-2 font-medium underline">{o.po_number}</Link>
          ))}
        </div>
      )}

      {list.error && !list.data && (
        list.error.includes("No completed recommendation run")
          ? <EmptyState title="No recommendations yet">
              {canReview ? "Click “New recommendations” (a forecast is needed first)." : "Ask a manager to create them."}
            </EmptyState>
          : <ErrorMessage message={list.error} onRetry={list.reload} />
      )}
      {list.loading && !list.data && <Spinner label="Loading recommendations…" />}

      {run && (
        <>
          <Card className="mb-6">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="text-sm text-slate-600">
                <FilterSelect label="Recommendation run" value={String(run.id)} onChange={(v) => update({ run: v })}>
                  {(runs.data ?? [run]).filter((r) => r.status === "completed").map((r) => (
                    <option key={r.id} value={r.id}>Run #{r.id} · {fmtDateTime(r.created_at)}</option>
                  ))}
                </FilterSelect>
                <p className="mt-2">
                  Forecast run #{run.forecast_run_id} · service level {fmtPct(run.policy_settings.service_level)} ·
                  review every {run.policy_settings.review_period_days} days
                </p>
              </div>
              <div className="text-right">
                <p className="flex items-center justify-end gap-2 text-sm text-slate-500">Suggested orders, total <SimulatedTag /></p>
                <p className="text-2xl font-semibold tabular-nums">{fmtMoney(run.summary?.total_suggested_order_cost ?? 0)}</p>
                {canReview && (
                  <Button className="mt-2" onClick={() => makeOrders(run.id)} disabled={ordering}>
                    {ordering ? "Creating…" : "Create draft orders from approved"}
                  </Button>
                )}
              </div>
            </div>
            <div className="mt-4 flex flex-wrap gap-2" role="group" aria-label="Filter by risk">
              <RiskChip label="All" count={RISKS.reduce((s, r) => s + (counts[r] ?? 0), 0)} active={!query.risk}
                        onClick={() => update({ risk: "" })} color="#64748B" />
              {RISKS.map((r) => (
                <RiskChip key={r} label={RISK_STYLE[r].label} count={counts[r] ?? 0} color={RISK_STYLE[r].color}
                          active={query.risk === r} onClick={() => update({ risk: query.risk === r ? "" : r })} />
              ))}
            </div>
          </Card>

          <Card>
            <div className="mb-4 flex flex-wrap items-center gap-3">
              <label className="min-w-[12rem] flex-1">
                <span className="sr-only">Search recommendations</span>
                <input type="search" placeholder="Search SKU or name…" value={searchText}
                       onChange={(e) => { setSearchText(e.target.value); update({ search: e.target.value }); }}
                       className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm" />
              </label>
              <FilterSelect label="Review status" value={query.review_status} onChange={(v) => update({ review: v })}>
                <option value="">Any review status</option>
                <option value="pending">To review</option>
                <option value="approved">Approved</option>
                <option value="rejected">Rejected</option>
                <option value="ordered">On a draft order</option>
              </FilterSelect>
              <FilterSelect label="Sort by" value={`${query.sort}:${query.order}`}
                            onChange={(v) => { const [sort, order] = v.split(":"); update({ sort, order }); }}>
                <option value="risk:asc">Most urgent first</option>
                <option value="estimated_order_cost:desc">Highest order cost</option>
                <option value="suggested_qty:desc">Largest quantity</option>
                <option value="days_of_cover:asc">Least days of cover</option>
                <option value="sku:asc">SKU</option>
              </FilterSelect>
              <label className="flex items-center gap-2 text-sm text-slate-700">
                <input type="checkbox" checked={!!query.only_orders} onChange={(e) => update({ orders: e.target.checked ? "1" : "" })} />
                Only items to order
              </label>
            </div>
            {list.data && list.data.items.length === 0 && <EmptyState title="No recommendations match these filters" />}
            {list.data && list.data.items.length > 0 && (
              <div className={list.loading ? "opacity-60" : ""} aria-busy={list.loading}>
                <RecommendationTable rows={list.data.items} canReview={canReview} busyId={busyId} onReview={review} />
                <div className="mt-3">
                  <Pagination page={list.data.page} pages={list.data.pages} total={list.data.total} pageSize={PAGE_SIZE}
                              onPage={(p) => update({ page: String(p) }, false)} />
                </div>
              </div>
            )}
            <p className="mt-3 text-xs text-slate-500">
              In the demo shop, sales, stock, costs and lead times are <span className="text-violet-700">synthetic</span>. "Stockout chance" is a model estimate, not an observed rate.
              Nothing is ordered from suppliers automatically.
            </p>
          </Card>
        </>
      )}

      <Dialog title="New recommendations" open={creatingRun} onClose={() => setCreatingRun(false)} wide>
        <NewRunForm defaults={policy.data} pollMs={pollMs} onCancel={() => setCreatingRun(false)}
                    onDone={(r) => { setCreatingRun(false); runs.reload(); update({ run: String(r.id) }); }} />
      </Dialog>
    </>
  );
}

function RiskChip({ label, count, color, active, onClick }:
  { label: string; count: number; color: string; active: boolean; onClick: () => void }) {
  return (
    <button type="button" onClick={onClick} aria-pressed={active}
            className={`flex items-center gap-2 rounded-full px-3 py-1.5 text-sm ring-1 ring-inset ${
              active ? "bg-slate-800 text-white ring-slate-800" : "bg-white text-slate-700 ring-slate-300 hover:bg-slate-50"}`}>
      <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: color }} aria-hidden />
      {label}
      <span className="tabular-nums font-semibold">{fmtInt(count)}</span>
    </button>
  );
}
