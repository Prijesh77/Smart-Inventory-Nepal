import { useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { api, ApiError } from "../../api/client";
import type { Page, Product, Shelf } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { Dialog } from "../../components/Dialog";
import { TextField } from "../../components/fields";
import { Badge, Button, Card, EmptyState, ErrorMessage, PageHeader, Skeleton } from "../../components/ui";
import { useToast } from "../../components/Toast";
import { useApi } from "../../hooks/useApi";
import { useDebounce } from "../../hooks/useDebounce";
import { fmtInt } from "../../lib/format";
import { t } from "../../lib/i18n";

const NO_SHELF = "0";

/** Where things are kept: find a product's shelf, or pick a shelf to see what is on it. */
export function ShelvesPage() {
  const { can } = useAuth();
  const canEdit = can("admin", "manager");
  const toast = useToast();
  const [params, setParams] = useSearchParams();
  const selected = params.get("shelf");
  const [editing, setEditing] = useState<Shelf | "new" | null>(null);
  const shelves = useApi((signal) => api.get<Shelf[]>("/shelves", undefined, signal));
  const unplaced = useApi((signal) => api.get<Page<Product>>("/products", { shelf_id: 0, is_active: true, page_size: 1 }, signal));
  const current = shelves.data?.find((s) => String(s.id) === selected) ?? null;

  function pick(id: string | null) {
    const next = new URLSearchParams(params);
    if (id) next.set("shelf", id); else next.delete("shelf");
    setParams(next, { replace: true });
  }

  function reloadAll() {
    shelves.reload();
    unplaced.reload();
  }

  async function remove(shelf: Shelf) {
    if (!window.confirm(t("Delete shelf {code}? Its products stay, without a shelf.", { code: shelf.code }))) return;
    try {
      await api.delete(`/shelves/${shelf.id}`);
      toast(t("Shelf {code} deleted.", { code: shelf.code }));
      pick(null);
      reloadAll();
    } catch (err) {
      toast(err instanceof ApiError ? err.message : t("Could not delete the shelf"));
    }
  }

  const areas = groupByArea(shelves.data ?? []);

  return (
    <>
      <PageHeader title={t("Shelves")}
                  description={t("Where each product is kept. Search for a product to find its shelf, or pick a shelf to see what is on it.")}
                  actions={canEdit && <Button onClick={() => setEditing("new")}>{t("Add shelf")}</Button>} />

      <Card className="mb-6" title={t("Where is it?")}>
        <FindProduct />
      </Card>

      {shelves.error && <ErrorMessage message={shelves.error} onRetry={shelves.reload} />}
      {shelves.loading && !shelves.data && <Skeleton variant="cards" rows={4} label={t("Loading shelves…")} />}
      {shelves.data && shelves.data.length === 0 && (
        <EmptyState icon="shelf" title={t("No shelves yet")}
                    action={canEdit ? <Button onClick={() => setEditing("new")}>{t("Add shelf")}</Button> : undefined}>
          {t("Add your shelves (for example A-1, Aisle A top shelf), then choose a shelf for each product, or add a shelf column to the product import.")}
        </EmptyState>
      )}

      {areas.map(([area, list]) => (
        <section key={area} className="mb-6" aria-label={area}>
          <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">{area}</h2>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {list.map((s) => (
              <ShelfTile key={s.id} code={s.code} name={s.name} count={s.product_count} active={String(s.id) === selected}
                         onClick={() => pick(String(s.id) === selected ? null : String(s.id))} />
            ))}
          </div>
        </section>
      ))}
      {shelves.data && shelves.data.length > 0 && (unplaced.data?.total ?? 0) > 0 && (
        <div className="mb-6 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <ShelfTile code="—" name={t("Not on a shelf yet")} count={unplaced.data!.total} active={selected === NO_SHELF}
                     onClick={() => pick(selected === NO_SHELF ? null : NO_SHELF)} muted />
        </div>
      )}

      {(current || selected === NO_SHELF) && (
        <Card title={current ? `${current.code} · ${current.name}` : t("Products not on a shelf yet")}
              subtitle={current?.area ?? undefined}
              actions={current && canEdit && (
                <div className="flex gap-2">
                  <Button variant="secondary" onClick={() => setEditing(current)}>{t("Edit")}</Button>
                  <Button variant="secondary" onClick={() => remove(current)}>{t("Delete")}</Button>
                </div>
              )}>
          <ShelfProducts shelfId={current ? current.id : 0} />
        </Card>
      )}

      <Dialog title={editing === "new" ? t("Add shelf") : t("Edit shelf")} open={editing !== null} onClose={() => setEditing(null)}>
        {editing !== null && (
          <ShelfForm shelf={editing === "new" ? undefined : editing} onCancel={() => setEditing(null)}
                     onSaved={(s) => {
                       setEditing(null);
                       toast(t("Shelf {code} saved.", { code: s.code }));
                       reloadAll();
                       pick(String(s.id));
                     }} />
        )}
      </Dialog>
    </>
  );
}

