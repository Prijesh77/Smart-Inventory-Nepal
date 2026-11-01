import { useState, type FormEvent } from "react";

import { api, ApiError } from "../../api/client";
import type { PurchaseOrder, Supplier } from "../../api/types";
import { SelectField, TextField } from "../../components/fields";
import { ProductPicker } from "../../components/ProductPicker";
import { Button, ErrorMessage } from "../../components/ui";
import { currencySymbol, inputToMoney, moneyToInput } from "../../lib/currency";
import { fmtLocalMoney } from "../../lib/format";

export interface DraftLine {
  product_id: number;
  sku: string;
  name: string;
  quantity: string;
  unit_cost: string;
}

/** Check lines the same way the API does: at least one, quantity a whole number > 0, cost >= 0 with 2 decimals. */
export function lineErrors(lines: DraftLine[]): string | null {
  if (!lines.length) return "Add at least one product";
  for (const l of lines) {
    if (!/^\d+$/.test(l.quantity) || Number(l.quantity) < 1) return `${l.sku}: quantity must be a whole number of at least 1`;
    if (l.unit_cost && !/^\d+(\.\d{1,2})?$/.test(l.unit_cost)) return `${l.sku}: unit cost must look like 2.75`;
  }
  return null;
}

export function linesBody(lines: DraftLine[]) {
  return lines.map((l) => ({ product_id: l.product_id, quantity: Number(l.quantity), unit_cost: inputToMoney(l.unit_cost) || null }));
}

/** Line total in the currency the costs were typed in. */
export function lineTotal(l: DraftLine): number | null {
  return l.unit_cost && /^\d+$/.test(l.quantity) ? Number(l.unit_cost) * Number(l.quantity) : null;
}

/** Create a draft order, or edit an existing draft (same form). */
export function OrderForm({ order, suppliers, onSaved, onCancel }: {
  order?: PurchaseOrder;
  suppliers: Supplier[];
  onSaved: (po: PurchaseOrder) => void;
  onCancel: () => void;
}) {
  const [supplierId, setSupplierId] = useState(order ? String(order.supplier_id) : "");
  const [notes, setNotes] = useState(order?.notes ?? "");
  const [expected, setExpected] = useState(order?.expected_date ?? "");
  const [lines, setLines] = useState<DraftLine[]>(() => order?.lines.map((l) => ({
    product_id: l.product_id, sku: l.sku, name: l.name, quantity: String(l.quantity_ordered), unit_cost: moneyToInput(l.unit_cost),
  })) ?? []);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const setLine = (i: number, change: Partial<DraftLine>) =>
    setLines((all) => all.map((l, j) => (j === i ? { ...l, ...change } : l)));
  const total = lines.reduce((s, l) => s + (lineTotal(l) ?? 0), 0);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const problem = !supplierId ? "Choose a supplier" : lineErrors(lines);
    setError(problem);
    if (problem) return;
    setSaving(true);
    try {
      const body = { notes: notes.trim() || null, expected_date: expected || null, lines: linesBody(lines) };
      const saved = order
        ? await api.patch<PurchaseOrder>(`/purchase-orders/${order.id}`, body)
        : await api.post<PurchaseOrder>("/purchase-orders", { ...body, supplier_id: Number(supplierId) });
      onSaved(saved);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save the order");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={onSubmit} noValidate className="space-y-4">
      {error && <ErrorMessage message={error} />}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <SelectField id="po-supplier" label="Supplier" value={supplierId} disabled={!!order || lines.length > 0}
                     onChange={(e) => setSupplierId(e.target.value)}>
          <option value="">Choose…</option>
          {suppliers.map((s) => <option key={s.id} value={s.id}>{s.name} ({s.lead_time_days}-day lead time)</option>)}
        </SelectField>
        <TextField id="po-expected" label="Expected delivery (optional)" type="date" value={expected}
                   onChange={(e) => setExpected(e.target.value)} hint="Empty = set from the lead time when submitted" />
      </div>
      {supplierId && (
        <ProductPicker label="Add a product from this supplier" selected={null} supplierId={Number(supplierId)}
                       onSelect={(p) => setLines((all) => all.some((l) => l.product_id === p.id) ? all
                         : [...all, { product_id: p.id, sku: p.sku, name: p.name, quantity: "1", unit_cost: moneyToInput(p.unit_cost) }])} />
      )}
      {lines.length > 0 && (
        <table className="min-w-full text-sm">
          <thead className="text-left text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th scope="col" className="py-2 pr-3 font-medium">Product</th>
              <th scope="col" className="py-2 pr-3 font-medium">Quantity</th>
              <th scope="col" className="py-2 pr-3 font-medium">Unit cost ({currencySymbol()})</th>
              <th scope="col" className="py-2 pr-3 text-right font-medium">Line total</th>
              <th scope="col"><span className="sr-only">Remove</span></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {lines.map((l, i) => (
              <tr key={l.product_id}>
                <td className="py-2 pr-3"><span className="font-medium">{l.sku}</span> <span className="text-slate-500">{l.name}</span></td>
                <td className="py-2 pr-3">
                  <input aria-label={`Quantity for ${l.sku}`} inputMode="numeric" value={l.quantity}
                         onChange={(e) => setLine(i, { quantity: e.target.value.trim() })}
                         className="w-24 rounded-md border border-slate-300 px-2 py-1" />
                </td>
                <td className="py-2 pr-3">
                  <input aria-label={`Unit cost for ${l.sku}`} inputMode="decimal" value={l.unit_cost}
                         onChange={(e) => setLine(i, { unit_cost: e.target.value.trim() })}
                         className="w-24 rounded-md border border-slate-300 px-2 py-1" />
                </td>
                <td className="py-2 pr-3 text-right tabular-nums">{fmtLocalMoney(lineTotal(l))}</td>
                <td className="py-2 text-right">
                  <Button variant="ghost" onClick={() => setLines((all) => all.filter((_, j) => j !== i))}
                          aria-label={`Remove ${l.sku}`}>✕</Button>
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <td colSpan={3} className="pt-2 text-right text-sm text-slate-500">Total</td>
              <td className="pt-2 text-right font-semibold tabular-nums">{fmtLocalMoney(total)}</td>
            </tr>
          </tfoot>
        </table>
      )}
      <TextField id="po-notes" label="Notes (optional)" value={notes} maxLength={2000} onChange={(e) => setNotes(e.target.value)} />
      <div className="flex justify-end gap-2 border-t border-slate-100 pt-4">
        <Button variant="secondary" onClick={onCancel}>Cancel</Button>
        <Button type="submit" disabled={saving}>{saving ? "Saving…" : order ? "Save draft" : "Create draft"}</Button>
      </div>
    </form>
  );
}
