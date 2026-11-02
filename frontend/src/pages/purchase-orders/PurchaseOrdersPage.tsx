import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { api } from "../../api/client";
import type { Page, PurchaseOrder, PurchaseOrderStatus } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { Dialog } from "../../components/Dialog";
import { FilterSelect } from "../../components/fields";
import { Pagination } from "../../components/Pagination";
import { Button, Card, EmptyState, ErrorMessage, PageHeader, SimulatedTag, Skeleton } from "../../components/ui";
import { useApi } from "../../hooks/useApi";
import { useReference } from "../../hooks/useReference";
import { fmtDate, fmtInt, fmtMoney } from "../../lib/format";
import { OrderForm } from "./OrderForm";
import { NOT_SENT_NOTE, PO_STATUS, PoStatusBadge } from "./status";

const PAGE_SIZE = 25;

export function PurchaseOrdersPage() {
  const { can } = useAuth();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const status = params.get("status") ?? "";
  const supplier = params.get("supplier_id") ?? "";
  const page = Number(params.get("page") ?? 1);
  const [creating, setCreating] = useState(false);
  const reference = useReference();
  const { data, error, loading, reload } = useApi(
    (signal) => api.get<Page<PurchaseOrder>>("/purchase-orders", { status, supplier_id: supplier, page, page_size: PAGE_SIZE }, signal),
    [status, supplier, page],
  );

  function update(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    if (key !== "page") next.delete("page");
    setParams(next, { replace: true });
  }

  return (
    <>
      <PageHeader
        title="Purchase orders"
        description={NOT_SENT_NOTE}
        actions={can("admin", "manager") && <Button onClick={() => setCreating(true)}>New draft order</Button>}
      />
      <Card>
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <FilterSelect label="Order status" value={status} onChange={(v) => update("status", v)}>
            <option value="">All statuses</option>
            {(Object.keys(PO_STATUS) as PurchaseOrderStatus[]).map((s) => <option key={s} value={s}>{PO_STATUS[s].label}</option>)}
          </FilterSelect>
          <FilterSelect label="Supplier" value={supplier} onChange={(v) => update("supplier_id", v)}>
            <option value="">All suppliers</option>
            {reference.data?.suppliers.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </FilterSelect>
          <span className="ml-auto flex items-center gap-2 text-xs text-slate-500">Costs <SimulatedTag /></span>
        </div>
        {error && <ErrorMessage message={error} onRetry={reload} />}
        {loading && !data && <Skeleton label="Loading orders…" />}
        {data && data.items.length === 0 && (
          <EmptyState icon="clipboard" title="No purchase orders yet">
            Approve recommendations on the <Link to="/recommendations" className="text-brand-600 hover:underline">Reorder page</Link> and
            create draft orders from them, or start a draft by hand.
          </EmptyState>
        )}
        {data && data.items.length > 0 && (
          <div className={`overflow-x-auto ${loading ? "opacity-60" : ""}`} aria-busy={loading}>
            <table className="min-w-full text-sm">
              <thead className="text-left text-xs uppercase tracking-wide text-slate-500">
                <tr>
                  <th scope="col" className="py-2 pr-4 font-medium">Order</th>
                  <th scope="col" className="py-2 pr-4 font-medium">Supplier</th>
                  <th scope="col" className="py-2 pr-4 font-medium">Status</th>
                  <th scope="col" className="py-2 pr-4 text-right font-medium">Lines</th>
                  <th scope="col" className="py-2 pr-4 text-right font-medium">Units</th>
                  <th scope="col" className="py-2 pr-4 text-right font-medium">Received</th>
                  <th scope="col" className="py-2 pr-4 text-right font-medium">Total</th>
                  <th scope="col" className="py-2 pr-4 font-medium">Expected</th>
                  <th scope="col" className="py-2 font-medium">Created</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {data.items.map((po) => (
                  <tr key={po.id} className="hover:bg-slate-50">
                    <td className="py-2 pr-4"><Link to={`/purchase-orders/${po.id}`} className="font-medium text-brand-600 hover:underline">{po.po_number}</Link></td>
                    <td className="py-2 pr-4">{po.supplier_name}</td>
                    <td className="py-2 pr-4"><PoStatusBadge status={po.status} /></td>
                    <td className="py-2 pr-4 text-right tabular-nums">{po.lines.length}</td>
                    <td className="py-2 pr-4 text-right tabular-nums">{fmtInt(po.total_units)}</td>
                    <td className="py-2 pr-4 text-right tabular-nums">{fmtInt(po.lines.reduce((s, l) => s + l.quantity_received, 0))}</td>
                    <td className="py-2 pr-4 text-right tabular-nums">{fmtMoney(po.total_cost)}</td>
                    <td className="py-2 pr-4">{fmtDate(po.expected_date)}</td>
                    <td className="py-2 text-slate-500">{fmtDate(po.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {data && data.total > 0 && (
          <div className="mt-3">
            <Pagination page={data.page} pages={data.pages} total={data.total} pageSize={PAGE_SIZE} onPage={(p) => update("page", String(p))} />
          </div>
        )}
      </Card>

      <Dialog title="New draft order" open={creating} onClose={() => setCreating(false)} wide>
        <OrderForm suppliers={reference.data?.suppliers ?? []} onCancel={() => setCreating(false)}
                   onSaved={(po) => navigate(`/purchase-orders/${po.id}`)} />
      </Dialog>
    </>
  );
}