export function groupByArea(shelves: Shelf[]): [string, Shelf[]][] {
  const groups = new Map<string, Shelf[]>();
  for (const s of shelves) {
    const area = s.area || t("Other shelves");
    groups.set(area, [...(groups.get(area) ?? []), s]);
  }
  return [...groups.entries()];
}

function ShelfTile({ code, name, count, active, onClick, muted = false }:
  { code: string; name: string; count: number; active: boolean; onClick: () => void; muted?: boolean }) {
  return (
    <button type="button" onClick={onClick} aria-pressed={active}
            className={`flex items-start gap-3 rounded-xl border p-4 text-left transition-colors ${
              active ? "border-brand-500 bg-brand-50 ring-1 ring-brand-500" : "border-slate-200 bg-white hover:border-brand-300"}`}>
      <span className={`flex h-10 min-w-[2.5rem] items-center justify-center rounded-lg px-2 text-sm font-bold ${
        muted ? "bg-slate-100 text-slate-500" : "bg-brand-600 text-white"}`}>{code}</span>
      <span className="min-w-0">
        <span className="block font-medium text-slate-900">{name}</span>
        <span className="block text-sm text-slate-500">{t(count === 1 ? "{n} product" : "{n} products", { n: fmtInt(count) })}</span>
      </span>
    </button>
  );
}

