import { useState, type FormEvent } from "react";

import { api, ApiError } from "../../api/client";
import { useCurrency } from "../../auth/CurrencyContext";
import { TextField } from "../../components/fields";
import { Button, ErrorMessage } from "../../components/ui";
import { fmtDate } from "../../lib/format";
import type { CurrencyRate } from "../../lib/currency";

/** The rupee exchange rate used for display. Admins can update it from the latest NRB rate. */
export function CurrencyForm({ canEdit }: { canEdit: boolean }) {
  const { rate, reloadRate } = useCurrency();
  const [value, setValue] = useState(String(rate.npr_per_usd));
  const [rateDate, setRateDate] = useState(rate.rate_date ?? "");
  const [source, setSource] = useState(rate.rate_source);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setSaved(false);
    const n = Number(value);
    if (!value.trim() || !(n > 0 && n <= 10_000)) return setError("Enter the rupees for 1 US dollar, e.g. 152.66");
    if (!source.trim()) return setError("Say where the rate comes from, e.g. Nepal Rastra Bank");
    setError(null);
    setSaving(true);
    try {
      await api.put<CurrencyRate>("/settings/currency",
        { npr_per_usd: n, rate_date: rateDate || null, rate_source: source.trim() });
      setSaved(true);
      reloadRate();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save the rate");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-4">
      <p className="text-sm leading-relaxed text-slate-600">
        All amounts are stored in <strong>US dollars</strong>, the currency of the M5 sales data. Use the{" "}
        <strong>Rs / $</strong> switch at the top to choose how they are shown. Rupee values are converted at{" "}
        <strong>Rs {rate.npr_per_usd} = $1</strong> ({rate.rate_source}
        {rate.rate_date ? `, ${fmtDate(rate.rate_date)}` : ""}). Amounts typed in rupees are saved to the nearest
        cent, so they can change by less than Re 1 after saving.
      </p>
      {canEdit ? (
        <form onSubmit={onSubmit} noValidate className="space-y-4">
          {error && <ErrorMessage message={error} />}
          {saved && <p role="status" className="rounded-md bg-emerald-50 p-3 text-sm text-emerald-800">Exchange rate saved.</p>}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <TextField id="fx-rate" label="Rupees per US dollar" inputMode="decimal" value={value}
                       onChange={(e) => setValue(e.target.value)} hint="Nepal Rastra Bank publishes this daily" />
            <TextField id="fx-date" label="Rate date" type="date" value={rateDate} onChange={(e) => setRateDate(e.target.value)} />
            <TextField id="fx-source" label="Source" value={source} maxLength={120} onChange={(e) => setSource(e.target.value)} />
          </div>
          <div className="flex justify-end border-t border-slate-100 pt-4">
            <Button type="submit" disabled={saving}>{saving ? "Saving…" : "Save rate"}</Button>
          </div>
        </form>
      ) : (
        <p className="rounded-md bg-slate-50 p-3 text-sm text-slate-600">Only admins can change the exchange rate.</p>
      )}
    </div>
  );
}
