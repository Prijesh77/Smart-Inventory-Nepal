import { CartesianGrid, ComposedChart, Legend, Line, ReferenceArea, ReferenceLine, ResponsiveContainer, Tooltip,
  XAxis, YAxis } from "recharts";

import type { ProductForecast } from "../../api/types";
import { AXIS, GRID, SERIES, TOOLTIP } from "../../lib/colors";
import { fmtDate, fmtDecimal, fmtShortDate } from "../../lib/format";

export interface ForecastPoint {
  date: string;
  actual: number | null;          // actual sales BEFORE the forecast starts
  later: number | null;           // actual sales INSIDE the forecast window (back-dated runs only)
  forecast: number | null;        // predicted units
}

/**
 * One row per date. Actuals and predictions are kept in different fields, so they are
 * drawn as different lines and can never be confused. Unavailable days (not on sale,
 * store closed) are left empty rather than drawn as zero demand.
 */
export function mergeForecast(data: ProductForecast): ForecastPoint[] {
  const rows = new Map<string, ForecastPoint>();
  const row = (date: string) => {
    if (!rows.has(date)) rows.set(date, { date, actual: null, later: null, forecast: null });
    return rows.get(date)!;
  };
  data.history.forEach((d) => { row(d.date).actual = d.is_available ? d.units : null; });
  data.actual_in_window.forEach((d) => { row(d.date).later = d.is_available ? d.units : null; });
  data.forecast.forEach((d) => { row(d.date).forecast = d.predicted_units; });
  return [...rows.values()].sort((a, b) => a.date.localeCompare(b.date));
}

/** WAPE of a back-dated forecast against what actually sold (available days only). */
export function windowWape(data: ProductForecast): number | null {
  const actual = new Map(data.actual_in_window.filter((d) => d.is_available).map((d) => [d.date, d.units]));
  let error = 0;
  let total = 0;
  data.forecast.forEach((f) => {
    const a = actual.get(f.date);
    if (a === undefined) return;
    error += Math.abs(f.predicted_units - a);
    total += a;
  });
  return actual.size && total > 0 ? error / total : null;
}

export function ForecastChart({ data }: { data: ProductForecast }) {
  const points = mergeForecast(data);
  const origin = data.run.origin_date;
  const last = points.at(-1)?.date;
  return (
    <div role="img" aria-label={`${data.sku}: actual daily sales before ${fmtDate(origin)} and ${data.forecast.length}-day forecast from ${fmtDate(origin)}, ${fmtDecimal(data.total_forecast)} units predicted`}>
      <ResponsiveContainer width="100%" height={300}>
        <ComposedChart data={points} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
          <CartesianGrid stroke={GRID} vertical={false} />
          {last && <ReferenceArea x1={origin} x2={last} fill="#EEF6FF" fillOpacity={0.7} />}
          <XAxis dataKey="date" tickFormatter={fmtShortDate} minTickGap={36} tick={{ fill: AXIS, fontSize: 12 }}
                 tickLine={false} axisLine={{ stroke: GRID }} />
          <YAxis allowDecimals={false} width={36} tick={{ fill: AXIS, fontSize: 12 }} axisLine={false} tickLine={false} />
          <ReferenceLine x={origin} stroke="#475569" strokeDasharray="3 3"
                         label={{ value: "Forecast starts", position: "insideTopLeft", fill: "#475569", fontSize: 11 }} />
          <Tooltip {...TOOLTIP} labelFormatter={(d) => fmtDate(String(d))}
                   formatter={(v, name) => [v === null || v === undefined ? "—" : fmtDecimal(Number(v)), name]} />
          <Legend verticalAlign="top" align="right" height={28} wrapperStyle={{ fontSize: 12 }} />
          <Line type="linear" dataKey="actual" name="Actual sales" stroke={SERIES.blue} strokeWidth={2}
                dot={false} connectNulls={false} isAnimationActive={false} />
          {data.actual_in_window.length > 0 && (
            <Line type="linear" dataKey="later" name="Actual sales (in forecast window)" stroke={SERIES.green}
                  strokeWidth={2} dot={false} connectNulls={false} isAnimationActive={false} />
          )}
          <Line type="monotone" dataKey="forecast" name="Forecast" stroke={SERIES.orange} strokeWidth={2.5}
                strokeDasharray="6 4" dot={false} isAnimationActive={false} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
