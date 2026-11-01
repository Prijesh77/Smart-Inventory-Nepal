import { useState } from "react";

import { api, ApiError, downloadFile } from "../../api/client";
import type { ImportJob, ImportPreview, ImportType } from "../../api/types";
import { TextField } from "../../components/fields";
import { Button, ErrorMessage, Spinner } from "../../components/ui";
import { DASH, fmtDate, fmtInt, fmtMoney, humanize } from "../../lib/format";

const MAX_BYTES = 5 * 1024 * 1024;

/** The order a new shop should follow: each step uses what the one before it added. */
export const IMPORT_STEPS: { type: ImportType; label: string; hint: string }[] = [
  { type: "suppliers", label: "Suppliers", hint: "Who you buy from and how many days delivery takes. Existing supplier codes are updated." },
  { type: "products", label: "Products", hint: "Your items with categories and prices in rupees. New categories are created automatically; existing SKUs are updated. New products start with 0 stock." },
  { type: "opening_stock", label: "Opening stock", hint: "Units on hand today, for products that have no stock movements yet. Later changes go through stock adjustments or received orders." },
  { type: "sales", label: "Sales history", hint: "Units sold per product per day. Feeds the forecasts; it does not change stock. Existing days are replaced." },
];

interface Mapping { sku: string; date: string; units: string; price: string }
const DEFAULT_MAPPING: Mapping = { sku: "sku", date: "date", units: "units", price: "unit_price" };

/** The file, plus (for sales only) which column holds each field. */
export function buildForm(file: File, m?: Mapping): FormData {
  const form = new FormData();
  form.append("file", file);
  if (m) {
    form.append("sku_column", m.sku.trim() || "sku");
    form.append("date_column", m.date.trim() || "date");
    form.append("units_column", m.units.trim() || "units");
    form.append("price_column", m.price.trim());
  }
  return form;
}

function cell(key: string, value: unknown): string {
  if (value === null || value === undefined || value === "") return DASH;
  if (key.startsWith("unit_price") || key.startsWith("unit_cost")) return fmtMoney(value as string);
  if (key.endsWith("date")) return fmtDate(String(value));
  if (typeof value === "number") return fmtInt(value);
  return String(value);
}

/**
 * Two steps, never one: check the file (nothing saved), then import.
 * The API imports every row or none, so a file with any bad row is refused as a whole.
 */
