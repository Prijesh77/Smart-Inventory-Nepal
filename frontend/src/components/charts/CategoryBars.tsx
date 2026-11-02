import { Bar, BarChart, Cell, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { AXIS, TOOLTIP } from "../../lib/colors";
import { fmtInt } from "../../lib/format";

export interface CategoryBar {
  key: string;
  label: string;
  value: number;
  color: string;
}

/**
 * Horizontal bars for counts per state (stock status, risk category).
 * Each bar is labelled with its name and value, so colour is never the only cue.
 */
export function CategoryBars({ data, ariaLabel }: { data: CategoryBar[]; ariaLabel: string }) {
  const height = Math.max(120, data.length * 44);
  return (
    <div role="img" aria-label={`${ariaLabel}: ${data.map((d) => `${d.label} ${d.value}`).join(", ")}`}>
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={data} layout="vertical" margin={{ top: 4, right: 40, bottom: 4, left: 8 }}>
          <XAxis type="number" hide />
          <YAxis type="category" dataKey="label" width={150} tick={{ fill: AXIS, fontSize: 12 }}
                 axisLine={false} tickLine={false} />
          <Tooltip contentStyle={TOOLTIP.contentStyle} labelStyle={TOOLTIP.labelStyle} cursor={{ fill: "#F1F5F9" }} formatter={(v) => [fmtInt(Number(v)), "Products"]} />
          <Bar dataKey="value" radius={[0, 4, 4, 0]} barSize={20} isAnimationActive={false}>
            {data.map((d) => <Cell key={d.key} fill={d.color} />)}
            <LabelList dataKey="value" position="right" fill="#334155" fontSize={12}
                       formatter={(v: unknown) => fmtInt(Number(v))} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
