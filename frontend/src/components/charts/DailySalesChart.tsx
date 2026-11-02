import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { SalesHistory } from "../../api/types";
import { AXIS, GRID, SERIES } from "../../lib/colors";
import { fmtDate, fmtInt, fmtMoney, fmtShortDate } from "../../lib/format";

type Point = SalesHistory["points"][number];

function TooltipBody({ active, payload }: { active?: boolean; payload?: { payload: Point }[] }) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  return (
    <div className="rounded-[10px] border border-slate-200 bg-white px-3 py-2 text-xs shadow-lg shadow-slate-900/5">
      <p className="font-medium text-slate-800">{fmtDate(p.sales_date)}</p>
      <p>{p.is_available ? `${fmtInt(p.units)} units sold` : "Not on sale / store closed"}</p>
      {p.unit_price && <p className="text-slate-500">Price {fmtMoney(p.unit_price)}</p>}
    </div>
  );
}

/** Daily units for one product. Unavailable days are drawn grey so they are not mistaken for zero demand. */
export function DailySalesChart({ history }: { history: SalesHistory }) {
  return (
    <div role="img" aria-label={`Daily units sold for ${history.sku} from ${fmtDate(history.start)} to ${fmtDate(history.end)}: ${fmtInt(history.total_units)} units`}>
      <ResponsiveContainer width="100%" height={240}>
        <BarChart data={history.points} margin={{ top: 8, right: 8, bottom: 0, left: 0 }} barCategoryGap={1}>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis dataKey="sales_date" tickFormatter={fmtShortDate} minTickGap={40} tick={{ fill: AXIS, fontSize: 12 }}
                 tickLine={false} axisLine={{ stroke: GRID }} />
          <YAxis allowDecimals={false} width={36} tick={{ fill: AXIS, fontSize: 12 }} axisLine={false} tickLine={false} />
          <Tooltip content={<TooltipBody />} cursor={{ fill: "#F1F5F9" }} />
          <Bar dataKey="units" radius={[2, 2, 0, 0]} isAnimationActive={false}>
            {history.points.map((p) => <Cell key={p.sales_date} fill={p.is_available ? SERIES.blue : SERIES.gray} />)}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
