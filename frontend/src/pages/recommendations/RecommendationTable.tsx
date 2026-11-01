import { Fragment, useState } from "react";
import { Link } from "react-router-dom";

import type { Recommendation, ReviewStatus } from "../../api/types";
import { Badge, Button } from "../../components/ui";
import { RISK_STYLE } from "../../lib/colors";
import { fmtDecimal, fmtInt, fmtMoney, fmtPct } from "../../lib/format";

const REVIEW_TONE = { pending: "gray", approved: "green", rejected: "red", ordered: "blue" } as const;
const REVIEW_LABEL: Record<ReviewStatus, string> = { pending: "To review", approved: "Approved", rejected: "Rejected", ordered: "On a draft order" };

export function RiskBadge({ risk }: { risk: Recommendation["risk_category"] }) {
  const style = RISK_STYLE[risk];
  return <Badge tone={style.tone}>{style.label}</Badge>;
}

export function RecommendationTable({ rows, canReview, busyId, onReview }: {
  rows: Recommendation[];
  canReview: boolean;
  busyId: number | null;
  onReview: (rec: Recommendation, status: ReviewStatus) => void;
}) {
  const [open, setOpen] = useState<Set<number>>(new Set());
  const toggle = (id: number) => setOpen((s) => {
    const next = new Set(s);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    return next;
  });

  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-sm">
        <thead className="text-left text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <th scope="col" className="py-2 pr-3 font-medium">Product</th>
            <th scope="col" className="py-2 pr-3 font-medium">Risk</th>
            <th scope="col" className="py-2 pr-3 text-right font-medium">On hand</th>
            <th scope="col" className="py-2 pr-3 text-right font-medium">Position</th>
            <th scope="col" className="py-2 pr-3 text-right font-medium" title="Forecast demand during the supplier lead time">Lead-time demand</th>
            <th scope="col" className="py-2 pr-3 text-right font-medium">Reorder point</th>
            <th scope="col" className="py-2 pr-3 text-right font-medium">Order qty</th>
            <th scope="col" className="py-2 pr-3 text-right font-medium">Lead time</th>
            <th scope="col" className="py-2 pr-3 text-right font-medium">Est. cost</th>
            <th scope="col" className="py-2 pr-3 font-medium">Review</th>
            <th scope="col" className="py-2 font-medium"><span className="sr-only">Actions</span></th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.map((r) => {
            const expanded = open.has(r.id);
            const canDecide = canReview && r.review_status !== "ordered";
            return (
              <Fragment key={r.id}>
                <tr className={expanded ? "bg-slate-50" : "hover:bg-slate-50"}>
                  <td className="py-2 pr-3">
                    <Link to={`/products/${r.product_id}`} className="font-medium text-brand-600 hover:underline">{r.sku}</Link>
                    <p className="text-xs text-slate-500">{r.name}</p>
                  </td>
                  <td className="py-2 pr-3"><RiskBadge risk={r.risk_category} /></td>
                  <td className="py-2 pr-3 text-right tabular-nums">{fmtInt(r.on_hand)}</td>
                  <td className="py-2 pr-3 text-right tabular-nums">{fmtInt(r.inventory_position)}</td>
                  <td className="py-2 pr-3 text-right tabular-nums">{fmtDecimal(r.forecast_lead_time_demand)}</td>
                  <td className="py-2 pr-3 text-right tabular-nums">{fmtDecimal(r.reorder_point)}</td>
                  <td className="py-2 pr-3 text-right font-semibold tabular-nums">{r.suggested_qty > 0 ? fmtInt(r.suggested_qty) : "—"}</td>
                  <td className="py-2 pr-3 text-right tabular-nums">{r.lead_time_days ? `${r.lead_time_days} d` : "—"}</td>
                  <td className="py-2 pr-3 text-right tabular-nums">{r.suggested_qty > 0 ? fmtMoney(r.estimated_order_cost) : "—"}</td>
                  <td className="py-2 pr-3"><Badge tone={REVIEW_TONE[r.review_status]}>{REVIEW_LABEL[r.review_status]}</Badge></td>
                  <td className="whitespace-nowrap py-2 text-right">
                    <Button variant="ghost" aria-expanded={expanded} aria-controls={`why-${r.id}`} onClick={() => toggle(r.id)}>
                      {expanded ? "Hide" : "Why?"}
                    </Button>
                    {canDecide && r.suggested_qty > 0 && r.review_status !== "approved" && (
                      <Button variant="secondary" disabled={busyId === r.id} onClick={() => onReview(r, "approved")}
                              aria-label={`Approve ${r.sku}`}>Approve</Button>
                    )}
                    {canDecide && r.review_status !== "rejected" && r.suggested_qty > 0 && (
                      <Button variant="ghost" disabled={busyId === r.id} onClick={() => onReview(r, "rejected")}
                              aria-label={`Reject ${r.sku}`}>Reject</Button>
                    )}
                    {canDecide && r.review_status !== "pending" && (
                      <Button variant="ghost" disabled={busyId === r.id} onClick={() => onReview(r, "pending")}
                              aria-label={`Undo decision for ${r.sku}`}>Undo</Button>
                    )}
                  </td>
                </tr>
                {expanded && (
                  <tr id={`why-${r.id}`} className="bg-slate-50">
                    <td colSpan={11} className="px-3 pb-4 pt-1">
                      <Explanation rec={r} />
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function Explanation({ rec }: { rec: Recommendation }) {
  const figures: [string, string][] = [
    ["Safety stock", fmtDecimal(rec.safety_stock)],
    ["Demand over lead time + review", fmtDecimal(rec.forecast_protection_demand)],
    ["Order-up-to level", fmtDecimal(rec.order_up_to)],
    ["Days of cover", rec.days_of_cover ? `${fmtDecimal(rec.days_of_cover)} d` : "—"],
    ["Stockout chance over lead time (model estimate)", rec.stockout_probability === null ? "—" : fmtPct(rec.stockout_probability)],
  ];
  return (
    <div className="space-y-3">
      <p className="max-w-4xl text-sm leading-relaxed text-slate-700">{rec.explanation}</p>
      <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-5">
        {figures.map(([label, value]) => (
          <div key={label}>
            <dt className="text-xs text-slate-500">{label}</dt>
            <dd className="font-medium tabular-nums">{value}</dd>
          </div>
        ))}
      </dl>
      {rec.warnings.length > 0 && (
        <ul className="list-disc space-y-1 pl-5 text-xs text-amber-800">
          {rec.warnings.map((w) => <li key={w}>{w}</li>)}
        </ul>
      )}
    </div>
  );
}
