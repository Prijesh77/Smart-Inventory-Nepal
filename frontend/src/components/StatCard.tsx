import type { ReactNode } from "react";

import { Icon, type IconName } from "./Icons";
import { SimulatedTag } from "./ui";

const TONES = {
  default: { value: "text-slate-900", icon: "bg-brand-50 text-brand-600" },
  warning: { value: "text-amber-700", icon: "bg-amber-50 text-amber-600" },
  critical: { value: "text-red-700", icon: "bg-red-50 text-red-600" },
} as const;

export function StatCard({ label, value, detail, simulated = false, tone = "default", icon }: {
  label: string;
  value: ReactNode;
  detail?: ReactNode;
  simulated?: boolean;
  tone?: keyof typeof TONES;
  icon?: IconName;
}) {
  const ItemIcon = icon ? Icon[icon] : null;
  return (
    <div role="group" aria-label={label} className="flex flex-col rounded-xl border border-slate-200 bg-white p-5 shadow-card">
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2.5">
          {ItemIcon && (
            <span className={`flex h-8 w-8 items-center justify-center rounded-lg ${TONES[tone].icon}`}>
              <ItemIcon className="h-4 w-4" />
            </span>
          )}
          <p className="text-sm font-medium text-slate-600">{label}</p>
        </div>
        {simulated && <SimulatedTag />}
      </div>
      <p data-testid="stat-value" className={`mt-3 text-[28px] font-semibold leading-none tracking-tight tabular-nums ${TONES[tone].value}`}>{value}</p>
      {detail && <p className="mt-2 text-xs leading-relaxed text-slate-500">{detail}</p>}
    </div>
  );
}
