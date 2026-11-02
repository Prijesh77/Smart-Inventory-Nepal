import { useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../../api/client";
import type { Category, Page, StockItem, StockStatus } from "../../api/types";
import { FilterSelect } from "../../components/fields";
import { Pagination } from "../../components/Pagination";
import { SortHeader } from "../../components/SortHeader";
import { Badge, Button, EmptyState, ErrorMessage, Skeleton } from "../../components/ui";
import { useApi } from "../../hooks/useApi";
import { useDebounce } from "../../hooks/useDebounce";
import { STOCK_STATUS_STYLE } from "../../lib/colors";
import { fmtDecimal, fmtInt } from "../../lib/format";

const PAGE_SIZE = 25;

export function StockStatusBadge({ status }: { status: StockStatus }) {
  const style = STOCK_STATUS_STYLE[status];
  return <Badge tone={style.tone}>{style.label}</Badge>;
}

/** Days of cover, highlighted when it is shorter than the supplier lead time. */
export function CoverCell({ item }: { item: StockItem }) {
  if (item.days_of_cover === null) return <span className="text-slate-400">—</span>;
  const short = item.lead_time_days !== null && item.days_of_cover < item.lead_time_days;
  return (
    <span className={short ? "font-medium text-red-700" : ""}>
      {fmtDecimal(item.days_of_cover)} d
      {short && <span className="sr-only"> (shorter than the lead time)</span>}
    </span>
  );
}

export function StockTable({ categories, initialSearch, canAdjust, onAdjust, onHistory, refreshKey }: {
  categories: Category[];
  initialSearch: string;
  canAdjust: boolean;
  onAdjust: (item: StockItem) => void;
  onHistory: (item: StockItem) => void;
  refreshKey: number;
}) {
  const [searchText, setSearchText] = useState(initialSearch);
  const search = useDebounce(searchText);
  const [category, setCategory] = useState("");
  const [status, setStatus] = useState("");
  const [sort, setSort] = useState("sku");
  const [order, setOrder] = useState<"asc" | "desc">("asc");
  const [page, setPage] = useState(1);

  const { data, error, loading, reload } = useApi(
    (signal) => api.get<Page<StockItem>>("/inventory", { page, page_size: PAGE_SIZE, search, category, status, sort, order }, signal),
    [page, search, category, status, sort, order, refreshKey],
  );

  function onSort(field: string) {
    setOrder(sort === field && order === "asc" ? "desc" : "asc");
    setSort(field);
    setPage(1);
  }

  return (
    <>
      <div className="mb-4 flex flex-wrap gap-3">
        <label className="min-w-[14rem] flex-1">
          <span className="sr-only">Search stock</span>
          <input type="search" placeholder="Search SKU or name…" value={searchText}
                 onChange={(e) => { setSearchText(e.target.value); setPage(1); }}
                 className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm" />
        </label>
        <FilterSelect label="Category" value={category} onChange={(v) => { setCategory(v); setPage(1); }}>
          <option value="">All categories</option>
          {categories.map((c) => <option key={c.id} value={c.code}>{c.name}</option>)}
        </FilterSelect>
        <FilterSelect label="Stock status" value={status} onChange={(v) => { setStatus(v); setPage(1); }}>
          <option value="">All statuses</option>
          {(Object.keys(STOCK_STATUS_STYLE) as StockStatus[]).map((s) =>
            <option key={s} value={s}>{STOCK_STATUS_STYLE[s].label}</option>)}
        </FilterSelect>
      </div>

      {error && <ErrorMessage message={error} onRetry={reload} />}
      {loading && !data && <Skeleton label="Loading stock…" />}
      {data && data.items.length === 0 && <EmptyState icon="warehouse" title="No products match these filters">Try a different search, or clear the filters.</EmptyState>}
      {data && data.items.length > 0 && (
        <div className={`overflow-x-auto ${loading ? "opacity-60" : ""}`} aria-busy={loading}>
          <table className="min-w-full text-sm">
            <thead className="text-xs text-slate-500">
              <tr>
                <SortHeader label="SKU" field="sku" sort={sort} order={order} onSort={onSort} />
                <th scope="col" className="py-2 pr-4 text-left font-medium uppercase tracking-wide">Status</th>
                <SortHeader label="On hand" field="on_hand" sort={sort} order={order} onSort={onSort} align="right" />
                <th scope="col" className="py-2 pr-4 text-right font-medium uppercase tracking-wide">On order</th>
                <SortHeader label="Position" field="inventory_position" sort={sort} order={order} onSort={onSort} align="right" />
                <SortHeader label="Sales / day" field="avg_daily_sales" sort={sort} order={order} onSort={onSort} align="right" />
                <SortHeader label="Cover" field="days_of_cover" sort={sort} order={order} onSort={onSort} align="right" />
                <th scope="col" className="py-2 pr-4 text-right font-medium uppercase tracking-wide">Lead time</th>
                <th scope="col" className="py-2 text-right font-medium uppercase tracking-wide"><span className="sr-only">Actions</span></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {data.items.map((item) => (
                <tr key={item.product_id} className="hover:bg-slate-50">
                  <td className="py-2 pr-4">
                    <Link to={`/products/${item.product_id}`} className="font-medium text-brand-600 hover:underline">{item.sku}</Link>
                    <p className="text-xs text-slate-500">{item.name}</p>
                  </td>
                  <td className="py-2 pr-4"><StockStatusBadge status={item.stock_status} /></td>
                  <td className="py-2 pr-4 text-right tabular-nums">{fmtInt(item.on_hand)}</td>
                  <td className="py-2 pr-4 text-right tabular-nums">{fmtInt(item.on_order)}</td>
                  <td className="py-2 pr-4 text-right tabular-nums">{fmtInt(item.inventory_position)}</td>
                  <td className="py-2 pr-4 text-right tabular-nums">{fmtDecimal(item.avg_daily_sales)}</td>
                  <td className="py-2 pr-4 text-right tabular-nums"><CoverCell item={item} /></td>
                  <td className="py-2 pr-4 text-right tabular-nums">{item.lead_time_days ? `${item.lead_time_days} d` : "—"}</td>
                  <td className="whitespace-nowrap py-2 text-right">
                    <Button variant="ghost" onClick={() => onHistory(item)} aria-label={`Movements for ${item.sku}`}>History</Button>
                    {canAdjust && <Button variant="ghost" onClick={() => onAdjust(item)} aria-label={`Adjust stock for ${item.sku}`}>Adjust</Button>}
                  </td>
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