export function DataImport({ onImported }: { onImported: (job: ImportJob) => void }) {
  const [type, setType] = useState<ImportType>("suppliers");
  const [file, setFile] = useState<File | null>(null);
  const [mapping, setMapping] = useState<Mapping>(DEFAULT_MAPPING);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [busy, setBusy] = useState<"check" | "import" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const step = IMPORT_STEPS.find((s) => s.type === type)!;
  const form = (f: File) => buildForm(f, type === "sales" ? mapping : undefined);

  function reset() {
    setPreview(null);
    setDone(null);
    setError(null);
  }

  function choose(f: File | null) {
    reset();
    if (f && f.size > MAX_BYTES) {
      setFile(null);
      setError("The file is larger than 5 MB; split it into smaller files");
      return;
    }
    setFile(f);
  }

  function pick(next: ImportType) {
    reset();
    setFile(null);
    setType(next);
  }

  async function template() {
    setError(null);
    try {
      await downloadFile(`/imports/templates/${type}.xlsx`, `${type}_template.xlsx`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The template could not be downloaded");
    }
  }

  async function check() {
    if (!file) return;
    setBusy("check");
    reset();
    try {
      setPreview(await api.upload<ImportPreview>(`/imports/${type}/preview`, form(file)));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The file could not be checked");
    } finally {
      setBusy(null);
    }
  }

  async function runImport() {
    if (!file) return;
    setBusy("import");
    setError(null);
    try {
      const job = await api.upload<ImportJob>(`/imports/${type}`, form(file));
      const counts = job.errors ?? {};
      const extra = counts.categories_added ? `, ${fmtInt(counts.categories_added)} new categories` : "";
      setDone(`Imported ${file.name}: ${fmtInt(counts.added ?? 0)} added, ${fmtInt(counts.replaced ?? 0)} ${type === "sales" ? "replaced" : "updated"}${extra}.`);
      setPreview(null);
      setFile(null);
      onImported(job);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The import failed; nothing was saved");
    } finally {
      setBusy(null);
    }
  }

  const columns = preview?.preview.length ? Object.keys(preview.preview[0]) : [];
  const replaceLabel = type === "sales" ? "Would replace existing days" : "Would update existing";

  return (
    <div className="space-y-4">
      <div role="group" aria-label="What to import" className="flex flex-wrap gap-2">
        {IMPORT_STEPS.map((s, i) => (
          <button key={s.type} type="button" aria-pressed={type === s.type} onClick={() => pick(s.type)}
                  className={`rounded-md px-3 py-1.5 text-sm font-medium ring-1 ring-inset ${type === s.type
                    ? "bg-brand-600 text-white ring-brand-600" : "bg-white text-slate-700 ring-slate-300 hover:bg-slate-50"}`}>
            {i + 1}. {s.label}
          </button>
        ))}
      </div>
      <p className="text-sm text-slate-600">
        {step.hint}{" "}
        <button type="button" onClick={template} className="text-brand-600 underline">Download the Excel template</button>
        {" "}(example rows and an Instructions sheet). A new shop imports in the order 1 to 4.
      </p>
      <div>
        <label htmlFor="import-file" className="block text-sm font-medium text-slate-700">Excel or CSV file (up to 5 MB)</label>
        <input id="import-file" key={type} type="file"
               accept=".xlsx,.csv,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
               onChange={(e) => choose(e.target.files?.[0] ?? null)}
               className="mt-1 block text-sm file:mr-3 file:rounded-md file:border-0 file:bg-brand-50 file:px-3 file:py-2 file:text-brand-700" />
      </div>
      {type === "sales" && (
        <details>
          <summary className="cursor-pointer text-sm text-slate-700">Column names in my file are different</summary>
          <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-4">
            <TextField id="map-sku" label="SKU column" value={mapping.sku} onChange={(e) => setMapping({ ...mapping, sku: e.target.value })} />
            <TextField id="map-date" label="Date column" value={mapping.date} onChange={(e) => setMapping({ ...mapping, date: e.target.value })} />
            <TextField id="map-units" label="Units column" value={mapping.units} onChange={(e) => setMapping({ ...mapping, units: e.target.value })} />
            <TextField id="map-price" label="Price column (optional)" value={mapping.price} onChange={(e) => setMapping({ ...mapping, price: e.target.value })} />
          </div>
        </details>
      )}
      {error && <ErrorMessage message={error} />}
      {done && <p role="status" className="rounded-md bg-emerald-50 p-3 text-sm text-emerald-800">{done}</p>}
      <div className="flex items-center gap-3">
        <Button onClick={check} disabled={!file || busy !== null}>{busy === "check" ? "Checking…" : "Check file"}</Button>
        {busy && <Spinner label={busy === "check" ? "Checking every row…" : "Importing…"} />}
      </div>

      {preview && (
        <div className="space-y-4 rounded-md border border-slate-200 p-4">
          <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-5">
            {([["Rows", preview.rows_total], ["Valid", preview.rows_valid], ["Rows with errors", preview.rows_invalid],
               ["Would be added", preview.would_add], [replaceLabel, preview.would_replace]] as const).map(([k, v]) => (
              <div key={k}>
                <dt className="text-xs text-slate-500">{k}</dt>
                <dd className={`font-semibold tabular-nums ${k === "Rows with errors" && v > 0 ? "text-red-700" : ""}`}>{fmtInt(v)}</dd>
              </div>
            ))}
          </dl>
          {preview.errors.length > 0 && (
            <div role="alert">
              <p className="mb-2 text-sm font-medium text-red-800">
                Fix these rows and check the file again. Nothing will be imported while any row has an error.
              </p>
              <div className="max-h-64 overflow-y-auto">
                <table className="min-w-full text-sm">
                  <thead className="text-left text-xs uppercase tracking-wide text-slate-500">
                    <tr><th scope="col" className="py-1 pr-3">Row</th><th scope="col" className="py-1 pr-3">Column</th><th scope="col" className="py-1">Problem</th></tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {preview.errors.map((e, i) => (
                      <tr key={i}><td className="py-1 pr-3 tabular-nums">{e.row}</td><td className="py-1 pr-3">{e.column}</td><td className="py-1">{e.message}</td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {preview.errors_truncated && <p className="mt-1 text-xs text-slate-500">Only the first {preview.errors.length} errors are listed.</p>}
            </div>
          )}
          {columns.length > 0 && (
            <details open={preview.can_import}>
              <summary className="cursor-pointer text-sm text-slate-700">First {preview.preview.length} valid rows</summary>
              <div className="overflow-x-auto">
                <table className="mt-2 min-w-full text-sm">
                  <thead className="text-left text-xs uppercase tracking-wide text-slate-500">
                    <tr>{columns.map((c) => <th key={c} scope="col" className="whitespace-nowrap py-1 pr-3 font-medium">{humanize(c)}</th>)}</tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {preview.preview.map((r, i) => (
                      <tr key={i}>{columns.map((c) => <td key={c} className="whitespace-nowrap py-1 pr-3">{cell(c, r[c])}</td>)}</tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
          )}
          {preview.can_import && (
            <div className="flex items-center justify-between gap-3 border-t border-slate-100 pt-3">
              <p className="text-sm text-slate-600">
                All {fmtInt(preview.rows_total)} rows are valid.
                {preview.would_replace > 0 && (type === "sales"
                  ? ` ${fmtInt(preview.would_replace)} existing day(s) will be replaced.`
                  : ` ${fmtInt(preview.would_replace)} existing row(s) will be updated.`)}
              </p>
              <Button onClick={runImport} disabled={busy !== null}>Import {fmtInt(preview.rows_total)} rows</Button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
