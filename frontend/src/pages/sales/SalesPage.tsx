import { useState, type FormEvent } from "react";

import { api, ApiError } from "../../api/client";
import type { SalesDay, SaleLine } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { DateField } from "../../components/DateField";
import { Dialog } from "../../components/Dialog";
import { TextField } from "../../components/fields";
import { ProductPicker } from "../../components/ProductPicker";
import { useToast } from "../../components/Toast";
import { Button, Card, EmptyState, ErrorMessage, Notice, PageHeader, Skeleton } from "../../components/ui";
import { useApi } from "../../hooks/useApi";
import { fmtDate, fmtInt, fmtMoney } from "../../lib/format";

interface DraftLine { id: number; sku: string; name: string; units: string }

/** Today in the user's own time zone, as the API's "YYYY-MM-DD". */
export function todayIso(now = new Date()): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

export const validUnits = (text: string) => /^\d+$/.test(text) && Number(text) >= 1 && Number(text) <= 100_000;

/**
 * Counter sales for one day. Saving adds the units to that day's sales (what the forecasts learn from)
 * and takes them out of stock. Nothing is saved unless every line can be.
 */
export function SalesPage() {
  const { can } = useAuth();
  const canRecord = can("admin", "manager");
  const toast = useToast();
  const today = todayIso();
  const [day, setDay] = useState<string | null>(today);
  const [draft, setDraft] = useState<DraftLine[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [correcting, setCorrecting] = useState<SaleLine | null>(null);
  const [version, setVersion] = useState(0);
  const recorded = useApi(
    (signal) => day ? api.get<SalesDay>("/sales", { date: day }, signal) : Promise.resolve(null),
    [day, version],
  );

  function addLine(p: { id: number; sku: string; name: string }) {
    setError(null);
    setDraft((lines) => lines.some((l) => l.id === p.id) ? lines : [...lines, { ...p, units: "1" }]);
  }

  async function send(body: { items: { product_id: number; units: number }[]; close_day?: boolean }, done: (r: SalesDay) => string) {
    if (!day) return false;
    setBusy(true);
    setError(null);
    try {
      toast(done(await api.post<SalesDay>("/sales", { sales_date: day, ...body })));
      setVersion((v) => v + 1);
      return true;
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save; nothing was recorded");
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (draft.some((l) => !validUnits(l.units))) return setError("Units must be whole numbers of at least 1");
    const units = draft.reduce((sum, l) => sum + Number(l.units), 0);
    const ok = await send({ items: draft.map((l) => ({ product_id: l.id, units: Number(l.units) })) },
      () => `Recorded ${fmtInt(units)} units across ${fmtInt(draft.length)} product${draft.length > 1 ? "s" : ""}. Stock is updated.`);
    if (ok) setDraft([]);
  }

  const closeDay = () => send({ items: [], close_day: true },
    (r) => r.zero_rows_added ? `Day marked complete: ${fmtInt(r.zero_rows_added)} products recorded as 0 sold.` : "This day was already complete.");

  const data = recorded.data;
  const complete = !!data && data.active_products > 0 && data.products_recorded >= data.active_products;

  return (
    <>
      <PageHeader title="Record sales"
                  description="Enter what was sold at the counter. Each sale is added to the day's total and taken out of stock, so forecasts and reorder suggestions stay up to date." />

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-5">
        <div className="space-y-6 xl:col-span-2">
          <Card title="Sales date">
            <DateField id="sales-date" label="Date" value={day ?? today} max={today} onChange={(iso) => setDay(iso || null)}
                       hint="Up to 60 days back; older history goes through the Excel import in Settings" />
          </Card>

          {canRecord ? (
            <Card title="Add sales" subtitle="Search for a product, set the units sold, then save.">
              <form onSubmit={save} noValidate className="space-y-4">
                <ProductPicker label="Product" selected={null} onSelect={addLine} />
                {error && <ErrorMessage message={error} />}
                {draft.length > 0 && (
                  <ul aria-label="Sales to save" className="divide-y divide-slate-100 rounded-lg border border-slate-200">
                    {draft.map((line) => (
                      <li key={line.id} className="flex items-center gap-3 px-3 py-2">
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-sm font-medium text-slate-800">{line.sku}</p>
                          <p className="truncate text-xs text-slate-500">{line.name}</p>
                        </div>
                        <input aria-label={`Units sold, ${line.sku}`} inputMode="numeric" value={line.units}
                               aria-invalid={!validUnits(line.units)}
                               onChange={(e) => setDraft((ls) => ls.map((l) => l.id === line.id ? { ...l, units: e.target.value.trim() } : l))}
                               className={`w-20 rounded-md border px-2 py-1.5 text-right text-sm tabular-nums ${
                                 validUnits(line.units) ? "border-slate-300" : "border-red-400"}`} />
                        <Button variant="ghost" aria-label={`Remove ${line.sku}`}
                                onClick={() => setDraft((ls) => ls.filter((l) => l.id !== line.id))}>Remove</Button>
                      </li>
                    ))}
                  </ul>
                )}
                <Button type="submit" disabled={busy || !day || draft.length === 0}>
                  {busy ? "Saving…" : draft.length ? `Save ${fmtInt(draft.length)} sale${draft.length > 1 ? "s" : ""}` : "Save sales"}
                </Button>
              </form>
            </Card>
          ) : (
            <Notice tone="info">You can view sales. Recording them needs a manager or admin account.</Notice>
          )}
        </div>

        <div className="xl:col-span-3">
          <Card title={day ? `Recorded for ${fmtDate(day)}` : "Recorded sales"}
                subtitle={data ? `${fmtInt(data.total_units)} units · ${fmtMoney(data.total_amount)}` : undefined}>
            {!day && <EmptyState title="Enter a valid date">Sales are shown one day at a time.</EmptyState>}
            {recorded.error && <ErrorMessage message={recorded.error} onRetry={recorded.reload} />}
            {day && recorded.loading && !data && <Skeleton label="Loading sales…" />}
            {day && data && (data.items.length === 0
              ? <EmptyState icon="money" title="No sales recorded for this day">Sales you save appear here.</EmptyState>
              : (
                <div className="overflow-x-auto">
                  <table className="min-w-full text-sm">
                    <thead className="text-left text-xs uppercase tracking-wide text-slate-500">
                      <tr>
                        <th scope="col" className="py-2 pr-3 font-medium">Product</th>
                        <th scope="col" className="py-2 pr-3 text-right font-medium">Units</th>
                        <th scope="col" className="py-2 pr-3 text-right font-medium">Price</th>
                        <th scope="col" className="py-2 pr-3 text-right font-medium">Amount</th>
                        <th scope="col" className="py-2 pr-3 text-right font-medium">On hand now</th>
                        {canRecord && <th scope="col" className="py-2"><span className="sr-only">Actions</span></th>}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {data.items.map((item) => (
                        <tr key={item.product_id}>
                          <td className="py-2 pr-3"><span className="font-medium text-slate-800">{item.sku}</span>
                            <p className="text-xs text-slate-500">{item.name}</p></td>
                          <td className="py-2 pr-3 text-right font-semibold tabular-nums">{fmtInt(item.units)}</td>
                          <td className="py-2 pr-3 text-right tabular-nums">{fmtMoney(item.unit_price)}</td>
                          <td className="py-2 pr-3 text-right tabular-nums">{fmtMoney(item.amount)}</td>
                          <td className="py-2 pr-3 text-right tabular-nums">{fmtInt(item.on_hand)}</td>
                          {canRecord && <td className="py-2 text-right">
                            <Button variant="ghost" aria-label={`Correct ${item.sku}`} onClick={() => setCorrecting(item)}>Correct</Button>
                          </td>}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ))}
            {day && data && (
              <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-4">
                <p className="text-sm text-slate-600">
                  {complete
                    ? "Day complete: every active product has a sales figure for this day."
                    : `${fmtInt(data.products_recorded)} of ${fmtInt(data.active_products)} products have a figure for this day. ` +
                      "When you finish, mark the day complete so the rest count as 0 sold."}
                </p>
                {canRecord && !complete && <Button variant="secondary" disabled={busy} onClick={closeDay}>Mark day complete</Button>}
              </div>
            )}
          </Card>
        </div>
      </div>

      <Dialog title="Correct a sale" open={!!correcting} onClose={() => setCorrecting(null)}>
        {correcting && day && (
          <CorrectionForm line={correcting} day={day} onCancel={() => setCorrecting(null)}
                          onSaved={(message) => { setCorrecting(null); toast(message); setVersion((v) => v + 1); }} />
        )}
      </Dialog>
    </>
  );
}

/** Take units back off a day's sales (a miscount or a wrong product); the units return to stock. */
function CorrectionForm({ line, day, onSaved, onCancel }:
  { line: SaleLine; day: string; onSaved: (message: string) => void; onCancel: () => void }) {
  const [amount, setAmount] = useState("");
  const [error, setError] = useState<string | undefined>();
  const [saving, setSaving] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!validUnits(amount) || Number(amount) > line.units) return setError(`Enter a whole number from 1 to ${fmtInt(line.units)}`);
    setSaving(true);
    try {
      await api.post<SalesDay>("/sales", { sales_date: day, items: [{ product_id: line.product_id, units: -Number(amount) }] });
      onSaved(`Removed ${fmtInt(Number(amount))} from ${line.sku}; the units are back in stock.`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save the correction");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={submit} noValidate className="space-y-4">
      <p className="text-sm text-slate-600">
        <span className="font-medium text-slate-800">{line.sku}</span> · {line.name} · <strong>{fmtInt(line.units)}</strong> recorded
        for {fmtDate(day)}
      </p>
      <TextField id="correction-units" label="Units to remove" inputMode="numeric" value={amount} error={error}
                 hint="These units go back into stock" onChange={(e) => setAmount(e.target.value.trim())} />
      <div className="flex justify-end gap-2 border-t border-slate-100 pt-4">
        <Button variant="secondary" onClick={onCancel}>Cancel</Button>
        <Button type="submit" disabled={saving}>{saving ? "Saving…" : "Remove units"}</Button>
      </div>
    </form>
  );
}
