import { useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../../api/client";
import type { SlowMovers as SlowMoversData } from "../../api/types";
import { FilterSelect } from "../../components/fields";
import { EmptyState, ErrorMessage, Spinner } from "../../components/ui";
import { useApi } from "../../hooks/useApi";
import { DASH, fmtDate, fmtInt, fmtMoney } from "../../lib/format";

/** Stock on the shelf that has not sold for a while, and the money tied up in it (biggest first). */
export function SlowMovers() {
  const [days, setDays] = useState("60");
  const { data, error, loading, reload } = useApi(
    (signal) => api.get<SlowMoversData>("/analytics/slow-movers", { days }, signal), [days]);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <p className="max-w-2xl text-sm text-slate-600">
          Products in stock with no sale in the period: money tied up on the shelf. Consider a discount, a bundle, or
          not reordering them.
        </p>
        <FilterSelect label="No sale for" value={days} onChange={setDays}>
          <option value="30">30 days</option>
          <option value="60">60 days</option>
          <option value="90">90 days</option>
        </FilterSelect>
      </div>
      {error && <ErrorMessage message={error} onRetry={reload} />}
      {loading && !data && <Spinner />}
      {data && data.items.length === 0 && (
        <EmptyState title={`Everything in stock has sold in the last ${days} days`} />
      )}
      {data && data.items.length > 0 && (
        <>
          <p className="text-sm">
            <strong>{fmtInt(data.items.length)}</strong> products, <strong>{fmtMoney(data.total_value)}</strong> at cost
            {data.products_without_cost > 0 && ` (${data.products_without_cost} without a cost are not counted)`}.
          </p>
          <div className="max-h-96 overflow-y-auto">
            <table className="min-w-full text-sm">
              <thead className="sticky top-0 bg-white text-left text-xs uppercase tracking-wide text-slate-500">
                <tr>
                  <th scope="col" className="py-2 pr-3 font-medium">Product</th>
                  <th scope="col" className="py-2 pr-3 font-medium">Category</th>
                  <th scope="col" className="py-2 pr-3 text-right font-medium">On hand</th>
                  <th scope="col" className="py-2 pr-3 text-right font-medium">Value at cost</th>
                  <th scope="col" className="py-2 font-medium">Last sold</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {data.items.map((r) => (
                  <tr key={r.product_id}>
                    <td className="py-2 pr-3">
                      <Link to={`/products/${r.product_id}`} className="font-medium text-brand-600 hover:underline">{r.sku}</Link>
                      <p className="text-xs text-slate-500">{r.name}</p>
                    </td>
                    <td className="py-2 pr-3 text-slate-600">{r.category}</td>
                    <td className="py-2 pr-3 text-right tabular-nums">{fmtInt(r.on_hand)}</td>
                    <td className="py-2 pr-3 text-right tabular-nums">{r.stock_value === null ? DASH : fmtMoney(r.stock_value)}</td>
                    <td className="py-2 text-slate-600">
                      {r.last_sold ? `${fmtDate(r.last_sold)} (${fmtInt(r.days_since_sale)} days ago)` : "Never in the data"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
