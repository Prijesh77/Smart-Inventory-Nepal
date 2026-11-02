import { useState } from "react";

import { api } from "../../api/client";
import type { Page, TransactionRow } from "../../api/types";
import { FilterSelect } from "../../components/fields";
import { Pagination } from "../../components/Pagination";
import { Badge, Button, EmptyState, ErrorMessage, Skeleton } from "../../components/ui";
import { useApi } from "../../hooks/useApi";
import { fmtDateTime, fmtInt, humanize } from "../../lib/format";

const PAGE_SIZE = 50;
export const TXN_TONE = { initial: "gray", receipt: "green", sale: "blue", adjustment: "amber", return: "purple" } as const;

/** The audit log of stock movements. It is read-only: movements are never edited or deleted. */
export function MovementsTable({ product, onClearProduct, refreshKey }:
  { product: { id: number; sku: string } | null; onClearProduct: () => void; refreshKey: number }) {
  const [type, setType] = useState("");
  const [page, setPage] = useState(1);
  const { data, error, loading, reload } = useApi(
    (signal) => api.get<Page<TransactionRow>>("/inventory/transactions",
      { page, page_size: PAGE_SIZE, txn_type: type, product_id: product?.id }, signal),
    [page, type, product?.id, refreshKey],
  );

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <FilterSelect label="Movement type" value={type} onChange={(v) => { setType(v); setPage(1); }}>
          <option value="">All types</option>
          {Object.keys(TXN_TONE).map((t) => <option key={t} value={t}>{humanize(t)}</option>)}
        </FilterSelect>
        {product && (
          <span className="flex items-center gap-2 rounded-full bg-brand-50 py-1 pl-3 pr-1 text-sm text-brand-700">
            Product {product.sku}
            <Button variant="ghost" className="!px-2 !py-0.5" onClick={() => { onClearProduct(); setPage(1); }}
                    aria-label="Show all products">✕</Button>
          </span>
        )}
      </div>

      {error && <ErrorMessage message={error} onRetry={reload} />}
      {loading && !data && <Skeleton label="Loading movements…" />}
      {data && data.items.length === 0 && <EmptyState icon="clipboard" title="No stock movements match">Try a different search, or clear the filters.</EmptyState>}
      {data && data.items.length > 0 && (
        <div className={`overflow-x-auto ${loading ? "opacity-60" : ""}`} aria-busy={loading}>
          <table className="min-w-full text-sm">
            <thead className="text-left text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th scope="col" className="py-2 pr-4 font-medium">When</th>
                <th scope="col" className="py-2 pr-4 font-medium">Product</th>
                <th scope="col" className="py-2 pr-4 font-medium">Type</th>
                <th scope="col" className="py-2 pr-4 text-right font-medium">Change</th>
                <th scope="col" className="py-2 pr-4 text-right font-medium">Stock after</th>
                <th scope="col" className="py-2 pr-4 font-medium">Reason</th>
                <th scope="col" className="py-2 font-medium">By</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {data.items.map((t) => (
                <tr key={t.id}>
                  <td className="whitespace-nowrap py-2 pr-4 text-slate-500">{fmtDateTime(t.created_at)}</td>
                  <td className="py-2 pr-4 font-medium">{t.sku}</td>
                  <td className="py-2 pr-4">
                    <Badge tone={TXN_TONE[t.txn_type]}>{humanize(t.txn_type)}</Badge>
                    {t.purchase_order_id && <span className="ml-1 text-xs text-slate-500">PO #{t.purchase_order_id}</span>}
                  </td>
                  <td className={`py-2 pr-4 text-right tabular-nums ${t.quantity < 0 ? "text-red-700" : "text-emerald-700"}`}>
                    {t.quantity > 0 ? `+${fmtInt(t.quantity)}` : fmtInt(t.quantity)}
                  </td>
                  <td className="py-2 pr-4 text-right tabular-nums">{fmtInt(t.balance_after)}</td>
                  <td className="max-w-xs truncate py-2 pr-4 text-slate-600" title={t.reason ?? ""}>{t.reason ?? "—"}</td>
                  <td className="py-2 text-slate-500">{t.created_by_email ?? "System (setup)"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {data && data.total > 0 && (
        <div className="mt-3">
          <Pagination page={data.page} pages={data.pages} total={data.total} pageSize={PAGE_SIZE} onPage={setPage} />
        </div>
      )}
    </>
  );
}
