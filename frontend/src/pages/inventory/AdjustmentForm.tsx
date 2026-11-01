import { useState, type FormEvent } from "react";

import { api, ApiError } from "../../api/client";
import type { ManualMovement, StockItem, TransactionRow } from "../../api/types";
import { SelectField, TextField } from "../../components/fields";
import { Button, ErrorMessage } from "../../components/ui";
import { fmtInt } from "../../lib/format";

/**
 * Which directions each movement type allows (same rules as the API):
 * an adjustment can add or remove; a sale removes; a return adds.
 */
const DIRECTIONS: Record<ManualMovement, ("add" | "remove")[]> = {
  adjustment: ["add", "remove"],
  sale: ["remove"],
  return: ["add"],
};

export function signedQuantity(direction: "add" | "remove", amount: number): number {
  return direction === "remove" ? -amount : amount;
}

export function AdjustmentForm({ item, onSaved, onCancel }:
  { item: StockItem; onSaved: (txn: TransactionRow) => void; onCancel: () => void }) {
  const [type, setType] = useState<ManualMovement>("adjustment");
  const [direction, setDirection] = useState<"add" | "remove">("remove");
  const [amount, setAmount] = useState("");
  const [reason, setReason] = useState("");
  const [errors, setErrors] = useState<{ amount?: string; reason?: string }>({});
  const [serverError, setServerError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const allowed = DIRECTIONS[type];
  const effectiveDirection = allowed.includes(direction) ? direction : allowed[0];
  const qty = /^\d+$/.test(amount) ? Number(amount) : 0;
  const after = item.on_hand + signedQuantity(effectiveDirection, qty);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const found: typeof errors = {};
    if (!/^\d+$/.test(amount) || qty < 1) found.amount = "Enter a whole number of at least 1";
    else if (after < 0) found.amount = `Only ${fmtInt(item.on_hand)} on hand; stock cannot go below 0`;
    if (reason.trim().length < 3) found.reason = "Explain the change (at least 3 characters); it is kept in the audit log";
    setErrors(found);
    setServerError(null);
    if (Object.keys(found).length) return;
    setSaving(true);
    try {
      const txn = await api.post<TransactionRow>("/inventory/adjustments", {
        product_id: item.product_id, txn_type: type, quantity: signedQuantity(effectiveDirection, qty), reason: reason.trim(),
      });
      onSaved(txn);
    } catch (err) {
      setServerError(err instanceof ApiError ? err.message : "Could not record the movement");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={onSubmit} noValidate className="space-y-4">
      <p className="text-sm text-slate-600">
        <span className="font-medium text-slate-800">{item.sku}</span> · {item.name} · currently{" "}
        <strong>{fmtInt(item.on_hand)}</strong> on hand
      </p>
      {serverError && <ErrorMessage message={serverError} />}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <SelectField id="txn-type" label="Type" value={type} onChange={(e) => setType(e.target.value as ManualMovement)}>
          <option value="adjustment">Adjustment (count, damage, loss)</option>
          <option value="sale">Sale</option>
          <option value="return">Customer return</option>
        </SelectField>
        <SelectField id="direction" label="Direction" value={effectiveDirection} disabled={allowed.length === 1}
                     onChange={(e) => setDirection(e.target.value as "add" | "remove")}>
          {allowed.map((d) => <option key={d} value={d}>{d === "add" ? "Add to stock" : "Remove from stock"}</option>)}
        </SelectField>
        <TextField id="amount" label="Units" inputMode="numeric" value={amount} error={errors.amount}
                   onChange={(e) => setAmount(e.target.value.trim())} />
      </div>
      <TextField id="reason" label="Reason" value={reason} error={errors.reason} maxLength={500}
                 placeholder="e.g. Weekly count found 3 damaged boxes" onChange={(e) => setReason(e.target.value)} />
      {qty > 0 && (
        <p className={`rounded-md p-3 text-sm ${after < 0 ? "bg-red-50 text-red-800" : "bg-slate-50 text-slate-700"}`}
           aria-live="polite">
          Stock will change from {fmtInt(item.on_hand)} to <strong>{fmtInt(after)}</strong>
          {after < 0 && " — not allowed"}.
        </p>
      )}
      <div className="flex justify-end gap-2 border-t border-slate-100 pt-4">
        <Button variant="secondary" onClick={onCancel}>Cancel</Button>
        <Button type="submit" disabled={saving}>{saving ? "Saving…" : "Record movement"}</Button>
      </div>
    </form>
  );
}
