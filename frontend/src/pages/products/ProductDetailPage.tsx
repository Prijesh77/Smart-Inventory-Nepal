import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { api } from "../../api/client";
import type { Product, SalesHistory } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { DailySalesChart } from "../../components/charts/DailySalesChart";
import { Dialog } from "../../components/Dialog";
import { FilterSelect } from "../../components/fields";
import { Badge, Button, Card, ErrorMessage, PageHeader, SimulatedTag, Skeleton } from "../../components/ui";
import { useApi } from "../../hooks/useApi";
import { useReference } from "../../hooks/useReference";
import { fmtDate, fmtDecimal, fmtInt, fmtMoney, humanize } from "../../lib/format";
import { fiscalYear } from "../../lib/nepaliDate";
import { ProductForm } from "./ProductForm";
import { CLASS_TONE } from "./ProductsPage";
import { t } from "../../lib/i18n";

export function ProductDetailPage() {
  const { id } = useParams();
  const { can } = useAuth();
  const [days, setDays] = useState("90");
  const [editing, setEditing] = useState(false);
  const reference = useReference();
  const product = useApi((signal) => api.get<Product>(`/products/${id}`, undefined, signal), [id]);
  const history = useApi(async (signal) => {
    // First ask for the default window to learn the last sales date, then the chosen length.
    const latest = await api.get<SalesHistory>(`/products/${id}/sales`, undefined, signal);
    if (days === "90") return latest;
    if (days === "fy") {                       // Nepali fiscal year (from 1 Shrawan) up to the last sales day
      const fy = fiscalYear(latest.end);
      if (fy) return api.get<SalesHistory>(`/products/${id}/sales`, { start: fy.start, end: latest.end }, signal);
    }
    const end = new Date(`${latest.end}T00:00:00Z`);
    const start = new Date(end.getTime() - (Number(days) - 1) * 86_400_000).toISOString().slice(0, 10);
    return api.get<SalesHistory>(`/products/${id}/sales`, { start, end: latest.end }, signal);
  }, [id, days]);

  if (product.loading && !product.data) return <Skeleton variant="text" label={t("Loading product…")} />;
  if (product.error) return <ErrorMessage message={product.error} onRetry={product.reload} />;
  const p = product.data!;
  const h = history.data;
  const availableDays = h?.points.filter((x) => x.is_available).length ?? 0;

  return (
    <>
      <Link to="/products" className="text-sm text-brand-600 hover:underline">← All products</Link>
      <div className="mt-2">
        <PageHeader
          title={`${p.sku} · ${p.name}`}
          description={<span className="flex flex-wrap items-center gap-2">
            {p.category.name}{p.department && ` · ${p.department}`}
            {p.demand_class && <Badge tone={CLASS_TONE[p.demand_class]}>{humanize(p.demand_class)} demand</Badge>}
            {!p.is_active && <Badge>{t("Inactive")}</Badge>}
          </span>}
          actions={can("admin", "manager") && <Button onClick={() => setEditing(true)}>{t("Edit product")}</Button>}
        />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <Card title={<span className="flex items-center gap-2">{t("Product settings")} <SimulatedTag /></span>}>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
            <Item label={t("Price")} value={fmtMoney(p.unit_price)} />
            <Item label={t("Unit cost")} value={fmtMoney(p.unit_cost)} />
            <Item label={t("On hand")} value={`${fmtInt(p.on_hand)} units`} />
            <Item label={t("Supplier")} value={p.supplier?.name ?? "—"} />
            <Item label={t("Shelf")} value={p.shelf ? `${p.shelf.code} · ${p.shelf.name}` : t("No shelf set")} />
            <Item label={t("Lead time")} value={p.effective_lead_time_days ? `${p.effective_lead_time_days} days${p.lead_time_days ? " (override)" : ""}` : "—"} />
            <Item label={t("Minimum order")} value={fmtInt(p.min_order_qty)} />
            <Item label={t("Pack size")} value={fmtInt(p.pack_size)} />
            <Item label={t("Updated")} value={fmtDate(p.updated_at)} />
          </dl>
          <div className="mt-4 flex gap-3 text-sm">
            <Link to={`/forecasts?product=${p.id}`} className="text-brand-600 hover:underline">{t("Forecast")}</Link>
            <Link to={`/inventory?search=${encodeURIComponent(p.sku)}`} className="text-brand-600 hover:underline">{t("Stock movements")}</Link>
          </div>
        </Card>

        <Card className="lg:col-span-2" title={t("Sales history (actual)")}
              actions={<FilterSelect label={t("Period")} value={days} onChange={setDays}>
                <option value="30">{t("Last 30 days")}</option>
                <option value="90">{t("Last 90 days")}</option>
                <option value="365">{t("Last 365 days")}</option>
                <option value="fy">{t("This fiscal year (from 1 Shrawan)")}</option>
              </FilterSelect>}>
          {history.error && <ErrorMessage message={history.error} onRetry={history.reload} />}
          {history.loading && !h && <Skeleton variant="text" label={t("Loading sales…")} />}
          {h && (
            <>
              <div className="mb-3 grid grid-cols-3 gap-3 text-sm">
                <Item label={t("Units sold")} value={fmtInt(h.total_units)} />
                <Item label={t("Per available day")} value={availableDays ? fmtDecimal(h.total_units / availableDays) : "—"} />
                <Item label={t("Days with no sales")} value={fmtInt(h.points.filter((x) => x.is_available && x.units === 0).length)} />
              </div>
              <DailySalesChart history={h} />
              <p className="mt-2 text-xs text-slate-500">{t("Grey bars: item not on sale or store closed (not counted as demand).")}</p>
            </>
          )}
        </Card>
      </div>

      <Dialog title={`Edit ${p.sku}`} open={editing} onClose={() => setEditing(false)} wide>
        <ProductForm product={p} categories={reference.data?.categories ?? []} suppliers={reference.data?.suppliers ?? []}
                     shelves={reference.data?.shelves ?? []}
                     onCancel={() => setEditing(false)}
                     onSaved={() => { setEditing(false); product.reload(); }} />
      </Dialog>
    </>
  );
}

function Item({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-slate-500">{label}</dt>
      <dd className="font-medium text-slate-800 tabular-nums">{value}</dd>
    </div>
  );
}
