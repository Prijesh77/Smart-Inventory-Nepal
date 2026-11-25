import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { api } from "../../api/client";
import type { Page, Product } from "../../api/types";
import { useAuth, useIsDemoShop } from "../../auth/AuthContext";
import { Dialog } from "../../components/Dialog";
import { FilterSelect } from "../../components/fields";
import { Pagination } from "../../components/Pagination";
import { SortHeader } from "../../components/SortHeader";
import { Badge, Button, Card, EmptyState, ErrorMessage, PageHeader, Skeleton } from "../../components/ui";
import { useToast } from "../../components/Toast";
import { useApi } from "../../hooks/useApi";
import { useDebounce } from "../../hooks/useDebounce";
import { useReference } from "../../hooks/useReference";
import { fmtInt, fmtMoney, humanize } from "../../lib/format";
import { ProductForm } from "./ProductForm";
import { t } from "../../lib/i18n";

const PAGE_SIZE = 25;
export const CLASS_TONE = { smooth: "green", erratic: "amber", intermittent: "blue", lumpy: "purple" } as const;

/** Filters live in the URL, so the back button and shared links keep them. */
export function ProductsPage() {
  const { can } = useAuth();
  const demo = useIsDemoShop();
  const [params, setParams] = useSearchParams();
  const [searchText, setSearchText] = useState(params.get("search") ?? "");
  const search = useDebounce(searchText);
  const [creating, setCreating] = useState(false);
  const toast = useToast();

  const page = Number(params.get("page") ?? 1);
  const filters = {
    category: params.get("category") ?? "",
    supplier_id: params.get("supplier_id") ?? "",
    demand_class: params.get("demand_class") ?? "",
    shelf_id: params.get("shelf_id") ?? "",
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
    [page, search, filters.category, filters.supplier_id, filters.demand_class, filters.shelf_id, filters.is_active, filters.sort, filters.order],
  );

  function onSort(field: string) {
    update({ sort: field, order: filters.sort === field && filters.order === "asc" ? "desc" : "asc" });
  }

  return (
    <>
      <PageHeader
        title={t("Products")}
        description={`Search, filter and edit products.${demo ? " In this demo shop, unit cost, supplier and lead time are simulated values." : ""}`}
        actions={can("admin", "manager") && <Button onClick={() => setCreating(true)}>{t("Add product")}</Button>}
      />

      <Card>
        <div className="mb-4 flex flex-wrap gap-3">
          <label className="min-w-[14rem] flex-1">
            <span className="sr-only">{t("Search products")}</span>
            <input type="search" placeholder={t("Search SKU or name…")} value={searchText}
                   onChange={(e) => { setSearchText(e.target.value); update({ search: e.target.value }); }}
                   className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm" />
          </label>
          <FilterSelect label={t("Category")} value={filters.category} onChange={(v) => update({ category: v })}>
            <option value="">{t("All categories")}</option>
            {reference.data?.categories.map((c) => <option key={c.id} value={c.code}>{c.name}</option>)}
          </FilterSelect>
          <FilterSelect label={t("Supplier")} value={filters.supplier_id} onChange={(v) => update({ supplier_id: v })}>
            <option value="">{t("All suppliers")}</option>
            {reference.data?.suppliers.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </FilterSelect>
          <FilterSelect label={t("Shelf")} value={filters.shelf_id} onChange={(v) => update({ shelf_id: v })}>
            <option value="">{t("All shelves")}</option>
            <option value="0">{t("Not on a shelf yet")}</option>
            {reference.data?.shelves.map((s) => <option key={s.id} value={s.id}>{s.code} · {s.name}</option>)}
          </FilterSelect>
          <FilterSelect label={t("Demand pattern")} value={filters.demand_class} onChange={(v) => update({ demand_class: v })}>
            <option value="">{t("All demand patterns")}</option>
            {Object.keys(CLASS_TONE).map((c) => <option key={c} value={c}>{t(humanize(c))}</option>)}
          </FilterSelect>
          <FilterSelect label={t("Status")} value={filters.is_active} onChange={(v) => update({ is_active: v })}>
            <option value="true">{t("Active")}</option>
            <option value="false">{t("Inactive")}</option>
            <option value="all">{t("All")}</option>
          </FilterSelect>
        </div>

        {error && <ErrorMessage message={error} onRetry={reload} />}
        {loading && !data && <Skeleton label={t("Loading products…")} />}
        {data && data.items.length === 0 && <EmptyState icon="box" title={t("No products match these filters")}>{t("Try a different search, or clear the filters.")}</EmptyState>}
        {data && data.items.length > 0 && (
          <div className={`overflow-x-auto ${loading ? "opacity-60" : ""}`} aria-busy={loading}>
            <table className="min-w-full text-sm">
              <thead className="text-xs text-slate-500">
                <tr>
                  <SortHeader label={t("SKU")} field="sku" {...filters} onSort={onSort} />
                  <SortHeader label={t("Name")} field="name" {...filters} onSort={onSort} />
                  <th scope="col" className="py-2 pr-4 text-left font-medium uppercase tracking-wide">{t("Category")}</th>
                  <SortHeader label={t("Shelf")} field="shelf" {...filters} onSort={onSort} />
                  <th scope="col" className="py-2 pr-4 text-left font-medium uppercase tracking-wide">{t("Supplier")}</th>
                  <SortHeader label={t("Price")} field="unit_price" {...filters} onSort={onSort} align="right" />
                  <SortHeader label={t("On hand")} field="on_hand" {...filters} onSort={onSort} align="right" />
                  <th scope="col" className="py-2 pr-4 text-right font-medium uppercase tracking-wide">{t("Lead time")}</th>
                  <th scope="col" className="py-2 text-left font-medium uppercase tracking-wide">{t("Demand")}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {data.items.map((p) => (
                  <tr key={p.id} className="hover:bg-slate-50">
                    <td className="py-2 pr-4 font-medium">
                      <Link to={`/products/${p.id}`} className="text-brand-600 hover:underline">{p.sku}</Link>
                      {!p.is_active && <span className="ml-2"><Badge>{t("Inactive")}</Badge></span>}
                    </td>
                    <td className="py-2 pr-4">{p.name}</td>
                    <td className="py-2 pr-4 text-slate-600">{p.category.name}</td>
                    <td className="py-2 pr-4">
                      {p.shelf ? <span title={p.shelf.name} className="rounded bg-brand-50 px-1.5 py-0.5 text-xs font-semibold text-brand-700">{p.shelf.code}</span>
                        : <span className="text-slate-400">—</span>}
                    </td>
                    <td className="py-2 pr-4 text-slate-600">{p.supplier?.name ?? "—"}</td>
                    <td className="py-2 pr-4 text-right tabular-nums">{fmtMoney(p.unit_price)}</td>
                    <td className="py-2 pr-4 text-right tabular-nums">{fmtInt(p.on_hand)}</td>
                    <td className="py-2 pr-4 text-right tabular-nums">
                      {p.effective_lead_time_days ? `${p.effective_lead_time_days} d` : "—"}
                    </td>
                    <td className="py-2">
                      {p.demand_class ? <Badge tone={CLASS_TONE[p.demand_class]}>{t(humanize(p.demand_class))}</Badge>
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

      <Dialog title={t("Add product")} open={creating} onClose={() => setCreating(false)} wide>
        <ProductForm
          categories={reference.data?.categories ?? []}
          suppliers={reference.data?.suppliers ?? []}
          shelves={reference.data?.shelves ?? []}
          onCancel={() => setCreating(false)}
          onSaved={(p) => {
            setCreating(false);
            toast(`Product ${p.sku} created. Stock starts at 0.`);
            reload();
          }}
        />
      </Dialog>
    </>
  );
}
