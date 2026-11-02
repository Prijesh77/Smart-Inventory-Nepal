/** Small shared building blocks so every page looks and behaves the same. */
import type { ButtonHTMLAttributes, ReactNode } from "react";

import { useIsDemoShop } from "../auth/AuthContext";
import { Icon, type IconName } from "./Icons";

type Variant = "primary" | "secondary" | "danger" | "ghost";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-brand-600 text-white shadow-sm shadow-brand-600/20 hover:bg-brand-700 hover:shadow-md hover:shadow-brand-600/25 active:bg-brand-800 disabled:bg-brand-600/50 disabled:shadow-none",
  secondary: "bg-white text-slate-700 shadow-sm ring-1 ring-inset ring-slate-300 hover:bg-slate-50 hover:text-slate-900 hover:ring-slate-400 disabled:bg-slate-50 disabled:text-slate-400",
  danger: "bg-red-600 text-white shadow-sm shadow-red-600/20 hover:bg-red-700 disabled:bg-red-600/50",
  ghost: "text-slate-600 hover:bg-slate-100 hover:text-slate-900 disabled:text-slate-400",
};

export function Button({ variant = "primary", className = "", ...props }:
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return (
    <button
      type="button"
      className={`inline-flex min-h-[36px] items-center justify-center gap-2 whitespace-nowrap rounded-lg px-3.5 py-2
        text-sm font-medium transition-all duration-150 active:scale-[0.98] disabled:cursor-not-allowed disabled:active:scale-100
        ${VARIANTS[variant]} ${className}`}
      {...props}
    />
  );
}

export function Card({ title, subtitle, actions, children, className = "" }:
  { title?: ReactNode; subtitle?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`rounded-xl border border-slate-200/80 bg-white shadow-card ${className}`}>
      {(title || actions) && (
        <header className="flex min-h-[56px] flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-5 py-3">
          <div className="min-w-0">
            <h2 className="text-[15px] font-semibold tracking-tight text-slate-900">{title}</h2>
            {subtitle && <p className="mt-0.5 text-xs text-slate-500">{subtitle}</p>}
          </div>
          {actions}
        </header>
      )}
      <div className="p-5">{children}</div>
    </section>
  );
}

/** A small "working on it" indicator next to an action (training, importing, checking a file). */
export function Spinner({ label = "Loading…" }: { label?: string }) {
  return (
    <div role="status" className="inline-flex items-center gap-2.5 rounded-lg bg-brand-50/60 px-3 py-2 text-sm text-brand-800 ring-1 ring-inset ring-brand-100">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-brand-200 border-t-brand-600" aria-hidden />
      {label}
    </div>
  );
}

/**
 * Grey placeholder bars while a list or card loads, shaped like what is coming, so the page does not jump.
 * Screen readers hear the label ("Loading products…").
 */
export function Skeleton({ label = "Loading…", rows = 4, variant = "table" }:
  { label?: string; rows?: number; variant?: "table" | "cards" | "text" }) {
  const bar = "animate-pulse rounded-md bg-slate-200/70";
  return (
    <div role="status" aria-live="polite" className="w-full">
      <span className="sr-only">{label}</span>
      {variant === "cards" ? (
        <div aria-hidden className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: rows }, (_, i) => (
            <div key={i} className="rounded-xl border border-slate-200/80 bg-white p-5 shadow-card">
              <div className={`${bar} h-4 w-1/2`} />
              <div className={`${bar} mt-4 h-7 w-1/3`} />
              <div className={`${bar} mt-3 h-3 w-2/3`} />
            </div>
          ))}
        </div>
      ) : (
        <div aria-hidden className="space-y-3">
          {variant === "table" && <div className={`${bar} h-3 w-full bg-slate-100`} />}
          {Array.from({ length: rows }, (_, i) => (
            <div key={i} className="flex items-center gap-4">
              <div className={`${bar} h-4`} style={{ width: `${30 + ((i * 37) % 45)}%` }} />
              {variant === "table" && <div className={`${bar} ml-auto h-4 w-16`} />}
              {variant === "table" && <div className={`${bar} h-4 w-12`} />}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

const NOTICE_TONES = {
  success: { box: "border-emerald-200 bg-emerald-50 text-emerald-900", icon: "text-emerald-600", name: "check" },
  info: { box: "border-brand-200 bg-brand-50 text-brand-900", icon: "text-brand-600", name: "info" },
  warning: { box: "border-amber-200 bg-amber-50 text-amber-900", icon: "text-amber-600", name: "alert" },
} as const;

/** A message that stays on the page (e.g. one with a link to follow). Short confirmations use toasts instead. */
export function Notice({ tone = "success", children, className = "" }:
  { tone?: keyof typeof NOTICE_TONES; children: ReactNode; className?: string }) {
  const t = NOTICE_TONES[tone];
  const NoticeIcon = Icon[t.name];
  return (
    <div role="status" className={`flex items-start gap-2.5 rounded-lg border p-3.5 text-sm ${t.box} ${className}`}>
      <NoticeIcon className={`mt-0.5 h-4 w-4 shrink-0 ${t.icon}`} />
      <div className="min-w-0">{children}</div>
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

export function EmptyState({ title, children, icon = "inbox", action }:
  { title: string; children?: ReactNode; icon?: IconName; action?: ReactNode }) {
  const EmptyIcon = Icon[icon];
  return (
    <div className="flex flex-col items-center rounded-xl border border-dashed border-slate-300 bg-gradient-to-b from-slate-50/80 to-white px-6 py-12 text-center">
      <span className="mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-brand-50 text-brand-500 ring-8 ring-brand-50/40">
        <EmptyIcon className="h-6 w-6" />
      </span>
      <p className="font-semibold text-slate-800">{title}</p>
      {children && <div className="mt-1.5 max-w-md text-sm leading-relaxed text-slate-500">{children}</div>}
      {action && <div className="mt-5">{action}</div>}
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
        <h1 className="text-[26px] font-semibold leading-tight tracking-tight text-slate-900">{title}</h1>
        {description && <p className="mt-2 max-w-3xl text-sm leading-relaxed text-slate-500">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}
