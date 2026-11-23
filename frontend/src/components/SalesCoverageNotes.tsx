import { Link } from "react-router-dom";

import { api } from "../api/client";
import type { SalesCoverage } from "../api/types";
import { useApi } from "../hooks/useApi";
import { fmtDate, fmtInt } from "../lib/format";
import { t } from "../lib/i18n";
import { Notice } from "./ui";

/** Fewer missing days than this are normal (a holiday, a sick day) and not worth a warning. */
export const MISSING_DAYS_WARNING = 3;

function useCoverage(deps: unknown[] = []) {
  return useApi((signal) => api.get<SalesCoverage>("/sales/coverage", undefined, signal), deps).data;
}

/** On the Forecasting and Reorder pages: many recent days with no sales recorded make the forecasts less reliable. */
export function MissingDaysNote({ className = "" }: { className?: string }) {
  const coverage = useCoverage();
  const missing = coverage?.missing_days ?? [];
  if (missing.length < MISSING_DAYS_WARNING) return null;
  return (
    <Notice tone="warning" className={className}>
      {t("No sales are recorded for {n} of the last 28 days (between {from} and {to}). Forecasts skip those days, so they and the order suggestions are less reliable.",
         { n: fmtInt(missing.length), from: fmtDate(missing[0]), to: fmtDate(missing[missing.length - 1]) })}{" "}
      <Link to="/sales" className="font-medium underline">{t("Record the missing days")}</Link>
    </Notice>
  );
}

/** On the Overview and Record sales pages: recent days where some products that usually sell have no entry. */
export function PartialDaysNote({ className = "", onPickDay, reloadKey }:
  { className?: string; onPickDay?: (day: string) => void; reloadKey?: unknown }) {
  const coverage = useCoverage([reloadKey]);
  const partial = coverage?.partial_days ?? [];
  if (partial.length === 0) return null;
  return (
    <Notice tone="warning" className={className}>
      <p>
        {t("Some recent days are only partly entered. Products with no entry count as 0 sold on those days; if sales are missing, add them.")}
      </p>
      <ul className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1">
        {partial.map((p) => {
          const label = t("{date}: {n} of {total} products", {
            date: fmtDate(p.date), n: fmtInt(p.products_recorded), total: fmtInt(p.products_expected) });
          return (
            <li key={p.date}>
              {onPickDay
                ? <button type="button" className="font-medium underline" onClick={() => onPickDay(p.date)}>{label}</button>
                : <Link to="/sales" className="font-medium underline">{label}</Link>}
            </li>
          );
        })}
      </ul>
    </Notice>
  );
}
