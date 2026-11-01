/** Small shared building blocks so every page looks and behaves the same. */
import type { ButtonHTMLAttributes, ReactNode } from "react";

import { useIsDemoShop } from "../auth/AuthContext";
import { Icon } from "./Icons";

type Variant = "primary" | "secondary" | "danger" | "ghost";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-brand-600 text-white shadow-sm hover:bg-brand-700 active:bg-brand-800 disabled:bg-brand-600/50",
  secondary: "bg-white text-slate-700 shadow-sm ring-1 ring-inset ring-slate-300 hover:bg-slate-50 hover:text-slate-900 disabled:bg-slate-50 disabled:text-slate-400",
  danger: "bg-red-600 text-white shadow-sm hover:bg-red-700 disabled:bg-red-600/50",
  ghost: "text-slate-600 hover:bg-slate-100 hover:text-slate-900 disabled:text-slate-400",
};

export function Button({ variant = "primary", className = "", ...props }:
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return (
    <button
      type="button"
      className={`inline-flex min-h-[36px] items-center justify-center gap-2 whitespace-nowrap rounded-md px-3.5 py-2
        text-sm font-medium transition-colors disabled:cursor-not-allowed ${VARIANTS[variant]} ${className}`}
      {...props}
    />
  );
}

export function Card({ title, actions, children, className = "" }:
  { title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`rounded-xl border border-slate-200 bg-white shadow-card ${className}`}>
      {(title || actions) && (
        <header className="flex min-h-[56px] flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-5 py-3">
          <h2 className="text-[15px] font-semibold text-slate-900">{title}</h2>
          {actions}
        </header>
      )}
      <div className="p-5">{children}</div>
    </section>
  );
}

export function Spinner({ label = "Loading…" }: { label?: string }) {
  return (
    <div role="status" className="flex items-center gap-3 rounded-lg bg-white px-4 py-3 text-sm text-slate-600 ring-1 ring-slate-200">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-slate-200 border-t-brand-600" aria-hidden />
      {label}
    </div>
  );
}

export function ErrorMessage({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex items-start justify-between gap-4 rounded-lg border border-red-200 bg-red-50 p-3.5 text-sm text-red-800">
      <span className="flex items-start gap-2.5">
        <Icon.alert className="mt-0.5 h-4 w-4 shrink-0 text-red-500" />
        <span>{message}</span>
      </span>
      {onRetry && <Button variant="secondary" onClick={onRetry}>Try again</Button>}
    </div>
  );
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center rounded-lg border border-dashed border-slate-300 bg-slate-50/50 px-6 py-10 text-center">
      <span className="mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-white text-slate-400 ring-1 ring-slate-200">
        <Icon.inbox className="h-5 w-5" />
      </span>
      <p className="font-medium text-slate-800">{title}</p>
      {children && <div className="mt-1 max-w-md text-sm text-slate-500">{children}</div>}
    </div>
  );
}

const BADGE_TONES = {
  gray: "bg-slate-100 text-slate-700 ring-slate-200",
  blue: "bg-blue-50 text-blue-700 ring-blue-200",
  green: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  amber: "bg-amber-50 text-amber-800 ring-amber-200",
  red: "bg-red-50 text-red-700 ring-red-200",
  purple: "bg-violet-50 text-violet-700 ring-violet-200",
} as const;

const BADGE_DOTS = {
  gray: "bg-slate-400", blue: "bg-blue-500", green: "bg-emerald-500",
  amber: "bg-amber-500", red: "bg-red-500", purple: "bg-violet-500",
} as const;

export function Badge({ tone = "gray", children }: { tone?: keyof typeof BADGE_TONES; children: ReactNode }) {
  return (
    <span className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${BADGE_TONES[tone]}`}>
      <span aria-hidden className={`h-1.5 w-1.5 rounded-full ${BADGE_DOTS[tone]}`} />
      {children}
    </span>
  );
}

/**
 * Marks a number or section that depends on made-up inputs (stock, costs, lead times). Shown only in a demo shop:
 * a real shop's figures come from its own records.
 */
export function SimulatedTag() {
  if (!useIsDemoShop()) return null;
  return (
    <span title="Based on simulated stock, cost or lead-time data, not real retailer records">
      <Badge tone="purple">Simulated</Badge>
    </span>
  );
}

export function PageHeader({ title, description, actions }:
  { title: string; description?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        <h1 className="text-2xl font-semibold tracking-tight text-slate-900">{title}</h1>
        {description && <p className="mt-1.5 max-w-3xl text-sm leading-relaxed text-slate-500">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}
