import { api } from "../../api/client";
import { Badge, ErrorMessage, Spinner } from "../../components/ui";
import { useApi } from "../../hooks/useApi";
import { fmtDate } from "../../lib/format";

export interface FestivalEntry {
  key: string; name: string; nepali: string; bs_year: number; main_label: string; main: string; main_bs: string;
  start?: string; end?: string; check: boolean; note: string; sources: string[];
}
interface FestivalCalendarData { covers: { from: string; to: string }; festivals: FestivalEntry[] }

/** Read-only: the festival dates the forecasts and "Festival ahead" notes use, shared by every shop. */
export function FestivalCalendar() {
  const { data, error, loading, reload } = useApi((signal) => api.get<FestivalCalendarData>("/festivals", undefined, signal));
  if (error) return <ErrorMessage message={error} onRetry={reload} />;
  if (loading && !data) return <Spinner />;
  if (!data) return null;
  const toCheck = data.festivals.filter((f) => f.check);
  return (
    <div className="space-y-3 text-sm">
      <p className="text-slate-600">
        Forecasts learn how each shop&apos;s sales change around these festivals, and the Reorder page warns before
        them. Dates are known from {fmtDate(data.covers.from)} to {fmtDate(data.covers.to)}; outside that the forecast
        treats festivals as unknown. Dates come from public-holiday lists (sources below each one).
      </p>
      {toCheck.length > 0 && (
        <p role="note" className="rounded-md bg-amber-50 p-3 text-amber-900">
          {toCheck.length} date{toCheck.length > 1 ? "s" : ""} differ between sources and should be checked against the
          Ministry of Home Affairs holiday list: {toCheck.map((f) => `${f.name} ${f.bs_year}`).join(", ")}.
        </p>
      )}
      <div className="max-h-96 overflow-y-auto">
        <table className="min-w-full">
          <thead className="sticky top-0 bg-white text-left text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th scope="col" className="py-2 pr-3 font-medium">Festival</th>
              <th scope="col" className="py-2 pr-3 font-medium">Main day</th>
              <th scope="col" className="py-2 pr-3 font-medium">BS</th>
              <th scope="col" className="py-2 font-medium">Notes and sources</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {data.festivals.map((f) => (
              <tr key={`${f.key}-${f.bs_year}`}>
                <td className="py-2 pr-3">
                  <span className="font-medium text-slate-800">{f.name}</span> <span className="text-slate-500">{f.nepali}</span>
                  <p className="text-xs text-slate-500">{f.main_label}</p>
                </td>
                <td className="whitespace-nowrap py-2 pr-3 tabular-nums">{fmtDate(f.main)}</td>
                <td className="whitespace-nowrap py-2 pr-3 font-mono text-xs">{f.main_bs}</td>
                <td className="py-2 text-xs text-slate-500">
                  {f.check && <Badge tone="amber">Please check</Badge>} {f.note}
                  <details><summary className="cursor-pointer">{f.sources.length} source{f.sources.length > 1 ? "s" : ""}</summary>
                    <ul className="ml-4 list-disc">{f.sources.map((s) => <li key={s}>{s}</li>)}</ul>
                  </details>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
