import { Link } from "react-router-dom";

import type { StockItem } from "../../api/types";
import { Button, EmptyState } from "../../components/ui";
import { fmtDecimal, fmtInt } from "../../lib/format";
import { CoverCell, StockStatusBadge } from "./StockTable";

/** Out-of-stock and low products, most urgent first (order comes from the API). */
export function AlertsList({ alerts, canAdjust, onAdjust }:
  { alerts: StockItem[]; canAdjust: boolean; onAdjust: (item: StockItem) => void }) {
  if (!alerts.length) {
    return <EmptyState icon="check" title="No low-stock alerts">Every product's stock covers its supplier lead time at the recent sales rate.</EmptyState>;
  }
  return (
    <>
      <p className="mb-3 text-sm text-slate-500">
        Rule: an item is <strong>low</strong> when its stock position (on hand + on order) will not last until a new order
        could arrive, at the average sales rate of the last 28 days. For forecast-based advice see{" "}
        <Link to="/recommendations" className="text-brand-600 hover:underline">Reorder recommendations</Link>.
      </p>
      <ul className="divide-y divide-slate-100">
        {alerts.map((a) => (
          <li key={a.product_id} className="flex flex-wrap items-center justify-between gap-3 py-3">
            <div>
              <div className="flex items-center gap-2">
                <StockStatusBadge status={a.stock_status} />
                <Link to={`/products/${a.product_id}`} className="font-medium text-brand-600 hover:underline">{a.sku}</Link>
                <span className="text-sm text-slate-500">{a.name}</span>
              </div>
              <p className="mt-1 text-sm text-slate-600">
                {fmtInt(a.inventory_position)} units in position · sells {fmtDecimal(a.avg_daily_sales)}/day ·
                cover <CoverCell item={a} /> vs lead time {a.lead_time_days ?? "—"} d
              </p>
            </div>
            {canAdjust && <Button variant="secondary" onClick={() => onAdjust(a)}>Adjust stock</Button>}
          </li>
        ))}
      </ul>
    </>
  );
}
