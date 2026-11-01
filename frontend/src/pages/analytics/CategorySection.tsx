import { useMemo, useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { api } from "../../api/client";
import type { CategoryPerformance, WeeklyPoint } from "../../api/types";
import { FilterSelect } from "../../components/fields";
import { EmptyState, ErrorMessage, SimulatedTag, Spinner } from "../../components/ui";
import { useApi } from "../../hooks/useApi";
import { AXIS, GRID, SERIES } from "../../lib/colors";
import { fmtDate, fmtDecimal, fmtInt, fmtMoney, fmtShortDate } from "../../lib/format";

/** One fixed colour per category, so a category keeps its colour on every chart. */
export const CATEGORY_COLOR: Record<string, string> = { FOODS: SERIES.blue, HOBBIES: SERIES.orange, HOUSEHOLD: SERIES.green };

export function CategoryTable() {
  const [days, setDays] = useState("28");
  const { data, error, loading, reload } = useApi(
    (signal) => api.get<CategoryPerformance[]>("/analytics/categories", { days }, signal), [days]);
  return (
    <>
      <div className="mb-3 flex items-center justify-between gap-3">
        <FilterSelect label="Sales period" value={days} onChange={setDays}>
          <option value="28">Last 28 days</option>
          <option value="91">Last 13 weeks</option>
          <option value="364">Last 52 weeks</option>
        </FilterSelect>
        <span className="flex items-center gap-2 text-xs text-slate-500">Stock and value <SimulatedTag /></span>
      </div>
      {error && <ErrorMessage message={error} onRetry={reload} />}
      {loading && !data && <Spinner />}
      {data && (
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead className="text-left text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th scope="col" className="py-2 pr-4 font-medium">Category</th>
                <th scope="col" className="py-2 pr-4 text-right font-medium">Products</th>
                <th scope="col" className="py-2 pr-4 text-right font-medium">Units sold</th>
                <th scope="col" className="py-2 pr-4 text-right font-medium">Revenue</th>
                <th scope="col" className="py-2 pr-4 text-right font-medium">Units / day</th>
                <th scope="col" className="py-2 pr-4 text-right font-medium">On hand</th>
                <th scope="col" className="py-2 pr-4 text-right font-medium">Stock value</th>
                <th scope="col" className="py-2 text-right font-medium">Days of cover</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {data.map((c) => (
                <tr key={c.category}>
                  <th scope="row" className="py-2 pr-4 text-left font-medium">
                    <span className="mr-2 inline-block h-2.5 w-2.5 rounded-full" style={{ backgroundColor: CATEGORY_COLOR[c.category] ?? SERIES.gray }} aria-hidden />
                    {c.name}
                  </th>
                  <td className="py-2 pr-4 text-right tabular-nums">{fmtInt(c.products)}</td>
                  <td className="py-2 pr-4 text-right tabular-nums">{fmtInt(c.units_sold)}</td>
                  <td className="py-2 pr-4 text-right tabular-nums">{fmtMoney(c.revenue)}</td>
                  <td className="py-2 pr-4 text-right tabular-nums">{fmtDecimal(c.avg_daily_units)}</td>
                  <td className="py-2 pr-4 text-right tabular-nums">{fmtInt(c.units_on_hand)}</td>
                  <td className="py-2 pr-4 text-right tabular-nums">{fmtMoney(c.inventory_value)}</td>
                  <td className="py-2 text-right tabular-nums">{c.days_of_cover === null ? "—" : `${fmtDecimal(c.days_of_cover)} d`}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

/** Turn [{week, category, units}] into one row per week with a column per category. */
export function pivotWeekly(points: WeeklyPoint[]): { rows: Record<string, number | string>[]; categories: string[] } {
  const categories = [...new Set(points.map((p) => p.category))].sort();
  const byWeek = new Map<string, Record<string, number | string>>();
  points.forEach((p) => {
    const row = byWeek.get(p.week_start) ?? { week_start: p.week_start };
    row[p.category] = p.units;
    byWeek.set(p.week_start, row);
  });
  return { rows: [...byWeek.values()].sort((a, b) => String(a.week_start).localeCompare(String(b.week_start))), categories };
}

export function WeeklyTrend() {
  const [weeks, setWeeks] = useState("52");
  const { data, error, loading, reload } = useApi(
    (signal) => api.get<WeeklyPoint[]>("/analytics/weekly-trend", { weeks }, signal), [weeks]);
  // The newest week is usually incomplete (data ends mid-week); leave it out so it does not look like a drop.
  const { rows, categories } = useMemo(() => {
    const pivot = pivotWeekly(data ?? []);
    return { ...pivot, rows: pivot.rows.slice(0, -1) };
  }, [data]);

  return (
    <>
      <div className="mb-3">
        <FilterSelect label="Weeks shown" value={weeks} onChange={setWeeks}>
          <option value="26">Last 26 weeks</option>
          <option value="52">Last 52 weeks</option>
          <option value="104">Last 2 years</option>
        </FilterSelect>
      </div>
      {error && <ErrorMessage message={error} onRetry={reload} />}
      {loading && !data && <Spinner />}
      {data && !rows.length && <EmptyState title="No sales in this period" />}
      {rows.length > 0 && (
        <div role="img" aria-label={`Units sold per week by category (${categories.join(", ")}), ${rows.length} weeks`}>
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={rows} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
              <CartesianGrid stroke={GRID} vertical={false} />
              <XAxis dataKey="week_start" tickFormatter={fmtShortDate} minTickGap={40} tick={{ fill: AXIS, fontSize: 12 }}
                     tickLine={false} axisLine={{ stroke: GRID }} />
              <YAxis width={48} tick={{ fill: AXIS, fontSize: 12 }} axisLine={false} tickLine={false} tickFormatter={(v) => fmtInt(v)} />
              <Tooltip labelFormatter={(d) => `Week of ${fmtDate(String(d))}`} formatter={(v, n) => [fmtInt(Number(v)), n]} />
              <Legend verticalAlign="top" align="right" height={28} wrapperStyle={{ fontSize: 12 }} />
              {categories.map((c) => (
                <Line key={c} type="monotone" dataKey={c} name={c.charAt(0) + c.slice(1).toLowerCase()}
                      stroke={CATEGORY_COLOR[c] ?? SERIES.gray} strokeWidth={2} dot={false} isAnimationActive={false} />
              ))}
            </LineChart>
          </ResponsiveContainer>
          <p className="mt-1 text-xs text-slate-500">Real M5 sales for the sampled products. The last, incomplete week is not shown.</p>
        </div>
      )}
    </>
  );
}
