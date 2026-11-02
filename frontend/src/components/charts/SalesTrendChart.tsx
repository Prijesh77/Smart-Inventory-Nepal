import { useId, useMemo } from "react";
import { Area, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { AXIS, GRID, SERIES, TOOLTIP } from "../../lib/colors";
import { fmtDate, fmtInt, fmtShortDate } from "../../lib/format";

interface Point {
  date: string;
  units: number;
}

/** Adds a trailing 7-day average so the weekly up-and-down pattern does not hide the trend. */
export function withRollingAverage(points: Point[], window = 7) {
  return points.map((p, i) => {
    const slice = points.slice(Math.max(0, i - window + 1), i + 1);
    const avg = slice.length === window ? slice.reduce((s, x) => s + x.units, 0) / window : null;
    return { ...p, avg };
  });
}

export function SalesTrendChart({ points }: { points: Point[] }) {
  const data = useMemo(() => withRollingAverage(points), [points]);
  const fillId = `sales-fill-${useId().replace(/:/g, "")}`;
  const total = points.reduce((s, p) => s + p.units, 0);
  return (
    <div role="img" aria-label={`Daily units sold for ${points.length} days, ${fmtInt(total)} units in total`}>
      <ResponsiveContainer width="100%" height={260}>
        <ComposedChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
          <defs>
            {/* The daily area fades towards the axis, so the 7-day average line stands out on top. */}
            <linearGradient id={fillId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={SERIES.sky} stopOpacity={0.35} />
              <stop offset="100%" stopColor={SERIES.sky} stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis dataKey="date" tickFormatter={fmtShortDate} minTickGap={40} tick={{ fill: AXIS, fontSize: 12 }}
                 axisLine={{ stroke: GRID }} tickLine={false} />
          <YAxis tick={{ fill: AXIS, fontSize: 12 }} axisLine={false} tickLine={false} width={48}
                 tickFormatter={(v) => fmtInt(v)} />
          <Tooltip {...TOOLTIP} labelFormatter={(d) => fmtDate(String(d))}
                   formatter={(v, name) => [v === null ? "—" : fmtInt(Number(v)), name]} />
          <Legend verticalAlign="top" align="right" height={28} iconType="plainline" wrapperStyle={{ fontSize: 12 }} />
          <Area type="monotone" dataKey="units" name="Units sold (daily)" stroke={SERIES.sky} fill={`url(#${fillId})`}
                fillOpacity={1} strokeWidth={1.5} isAnimationActive={false} />
          <Line type="monotone" dataKey="avg" name="7-day average" stroke={SERIES.blue} strokeWidth={2.5}
                dot={false} connectNulls={false} isAnimationActive={false} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
