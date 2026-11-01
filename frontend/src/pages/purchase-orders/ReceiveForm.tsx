import { useState, type FormEvent } from "react";

import { api, ApiError } from "../../api/client";
import type { PurchaseOrder } from "../../api/types";
import { Button, ErrorMessage } from "../../components/ui";
import { fmtInt } from "../../lib/format";

/** Lines to send: only quantities above 0, each no more than what is still expected. */
export function receiveLines(order: PurchaseOrder, qty: Record<number, string>): { lines: { item_id: number; quantity: number }[]; error: string | null } {
  const lines: { item_id: number; quantity: number }[] = [];
  for (const line of order.lines) {
    const text = (qty[line.id] ?? "").trim();
    if (!text || text === "0") continue;
    if (!/^\d+$/.test(text)) return { lines: [], error: `${line.sku}: enter a whole number` };
    if (Number(text) > line.quantity_outstanding)
      return { lines: [], error: `${line.sku}: only ${line.quantity_outstanding} still expected` };
    lines.push({ item_id: line.id, quantity: Number(text) });
  }
  return { lines, error: lines.length ? null : "Enter a quantity for at least one line" };
}

/** Book a delivery. Every line is booked or none (the API guarantees this). */
export function ReceiveForm({ order, onReceived, onCancel }:
  { order: PurchaseOrder; onReceived: (po: PurchaseOrder) => void; onCancel: () => void }) {
  const open = order.lines.filter((l) => l.quantity_outstanding > 0);
  const [qty, setQty] = useState<Record<number, string>>(() =>
    Object.fromEntries(open.map((l) => [l.id, String(l.quantity_outstanding)])));
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const { lines, error: problem } = receiveLines(order, qty);
    setError(problem);
    if (problem) return;
    setSaving(true);
    try {
      onReceived(await api.post<PurchaseOrder>(`/purchase-orders/${order.id}/receive`, { lines }));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not book the delivery");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={onSubmit} noValidate className="space-y-4">
      <p className="text-sm text-slate-600">
        Enter what actually arrived. The full outstanding amount is filled in; lower it for a partial delivery, or set 0 for
        lines that did not arrive. Stock goes up and each line is recorded as a receipt in the inventory log.
      </p>
      {error && <ErrorMessage message={error} />}
      <table className="min-w-full text-sm">
        <thead className="text-left text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <th scope="col" className="py-2 pr-3 font-medium">Product</th>
            <th scope="col" className="py-2 pr-3 text-right font-medium">Ordered</th>
            <th scope="col" className="py-2 pr-3 text-right font-medium">Already received</th>
            <th scope="col" className="py-2 font-medium">Received now</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {open.map((l) => (
            <tr key={l.id}>
              <td className="py-2 pr-3 font-medium">{l.sku}</td>
              <td className="py-2 pr-3 text-right tabular-nums">{fmtInt(l.quantity_ordered)}</td>
              <td className="py-2 pr-3 text-right tabular-nums">{fmtInt(l.quantity_received)}</td>
              <td className="py-2">
                <input aria-label={`Received now for ${l.sku}`} inputMode="numeric" value={qty[l.id] ?? ""}
                       onChange={(e) => setQty((q) => ({ ...q, [l.id]: e.target.value }))}
                       className="w-24 rounded-md border border-slate-300 px-2 py-1" />
                <span className="ml-2 text-xs text-slate-500">of {fmtInt(l.quantity_outstanding)}</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="flex justify-end gap-2 border-t border-slate-100 pt-4">
        <Button variant="secondary" onClick={onCancel}>Cancel</Button>
        <Button type="submit" disabled={saving}>{saving ? "Booking…" : "Book delivery"}</Button>
      </div>
    </form>
  );
}
