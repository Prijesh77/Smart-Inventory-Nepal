import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { api } from "../../api/client";
import type { Page, Product } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { Dialog } from "../../components/Dialog";
import { FilterSelect } from "../../components/fields";
import { Pagination } from "../../components/Pagination";
import { SortHeader } from "../../components/SortHeader";
import { Badge, Button, Card, EmptyState, ErrorMessage, PageHeader, Spinner } from "../../components/ui";
import { useApi } from "../../hooks/useApi";
import { useDebounce } from "../../hooks/useDebounce";
import { useReference } from "../../hooks/useReference";
import { fmtInt, fmtMoney, humanize } from "../../lib/format";
import { ProductForm } from "./ProductForm";

const PAGE_SIZE = 25;
export const CLASS_TONE = { smooth: "green", erratic: "amber", intermittent: "blue", lumpy: "purple" } as const;

/** Filters live in the URL, so the back button and shared links keep them. */
export function ProductsPage() {
  const { can } = useAuth();
  const [params, setParams] = useSearchParams();
  const [searchText, setSearchText] = useState(params.get("search") ?? "");
  const search = useDebounce(searchText);
  const [creating, setCreating] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const page = Number(params.get("page") ?? 1);
  const filters = {
    category: params.get("category") ?? "",
    supplier_id: params.get("supplier_id") ?? "",
    demand_class: params.get("demand_class") ?? "",
    is_active: params.get("is_active") ?? "true",
    sort: params.get("sort") ?? "sku",
    order: (params.get("order") ?? "asc") as "asc" | "desc",
  };

  function update(changes: Record<string, string>, resetPage = true) {
    const next = new URLSearchParams(params);
    Object.entries(changes).forEach(([k, v]) => (v ? next.set(k, v) : next.delete(k)));
    if (resetPage) next.delete("page");
    setParams(next, { replace: true });
  }

  const reference = useReference();
  const { data, error, loading, reload } = useApi(
    (signal) => api.get<Page<Product>>("/products", {
      page, page_size: PAGE_SIZE, search, ...filters,
      is_active: filters.is_active === "all" ? undefined : filters.is_active,
    }, signal),
    [page, search, filters.category, filters.supplier_id, filters.demand_class, filters.is_active, filters.sort, filters.order],
  );

  function onSort(field: string) {
    update({ sort: field, order: filters.sort === field && filters.order === "asc" ? "desc" : "asc" });
  }

  return (
    <>
      <PageHeader
        title="Products"
        description="Search, filter and edit products. Unit cost, supplier and lead time are simulated values."
        actions={can("admin", "manager") && <Button onClick={() => setCreating(true)}>Add product</Button>}
      />
      {notice && <p role="status" className="mb-4 rounded-md bg-emerald-50 p-3 text-sm text-emerald-800">{notice}</p>}

      <Card>
        <div className="mb-4 flex flex-wrap gap-3">
          <label className="min-w-[14rem] flex-1">
            <span className="sr-only">Search products</span>
            <input type="search" placeholder="Search SKU or name…" value={searchText}
                   onChange={(e) => { setSearchText(e.target.value); update({ search: e.target.value }); }}
                   className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm" />
          </label>
          <FilterSelect label="Category" value={filters.category} onChange={(v) => update({ category: v })}>
            <option value="">All categories</option>
            {reference.data?.categories.map((c) => <option key={c.id} value={c.code}>{c.name}</option>)}
          </FilterSelect>
          <FilterSelect label="Supplier" value={filters.supplier_id} onChange={(v) => update({ supplier_id: v })}>
            <option value="">All suppliers</option>
            {reference.data?.suppliers.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </FilterSelect>
          <FilterSelect label="Demand pattern" value={filters.demand_class} onChange={(v) => update({ demand_class: v })}>
            <option value="">All demand patterns</option>
            {Object.keys(CLASS_TONE).map((c) => <option key={c} value={c}>{humanize(c)}</option>)}
          </FilterSelect>
          <FilterSelect label="Status" value={filters.is_active} onChange={(v) => update({ is_active: v })}>
            <option value="true">Active</option>
            <option value="false">Inactive</option>
            <option value="all">All</option>
          </FilterSelect>
        </div>

        {error && <ErrorMessage message={error} onRetry={reload} />}
        {loading && !data && <Spinner label="Loading products…" />}
        {data && data.items.length === 0 && <EmptyState title="No products match these filters" />}
        {data && data.items.length > 0 && (
          <div className={`overflow-x-auto ${loading ? "opacity-60" : ""}`} aria-busy={loading}>
            <table className="min-w-full text-sm">
              <thead className="text-xs text-slate-500">
                <tr>
                  <SortHeader label="SKU" field="sku" {...filters} onSort={onSort} />
                  <SortHeader label="Name" field="name" {...filters} onSort={onSort} />
                  <th scope="col" className="py-2 pr-4 text-left font-medium uppercase tracking-wide">Category</th>
                  <th scope="col" className="py-2 pr-4 text-left font-medium uppercase tracking-wide">Supplier</th>
                  <SortHeader label="Price" field="unit_price" {...filters} onSort={onSort} align="right" />
                  <SortHeader label="On hand" field="on_hand" {...filters} onSort={onSort} align="right" />
                  <th scope="col" className="py-2 pr-4 text-right font-medium uppercase tracking-wide">Lead time</th>
                  <th scope="col" className="py-2 text-left font-medium uppercase tracking-wide">Demand</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {data.items.map((p) => (
                  <tr key={p.id} className="hover:bg-slate-50">
                    <td className="py-2 pr-4 font-medium">
                      <Link to={`/products/${p.id}`} className="text-brand-600 hover:underline">{p.sku}</Link>
                      {!p.is_active && <span className="ml-2"><Badge>Inactive</Badge></span>}
                    </td>
                    <td className="py-2 pr-4">{p.name}</td>
                    <td className="py-2 pr-4 text-slate-600">{p.category.name}</td>
                    <td className="py-2 pr-4 text-slate-600">{p.supplier?.name ?? "—"}</td>
                    <td className="py-2 pr-4 text-right tabular-nums">{fmtMoney(p.unit_price)}</td>
                    <td className="py-2 pr-4 text-right tabular-nums">{fmtInt(p.on_hand)}</td>
                    <td className="py-2 pr-4 text-right tabular-nums">
                      {p.effective_lead_time_days ? `${p.effective_lead_time_days} d` : "—"}
                    </td>
                    <td className="py-2">
                      {p.demand_class ? <Badge tone={CLASS_TONE[p.demand_class]}>{humanize(p.demand_class)}</Badge>
                        : <span className="text-slate-400">—</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {data && data.total > 0 && (
          <div className="mt-3">
            <Pagination page={data.page} pages={data.pages} total={data.total} pageSize={PAGE_SIZE}
                        onPage={(p) => update({ page: String(p) }, false)} />
          </div>
        )}
      </Card>

      <Dialog title="Add product" open={creating} onClose={() => setCreating(false)} wide>
        <ProductForm
          categories={reference.data?.categories ?? []}
          suppliers={reference.data?.suppliers ?? []}
          onCancel={() => setCreating(false)}
          onSaved={(p) => {
            setCreating(false);
            setNotice(`Product ${p.sku} created. Stock starts at 0.`);
            reload();
          }}
        />
      </Dialog>
    </>
  );
}