function ShelfProducts({ shelfId }: { shelfId: number }) {
  const { data, error, loading, reload } = useApi(
    (signal) => api.get<Page<Product>>("/products", { shelf_id: shelfId, is_active: true, page_size: 100, sort: "name" }, signal),
    [shelfId],
  );
  if (error) return <ErrorMessage message={error} onRetry={reload} />;
  if (loading && !data) return <Skeleton label={t("Loading products…")} />;
  if (!data || data.items.length === 0) return <p className="text-sm text-slate-500">{t("No products on this shelf.")}</p>;
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-sm">
        <thead className="text-left text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <th scope="col" className="py-2 pr-4 font-medium">{t("Product")}</th>
            <th scope="col" className="py-2 pr-4 font-medium">{t("Category")}</th>
            <th scope="col" className="py-2 text-right font-medium">{t("On hand")}</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {data.items.map((p) => (
            <tr key={p.id}>
              <td className="py-2 pr-4">
                <Link to={`/products/${p.id}`} className="font-medium text-brand-600 hover:underline">{p.sku}</Link>
                <span className="ml-2 text-slate-600">{p.name}</span>
              </td>
              <td className="py-2 pr-4 text-slate-600">{p.category.name}</td>
              <td className="py-2 text-right tabular-nums">
                {p.on_hand > 0 ? fmtInt(p.on_hand) : <Badge tone="red">{t("Out of stock")}</Badge>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {data.total > data.items.length && (
        <p className="mt-2 text-xs text-slate-500">{t("Showing the first {n} products.", { n: fmtInt(data.items.length) })}</p>
      )}
    </div>
  );
}

function FindProduct() {
  const [text, setText] = useState("");
  const search = useDebounce(text, 250);
  const { data } = useApi(
    (signal) => search.trim() ? api.get<Page<Product>>("/products", { search, page_size: 8, is_active: true }, signal) : Promise.resolve(null),
    [search],
  );
  return (
    <div>
      <label htmlFor="find-product" className="block text-sm font-medium text-slate-700">{t("Product")}</label>
      <input id="find-product" type="search" autoComplete="off" value={text} onChange={(e) => setText(e.target.value)}
             placeholder={t("Type a SKU or name…")} className="mt-1 w-full max-w-md rounded-md border border-slate-300 px-3 py-2 text-sm" />
      {data && data.items.length === 0 && <p className="mt-3 text-sm text-slate-500">{t("No products match.")}</p>}
      {data && data.items.length > 0 && (
        <ul className="mt-3 divide-y divide-slate-100 rounded-lg border border-slate-200" aria-label={t("Where the products are")}>
          {data.items.map((p) => (
            <li key={p.id} className="flex items-center justify-between gap-3 px-3 py-2 text-sm">
              <span className="min-w-0">
                <Link to={`/products/${p.id}`} className="font-medium text-brand-600 hover:underline">{p.sku}</Link>
                <span className="ml-2 text-slate-600">{p.name}</span>
              </span>
              {p.shelf ? (
                <span className="shrink-0 text-right">
                  <span className="rounded-md bg-brand-600 px-2 py-0.5 text-xs font-bold text-white">{p.shelf.code}</span>
                  <span className="ml-2 text-slate-600">{p.shelf.name}</span>
                </span>
              ) : <span className="shrink-0 text-slate-400">{t("No shelf set")}</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

const CODE = /^[A-Za-z0-9_-]+$/;

export function ShelfForm({ shelf, onSaved, onCancel }: { shelf?: Shelf; onSaved: (s: Shelf) => void; onCancel: () => void }) {
  const [code, setCode] = useState(shelf?.code ?? "");
  const [name, setName] = useState(shelf?.name ?? "");
  const [area, setArea] = useState(shelf?.area ?? "");
  const [errors, setErrors] = useState<{ code?: string; name?: string }>({});
  const [serverError, setServerError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const found: { code?: string; name?: string } = {};
    if (!CODE.test(code.trim())) found.code = t("Use letters, digits, '-' or '_', e.g. A-1");
    if (!name.trim()) found.name = t("Name is required");
    setErrors(found);
    setServerError(null);
    if (Object.keys(found).length) return;
    setSaving(true);
    try {
      const body = { code: code.trim(), name: name.trim(), area: area.trim() || null };
      onSaved(shelf ? await api.patch<Shelf>(`/shelves/${shelf.id}`, body) : await api.post<Shelf>("/shelves", body));
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) setErrors({ code: err.message });
      else setServerError(err instanceof ApiError ? err.message : t("Could not save the shelf"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={onSubmit} noValidate className="space-y-4">
      {serverError && <ErrorMessage message={serverError} />}
      <TextField id="shelf-code" label={t("Shelf code")} value={code} onChange={(e) => setCode(e.target.value)} error={errors.code}
                 hint={t("Short label on the shelf, e.g. A-1 or STORE")} />
      <TextField id="shelf-name" label={t("Name")} value={name} onChange={(e) => setName(e.target.value)} error={errors.name}
                 hint={t("e.g. Aisle A: rice, dal and flour")} />
      <TextField id="shelf-area" label={t("Area (optional)")} value={area} onChange={(e) => setArea(e.target.value)}
                 hint={t("Groups shelves on this page, e.g. Front shop or Storeroom")} />
      <div className="flex justify-end gap-2 border-t border-slate-100 pt-4">
        <Button variant="secondary" onClick={onCancel}>{t("Cancel")}</Button>
        <Button type="submit" disabled={saving}>{saving ? t("Saving…") : t("Save shelf")}</Button>
      </div>
    </form>
  );
}
