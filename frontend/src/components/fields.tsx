/** Labelled form controls with error text linked for screen readers. */
import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from "react";

const CONTROL = "mt-1.5 w-full rounded-md border px-3 py-2 text-sm";

export function TextField({ label, error, hint, id, ...props }:
  InputHTMLAttributes<HTMLInputElement> & { label: string; error?: string; hint?: string; id: string }) {
  return (
    <div>
      <label htmlFor={id} className="block text-sm font-medium text-slate-700">{label}</label>
      <input id={id} aria-invalid={!!error} aria-describedby={error ? `${id}-error` : hint ? `${id}-hint` : undefined}
             className={`${CONTROL} ${error ? "border-red-400" : "border-slate-300"}`} {...props} />
      {error ? <p id={`${id}-error`} className="mt-1 text-xs text-red-700">{error}</p>
        : hint && <p id={`${id}-hint`} className="mt-1 text-xs text-slate-500">{hint}</p>}
    </div>
  );
}

export function SelectField({ label, error, id, children, ...props }:
  SelectHTMLAttributes<HTMLSelectElement> & { label: string; error?: string; id: string; children: ReactNode }) {
  return (
    <div>
      <label htmlFor={id} className="block text-sm font-medium text-slate-700">{label}</label>
      <select id={id} aria-invalid={!!error} aria-describedby={error ? `${id}-error` : undefined}
              className={`${CONTROL} bg-white ${error ? "border-red-400" : "border-slate-300"}`} {...props}>
        {children}
      </select>
      {error && <p id={`${id}-error`} className="mt-1 text-xs text-red-700">{error}</p>}
    </div>
  );
}

/** Compact select used in filter bars (label hidden visually but read by screen readers). */
export function FilterSelect({ label, value, onChange, children }:
  { label: string; value: string; onChange: (value: string) => void; children: ReactNode }) {
  return (
    <label className="text-sm">
      <span className="sr-only">{label}</span>
      <select value={value} onChange={(e) => onChange(e.target.value)} aria-label={label}
              className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm">
        {children}
      </select>
    </label>
  );
}
