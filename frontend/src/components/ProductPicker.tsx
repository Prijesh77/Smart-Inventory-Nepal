import { useId, useState } from "react";

import { api } from "../api/client";
import type { Page, Product } from "../api/types";
import { useApi } from "../hooks/useApi";
import { useDebounce } from "../hooks/useDebounce";

/** Type to search products; pick one from the list (arrow keys + Enter, or click). */
export function ProductPicker({ label, selected, onSelect, supplierId }: {
  label: string;
  selected: { id: number; sku: string } | null;
  onSelect: (p: { id: number; sku: string; name: string; unit_cost: string | null }) => void;
  supplierId?: number;           // only offer this supplier's products
}) {
  const id = useId();
  const [text, setText] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const search = useDebounce(text, 250);
  const { data } = useApi(
    (signal) => search.trim()
      ? api.get<Page<Product>>("/products", { search, page_size: 8, supplier_id: supplierId, is_active: true }, signal)
      : Promise.resolve(null),
    [search, supplierId],
  );
  const options = data?.items ?? [];

  function choose(p: Product) {
    onSelect({ id: p.id, sku: p.sku, name: p.name, unit_cost: p.unit_cost });
    setText("");
    setOpen(false);
  }

  return (
    <div className="relative min-w-[16rem]">
      <label htmlFor={id} className="block text-sm font-medium text-slate-700">{label}</label>
      <input
        id={id} type="search" role="combobox" aria-expanded={open && options.length > 0} aria-controls={`${id}-list`}
        aria-autocomplete="list" autoComplete="off" value={text}
        placeholder={selected ? `${selected.sku} (type to change)` : "Type a SKU or name…"}
        onChange={(e) => { setText(e.target.value); setOpen(true); setActive(0); }}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(a + 1, options.length - 1)); }
          if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
          if (e.key === "Enter" && options[active]) { e.preventDefault(); choose(options[active]); }
          if (e.key === "Escape") setOpen(false);
        }}
        className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
      />
      {open && options.length > 0 && (
        <ul id={`${id}-list`} role="listbox" aria-label="Matching products"
            className="absolute z-20 mt-1 max-h-72 w-full overflow-y-auto rounded-md bg-white py-1 text-sm shadow-lg ring-1 ring-slate-200">
          {options.map((p, i) => (
            <li key={p.id} role="option" aria-selected={i === active}
                onMouseDown={(e) => { e.preventDefault(); choose(p); }}
                className={`cursor-pointer px-3 py-2 ${i === active ? "bg-brand-50 text-brand-700" : "hover:bg-slate-50"}`}>
              <span className="font-medium">{p.sku}</span> <span className="text-slate-500">{p.name}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
