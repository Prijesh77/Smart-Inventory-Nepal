import { useState, type FormEvent } from "react";

import { api, ApiError } from "../../api/client";
import type { Category, Product, ProductInput, Supplier } from "../../api/types";
import { SelectField, TextField } from "../../components/fields";
import { Button, ErrorMessage } from "../../components/ui";

interface FormValues {
  sku: string;
  name: string;
  category_code: string;
  department: string;
  supplier_id: string;
  unit_price: string;
  unit_cost: string;
  lead_time_days: string;
  min_order_qty: string;
  pack_size: string;
  is_active: boolean;
}

type Errors = Partial<Record<keyof FormValues, string>>;

const MONEY = /^\d+(\.\d{1,2})?$/;
const SKU = /^[A-Za-z0-9_-]+$/;
const WHOLE = /^\d+$/;

/** The same rules the API enforces, checked first so the user sees mistakes before saving. */
export function validate(v: FormValues, isNew: boolean): Errors {
  const e: Errors = {};
  if (isNew) {
    if (!v.sku.trim()) e.sku = "SKU is required";
    else if (!SKU.test(v.sku.trim())) e.sku = "Use letters, digits, '_' or '-' only";
    else if (v.sku.trim().length > 50) e.sku = "At most 50 characters";
  }
  if (!v.name.trim()) e.name = "Name is required";
  if (!v.category_code) e.category_code = "Choose a category";
  if (!MONEY.test(v.unit_price.trim())) e.unit_price = "Enter a price in rupees like 120 or 45.50 (0 or more, up to 2 decimals)";
  if (v.unit_cost.trim() && !MONEY.test(v.unit_cost.trim())) e.unit_cost = "Enter a cost in rupees like 98.50, or leave empty";
  if (v.lead_time_days.trim() && (!WHOLE.test(v.lead_time_days) || +v.lead_time_days < 1 || +v.lead_time_days > 365))
    e.lead_time_days = "Whole days from 1 to 365, or leave empty to use the supplier's";
  if (!WHOLE.test(v.min_order_qty) || +v.min_order_qty < 1) e.min_order_qty = "Whole number, at least 1";
  if (!WHOLE.test(v.pack_size) || +v.pack_size < 1) e.pack_size = "Whole number, at least 1";
  return e;
}

export function toInput(v: FormValues, isNew: boolean): ProductInput {
  return {
    ...(isNew ? { sku: v.sku.trim() } : { is_active: v.is_active }),
    name: v.name.trim(),
    category_code: v.category_code,
    department: v.department.trim() || null,
    supplier_id: v.supplier_id ? Number(v.supplier_id) : null,
    unit_price: v.unit_price.trim(),
    unit_cost: v.unit_cost.trim() || null,
    lead_time_days: v.lead_time_days.trim() ? Number(v.lead_time_days) : null,
    min_order_qty: Number(v.min_order_qty),
    pack_size: Number(v.pack_size),
  };
}

function initialValues(p?: Product): FormValues {
  return {
    sku: p?.sku ?? "", name: p?.name ?? "", category_code: p?.category.code ?? "", department: p?.department ?? "",
    supplier_id: p?.supplier ? String(p.supplier.id) : "", unit_price: String(p?.unit_price ?? ""),
    unit_cost: String(p?.unit_cost ?? ""), lead_time_days: p?.lead_time_days ? String(p.lead_time_days) : "",
    min_order_qty: String(p?.min_order_qty ?? 1), pack_size: String(p?.pack_size ?? 1), is_active: p?.is_active ?? true,
  };
}

