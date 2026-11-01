import { useState } from "react";

import { api, ApiError } from "../../api/client";
import type { ImportJob, ImportPreview } from "../../api/types";
import { TextField } from "../../components/fields";
import { Button, ErrorMessage, Spinner } from "../../components/ui";
import { fmtDate, fmtInt, fmtMoney } from "../../lib/format";

const MAX_BYTES = 5 * 1024 * 1024;
export const TEMPLATE = "sku,date,units,unit_price\nFOODS_1_013,2016-05-23,4,1.50\nHOBBIES_1_001,2016-05-23,0,\n";

interface Mapping { sku: string; date: string; units: string; price: string }

export function buildForm(file: File, m: Mapping): FormData {
  const form = new FormData();
  form.append("file", file);
  form.append("sku_column", m.sku.trim() || "sku");
  form.append("date_column", m.date.trim() || "date");
  form.append("units_column", m.units.trim() || "units");
  form.append("price_column", m.price.trim());
  return form;
}

function downloadTemplate() {
  const url = URL.createObjectURL(new Blob([TEMPLATE], { type: "text/csv" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = "sales_import_template.csv";
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/**
 * Two steps, never one: check the file (nothing saved), then import.
 * The API imports every row or none, so a file with any bad row is refused as a whole.
 */
export function SalesImport({ onImported }: { onImported: (job: ImportJob) => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [mapping, setMapping] = useState<Mapping>({ sku: "sku", date: "date", units: "units", price: "unit_price" });
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [busy, setBusy] = useState<"check" | "import" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  function choose(f: File | null) {
    setPreview(null);
    setDone(null);
    setError(null);
    if (f && f.size > MAX_BYTES) {
      setFile(null);
      setError("The file is larger than 5 MB; split it into smaller files");
      return;
    }
    setFile(f);
  }

  async function check() {
    if (!file) return;
    setBusy("check");
    setError(null);
    setPreview(null);
    try {
      setPreview(await api.upload<ImportPreview>("/imports/sales/preview", buildForm(file, mapping)));
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
      const job = await api.upload<ImportJob>("/imports/sales", buildForm(file, mapping));
      setDone(`Imported ${file.name}: ${fmtInt(job.errors?.added ?? 0)} rows added, ${fmtInt(job.errors?.replaced ?? 0)} replaced.`);
      setPreview(null);
      setFile(null);
      onImported(job);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The import failed; nothing was saved");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-slate-600">
        Add daily sales from a CSV file. Required columns: SKU, date (YYYY-MM-DD) and units sold; price is optional.
        Sales feed the forecasts; they do <strong>not</strong> change stock levels.{" "}
        <button type="button" onClick={downloadTemplate} className="text-brand-600 underline">Download a template</button>
      </p>
      <div>
        <label htmlFor="import-file" className="block text-sm font-medium text-slate-700">CSV file (UTF-8, up to 5 MB)</label>
        <input id="import-file" type="file" accept=".csv,text/csv" onChange={(e) => choose(e.target.files?.[0] ?? null)}
               className="mt-1 block text-sm file:mr-3 file:rounded-md file:border-0 file:bg-brand-50 file:px-3 file:py-2 file:text-brand-700" />
      </div>
      <details>
        <summary className="cursor-pointer text-sm text-slate-700">Column names in my file are different</summary>
        <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-4">
          <TextField id="map-sku" label="SKU column" value={mapping.sku} onChange={(e) => setMapping({ ...mapping, sku: e.target.value })} />
          <TextField id="map-date" label="Date column" value={mapping.date} onChange={(e) => setMapping({ ...mapping, date: e.target.value })} />
          <TextField id="map-units" label="Units column" value={mapping.units} onChange={(e) => setMapping({ ...mapping, units: e.target.value })} />
          <TextField id="map-price" label="Price column (optional)" value={mapping.price} onChange={(e) => setMapping({ ...mapping, price: e.target.value })} />
        </div>
      </details>
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
               ["Would be added", preview.would_add], ["Would replace existing", preview.would_replace]] as const).map(([k, v]) => (
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
          {preview.preview.length > 0 && (
            <details open={preview.can_import}>
              <summary className="cursor-pointer text-sm text-slate-700">First {preview.preview.length} valid rows</summary>
              <table className="mt-2 min-w-full text-sm">
                <thead className="text-left text-xs uppercase tracking-wide text-slate-500">
                  <tr><th scope="col" className="py-1 pr-3">SKU</th><th scope="col" className="py-1 pr-3">Date</th>
                    <th scope="col" className="py-1 pr-3 text-right">Units</th><th scope="col" className="py-1 text-right">Price</th></tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {preview.preview.map((r) => (
                    <tr key={`${r.sku}-${r.sales_date}`}>
                      <td className="py-1 pr-3">{r.sku}</td><td className="py-1 pr-3">{fmtDate(r.sales_date)}</td>
                      <td className="py-1 pr-3 text-right tabular-nums">{fmtInt(r.units)}</td><td className="py-1 text-right tabular-nums">{fmtMoney(r.unit_price)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </details>
          )}
          {preview.can_import && (
            <div className="flex items-center justify-between gap-3 border-t border-slate-100 pt-3">
              <p className="text-sm text-slate-600">
                All {fmtInt(preview.rows_total)} rows are valid.
                {preview.would_replace > 0 && ` ${fmtInt(preview.would_replace)} existing day(s) will be replaced.`}
              </p>
              <Button onClick={runImport} disabled={busy !== null}>Import {fmtInt(preview.rows_total)} rows</Button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
