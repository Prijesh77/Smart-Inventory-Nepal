import { useEffect, useState, type FormEvent } from "react";

import { api, ApiError } from "../../api/client";
import type { Category, Supplier } from "../../api/types";
import { TextField } from "../../components/fields";
import { Button, EmptyState, ErrorMessage, Skeleton } from "../../components/ui";
import { useToast } from "../../components/Toast";
import { useReference } from "../../hooks/useReference";

const CODE = /^[A-Za-z0-9_-]+$/;
const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

interface SupplierValues { code: string; name: string; lead_time_days: string; contact_email: string }
const EMPTY_SUPPLIER: SupplierValues = { code: "", name: "", lead_time_days: "", contact_email: "" };

export function validateSupplier(v: SupplierValues): Partial<Record<keyof SupplierValues, string>> {
  const e: Partial<Record<keyof SupplierValues, string>> = {};
  if (!v.code.trim()) e.code = "Code is required";
  else if (!CODE.test(v.code.trim()) || v.code.trim().length > 30) e.code = "Up to 30 letters, digits, '-' or '_'";
  if (!v.name.trim()) e.name = "Name is required";
  const days = Number(v.lead_time_days);
  if (!/^\d+$/.test(v.lead_time_days.trim()) || days < 1 || days > 365) e.lead_time_days = "Whole days, 1 to 365";
  if (v.contact_email.trim() && !EMAIL.test(v.contact_email.trim())) e.contact_email = "Not an email address";
  return e;
}

/**
 * The lists that products refer to. A new shop can fill them here one by one,
 * or all at once with the Suppliers and Products imports.
 */
export function CatalogSetup({ canEdit, version }: { canEdit: boolean; version: number }) {
  const { data, error, loading, reload } = useReference();
  const [supplier, setSupplier] = useState<SupplierValues>(EMPTY_SUPPLIER);
  const [supplierErrors, setSupplierErrors] = useState<ReturnType<typeof validateSupplier>>({});
  const [category, setCategory] = useState("");
  const toast = useToast();
  const [failure, setFailure] = useState<string | null>(null);

  useEffect(() => { if (version) reload(); }, [version]);  // eslint-disable-line react-hooks/exhaustive-deps

  async function save<T>(request: () => Promise<T>, success: (result: T) => string) {
    setFailure(null);
    try {
      toast(success(await request()));
      reload();
      return true;
    } catch (err) {
      setFailure(err instanceof ApiError ? err.message : "Could not save; please try again");
      return false;
    }
  }

  async function addSupplier(event: FormEvent) {
    event.preventDefault();
    const errors = validateSupplier(supplier);
    setSupplierErrors(errors);
    if (Object.keys(errors).length) return;
    const body = { code: supplier.code.trim(), name: supplier.name.trim(), lead_time_days: Number(supplier.lead_time_days),
      contact_email: supplier.contact_email.trim() || null };
    if (await save(() => api.post<Supplier>("/suppliers", body), (s) => `Supplier ${s.code} added.`)) setSupplier(EMPTY_SUPPLIER);
  }

  async function addCategory(event: FormEvent) {
    event.preventDefault();
    if (!category.trim()) return setFailure("Enter a category name");
    if (await save(() => api.post<Category>("/categories", { name: category.trim() }), (c) => `Category ${c.name} added.`)) setCategory("");
  }

  const field = (key: keyof SupplierValues, label: string, extra = {}) => (
    <TextField id={`supplier-${key}`} label={label} value={supplier[key]} error={supplierErrors[key]}
               onChange={(e) => setSupplier({ ...supplier, [key]: e.target.value })} {...extra} />
  );

  if (error) return <ErrorMessage message={error} onRetry={reload} />;
  if (loading && !data) return <Skeleton variant="text" />;
  if (!data) return null;
  return (
    <div className="space-y-6">
      {failure && <ErrorMessage message={failure} />}

      <section aria-labelledby="suppliers-heading" className="space-y-3">
        <h3 id="suppliers-heading" className="text-sm font-semibold text-slate-800">Suppliers ({data.suppliers.length})</h3>
        {data.suppliers.length === 0
          ? <EmptyState icon="clipboard" title="No suppliers yet">Add one below, or import the Suppliers sheet.</EmptyState>
          : (
            <div className="max-h-56 overflow-y-auto">
              <table className="min-w-full text-sm">
                <thead className="text-left text-xs uppercase tracking-wide text-slate-500">
                  <tr><th scope="col" className="py-1 pr-3 font-medium">Code</th><th scope="col" className="py-1 pr-3 font-medium">Name</th>
                    <th scope="col" className="py-1 pr-3 text-right font-medium">Lead time</th><th scope="col" className="py-1 font-medium">Email</th></tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {data.suppliers.map((s) => (
                    <tr key={s.id}><td className="py-1 pr-3 font-mono text-xs">{s.code}</td><td className="py-1 pr-3">{s.name}</td>
                      <td className="py-1 pr-3 text-right tabular-nums">{s.lead_time_days} days</td><td className="py-1 text-slate-500">{s.contact_email ?? "—"}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        {canEdit && (
          <form onSubmit={addSupplier} noValidate aria-label="Add supplier"
                className="grid grid-cols-1 items-start gap-3 sm:grid-cols-[1fr_2fr_1fr_2fr_auto]">
            {field("code", "Code", { placeholder: "KTM-GRAIN" })}
            {field("name", "Name")}
            {field("lead_time_days", "Lead time (days)", { inputMode: "numeric" })}
            {field("contact_email", "Email (optional)", { type: "email" })}
            <Button type="submit" className="sm:mt-6">Add supplier</Button>
          </form>
        )}
      </section>

      <section aria-labelledby="categories-heading" className="space-y-3">
        <h3 id="categories-heading" className="text-sm font-semibold text-slate-800">Categories ({data.categories.length})</h3>
        {data.categories.length === 0
          ? <EmptyState icon="box" title="No categories yet">Add one below; importing products also creates them.</EmptyState>
          : (
            <ul className="flex flex-wrap gap-2">
              {data.categories.map((c) => (
                <li key={c.id} className="rounded-full bg-slate-100 px-3 py-1 text-sm text-slate-700" title={c.code}>{c.name}</li>
              ))}
            </ul>
          )}
        {canEdit && (
          <form onSubmit={addCategory} noValidate aria-label="Add category" className="flex items-end gap-3">
            <div className="w-64">
              <TextField id="category-name" label="New category" value={category} placeholder="Cold drinks"
                         onChange={(e) => setCategory(e.target.value)} />
            </div>
            <Button type="submit">Add category</Button>
          </form>
        )}
      </section>
    </div>
  );
}