export function ProductForm({ product, categories, suppliers, onSaved, onCancel }: {
  product?: Product;
  categories: Category[];
  suppliers: Supplier[];
  onSaved: (product: Product) => void;
  onCancel: () => void;
}) {
  const isNew = !product;
  const [values, setValues] = useState<FormValues>(() => initialValues(product));
  const [errors, setErrors] = useState<Errors>({});
  const [serverError, setServerError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const set = (field: keyof FormValues) => (e: { target: { value: string } }) =>
    setValues((v) => ({ ...v, [field]: e.target.value }));

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const found = validate(values, isNew);
    setErrors(found);
    setServerError(null);
    if (Object.keys(found).length) return;
    setSaving(true);
    try {
      const body = toInput(values, isNew);
      const saved = isNew ? await api.post<Product>("/products", body) : await api.patch<Product>(`/products/${product.id}`, body);
      onSaved(saved);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) setErrors({ sku: err.message });
      else setServerError(err instanceof ApiError ? err.message : "Could not save the product");
    } finally {
      setSaving(false);
    }
  }

  const supplier = suppliers.find((s) => String(s.id) === values.supplier_id);

  return (
    <form onSubmit={onSubmit} noValidate className="space-y-4">
      {serverError && <ErrorMessage message={serverError} />}
      {isNew && (categories.length === 0 || suppliers.length === 0) && (
        <p role="note" className="rounded-md bg-amber-50 p-3 text-sm text-amber-900">
          {categories.length === 0 ? "This shop has no categories yet. " : "This shop has no suppliers yet. "}
          Add them in <strong>Settings &amp; import → Suppliers and categories</strong>, or import many products at once
          from Excel there.
        </p>
      )}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <TextField id="sku" label="SKU" value={values.sku} onChange={set("sku")} error={errors.sku}
                   disabled={!isNew} hint={isNew ? "Saved in capitals, e.g. RICE-BASMATI-1KG" : "The SKU cannot change after creation"} />
        <TextField id="name" label="Name" value={values.name} onChange={set("name")} error={errors.name} />
        <SelectField id="category" label="Category" value={values.category_code} onChange={set("category_code")}
                     error={errors.category_code}>
          <option value="">Choose…</option>
          {categories.map((c) => <option key={c.id} value={c.code}>{c.name}</option>)}
        </SelectField>
        <TextField id="department" label="Department (optional)" value={values.department} onChange={set("department")} />
        <SelectField id="supplier" label="Supplier" value={values.supplier_id} onChange={set("supplier_id")}>
          <option value="">No supplier</option>
          {suppliers.map((s) => <option key={s.id} value={s.id}>{s.name} ({s.lead_time_days}-day lead time)</option>)}
        </SelectField>
        <TextField id="lead_time" label="Lead time override (days)" inputMode="numeric" value={values.lead_time_days}
                   onChange={set("lead_time_days")} error={errors.lead_time_days}
                   hint={supplier ? `Empty = supplier's ${supplier.lead_time_days} days` : "Empty = supplier's lead time"} />
        <TextField id="price" label="Unit price (Rs)" inputMode="decimal" value={values.unit_price}
                   onChange={set("unit_price")} error={errors.unit_price} />
        <TextField id="cost" label="Unit cost (Rs, optional)" inputMode="decimal" value={values.unit_cost}
                   onChange={set("unit_cost")} error={errors.unit_cost} hint="Needed for order-cost estimates" />
        <TextField id="moq" label="Minimum order quantity" inputMode="numeric" value={values.min_order_qty}
                   onChange={set("min_order_qty")} error={errors.min_order_qty} />
        <TextField id="pack" label="Pack size" inputMode="numeric" value={values.pack_size}
                   onChange={set("pack_size")} error={errors.pack_size} hint="Orders are rounded up to whole packs" />
      </div>
      {!isNew && (
        <label className="flex items-center gap-2 text-sm text-slate-700">
          <input type="checkbox" checked={values.is_active}
                 onChange={(e) => setValues((v) => ({ ...v, is_active: e.target.checked }))} />
          Active (inactive products are left out of forecasts and recommendations)
        </label>
      )}
      <div className="flex justify-end gap-2 border-t border-slate-100 pt-4">
        <Button variant="secondary" onClick={onCancel}>Cancel</Button>
        <Button type="submit" disabled={saving}>{saving ? "Saving…" : isNew ? "Create product" : "Save changes"}</Button>
      </div>
    </form>
  );
}
