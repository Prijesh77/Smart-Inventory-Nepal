import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { fmtPct } from "../lib/format";
import { Icon, type IconName } from "./Icons";
import { SimulatedTag } from "./ui";

const TONES = {
  default: { value: "text-slate-900", icon: "bg-brand-50 text-brand-600", accent: "bg-brand-500" },
  warning: { value: "text-amber-700", icon: "bg-amber-50 text-amber-600", accent: "bg-amber-500" },
  critical: { value: "text-red-700", icon: "bg-red-50 text-red-600", accent: "bg-red-500" },
} as const;

/**
 * One figure on the Overview. "primary" cards are the ones to act on: bigger, with a coloured accent bar and,
 * when `to` is given, the whole card links to the page where you act. "compact" cards are for context.
 */
export function StatCard({ label, value, detail, simulated = false, tone = "default", icon, to, size = "compact", trend }: {
  label: string;
  value: ReactNode;
  detail?: ReactNode;
  simulated?: boolean;
  tone?: keyof typeof TONES;
  icon?: IconName;
  to?: string;
  size?: "primary" | "compact";
  /** Change vs the previous period (0.13 = +13%), shown as an up/down chip. */
  trend?: number | null;
}) {
  const ItemIcon = icon ? Icon[icon] : null;
  const primary = size === "primary";
  const t = TONES[tone];
  const body = (
    <>
      {primary && <span aria-hidden className={`absolute inset-y-0 left-0 w-1 ${t.accent}`} />}
      <div className="flex items-start justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2.5">
          {ItemIcon && (
            <span className={`flex shrink-0 items-center justify-center rounded-lg ${primary ? "h-9 w-9" : "h-8 w-8"} ${t.icon}`}>
              <ItemIcon className="h-4 w-4" />
            </span>
          )}
          <p className="text-sm font-medium text-slate-600">{label}</p>
        </div>
        {simulated && <SimulatedTag />}
      </div>
      <div className="mt-3 flex items-baseline gap-2">
        <p data-testid="stat-value"
           className={`font-semibold leading-none tracking-tight tabular-nums ${primary ? "text-[34px]" : "text-[24px]"} ${t.value}`}>
          {value}
        </p>
        {trend !== undefined && trend !== null && <Trend change={trend} />}
      </div>
      {detail && <p className="mt-2 text-xs leading-relaxed text-slate-500">{detail}</p>}
      {to && (
        <p className="mt-auto flex items-center gap-1 pt-3 text-xs font-medium text-brand-600 group-hover:text-brand-700">
          {primary ? "Review" : "Open"}
          <Icon.arrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" />
        </p>
      )}
    </>
  );
  const box = `group relative flex h-full flex-col overflow-hidden rounded-xl border border-slate-200/80 bg-white shadow-card ${
    primary ? "p-5 pl-6" : "p-4"}`;
  return (
    <div role="group" aria-label={label} className="h-full">
      {to ? <Link to={to} className={`${box} lift`}>{body}</Link> : <div className={box}>{body}</div>}
    </div>
  );
}

function Trend({ change }: { change: number }) {
  const up = change > 0;
  const flat = Math.abs(change) < 0.005;
  const style = flat ? "bg-slate-100 text-slate-600" : up ? "bg-emerald-50 text-emerald-700" : "bg-red-50 text-red-700";
  const Arrow = up ? Icon.arrowUp : Icon.arrowDown;
  return (
    <span className={`inline-flex items-center gap-0.5 rounded-full px-1.5 py-0.5 text-[11px] font-semibold tabular-nums ${style}`}
          title="Compared with the previous 28 days">
      {!flat && <Arrow className="h-3 w-3" />}
      {fmtPct(change, true)}
    </span>
  );
}
