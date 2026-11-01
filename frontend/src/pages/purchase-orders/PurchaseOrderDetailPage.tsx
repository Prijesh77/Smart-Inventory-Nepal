import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { api, ApiError } from "../../api/client";
import type { PurchaseOrder } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { Dialog } from "../../components/Dialog";
import { Button, Card, ErrorMessage, PageHeader, SimulatedTag, Spinner } from "../../components/ui";
import { useApi } from "../../hooks/useApi";
import { useReference } from "../../hooks/useReference";
import { fmtDate, fmtDateTime, fmtInt, fmtMoney } from "../../lib/format";
import { OrderForm } from "./OrderForm";
import { ReceiveForm } from "./ReceiveForm";
import { NOT_SENT_NOTE, PoStatusBadge } from "./status";

export function PurchaseOrderDetailPage() {
  const { id } = useParams();
  const { can } = useAuth();
  const canAct = can("admin", "manager");
  const reference = useReference();
  const { data, error, loading, reload } = useApi((signal) => api.get<PurchaseOrder>(`/purchase-orders/${id}`, undefined, signal), [id]);
  const [order, setOrder] = useState<PurchaseOrder | null>(null);
  const [dialog, setDialog] = useState<"edit" | "receive" | "cancel" | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ kind: "ok" | "error"; text: string } | null>(null);

  const po = order && String(order.id) === id ? order : data;
  if (loading && !po) return <Spinner label="Loading order…" />;
  if (error && !po) return <ErrorMessage message={error} onRetry={reload} />;
  if (!po) return null;

  async function action(path: "submit" | "cancel", success: string) {
    setBusy(true);
    setMessage(null);
    try {
      setOrder(await api.post<PurchaseOrder>(`/purchase-orders/${po!.id}/${path}`));
      setMessage({ kind: "ok", text: success });
      setDialog(null);
    } catch (err) {
      setMessage({ kind: "error", text: err instanceof ApiError ? err.message : "The action failed" });
    } finally {
      setBusy(false);
    }
  }

  const received = po.lines.reduce((s, l) => s + l.quantity_received, 0);
  const canReceive = po.status === "submitted" || po.status === "partially_received";
  const canCancel = (po.status === "draft" || po.status === "submitted") && received === 0;

  return (
    <>
      <Link to="/purchase-orders" className="text-sm text-brand-600 hover:underline">← All purchase orders</Link>
      <div className="mt-2">
        <PageHeader
          title={po.po_number}
          description={<span className="flex flex-wrap items-center gap-2"><PoStatusBadge status={po.status} /> {po.supplier_name}</span>}
          actions={canAct && (
            <>
              {po.status === "draft" && <Button variant="secondary" onClick={() => setDialog("edit")}>Edit draft</Button>}
              {po.status === "draft" && (
                <Button disabled={busy} onClick={() => action("submit", "Order marked as submitted. It now counts as stock on order. Nothing was sent to the supplier.")}>
                  Submit order
                </Button>
              )}
              {canReceive && <Button onClick={() => setDialog("receive")}>Receive delivery</Button>}
              {canCancel && <Button variant="danger" onClick={() => setDialog("cancel")}>Cancel order</Button>}
            </>
          )}
        />
      </div>
      {message && (
        <p role={message.kind === "error" ? "alert" : "status"}
           className={`mb-4 rounded-md p-3 text-sm ${message.kind === "error" ? "bg-red-50 text-red-800" : "bg-emerald-50 text-emerald-800"}`}>
          {message.text}
        </p>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <Card title={<span className="flex items-center gap-2">Lines <SimulatedTag /></span>} className="lg:col-span-2">
          <table className="min-w-full text-sm">
            <thead className="text-left text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th scope="col" className="py-2 pr-3 font-medium">Product</th>
                <th scope="col" className="py-2 pr-3 text-right font-medium">Ordered</th>
                <th scope="col" className="py-2 pr-3 text-right font-medium">Received</th>
                <th scope="col" className="py-2 pr-3 text-right font-medium">Still expected</th>
                <th scope="col" className="py-2 pr-3 text-right font-medium">Unit cost</th>
                <th scope="col" className="py-2 text-right font-medium">Line total</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {po.lines.map((l) => (
                <tr key={l.id}>
                  <td className="py-2 pr-3">
                    <Link to={`/products/${l.product_id}`} className="font-medium text-brand-600 hover:underline">{l.sku}</Link>
                    <p className="text-xs text-slate-500">{l.name}{l.recommendation_id && " · from a reorder recommendation"}</p>
                  </td>
                  <td className="py-2 pr-3 text-right tabular-nums">{fmtInt(l.quantity_ordered)}</td>
                  <td className="py-2 pr-3 text-right tabular-nums">{fmtInt(l.quantity_received)}</td>
                  <td className="py-2 pr-3 text-right tabular-nums">{fmtInt(l.quantity_outstanding)}</td>
                  <td className="py-2 pr-3 text-right tabular-nums">{fmtMoney(l.unit_cost)}</td>
                  <td className="py-2 text-right tabular-nums">{fmtMoney(l.line_total)}</td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr className="font-semibold">
                <td className="pt-3">Total</td>
                <td className="pt-3 text-right tabular-nums">{fmtInt(po.total_units)}</td>
                <td className="pt-3 text-right tabular-nums">{fmtInt(received)}</td>
                <td className="pt-3 text-right tabular-nums">{fmtInt(po.total_units - received)}</td>
                <td />
                <td className="pt-3 text-right tabular-nums">{fmtMoney(po.total_cost)}</td>
              </tr>
            </tfoot>
          </table>
        </Card>

        <Card title="Order details">
          <dl className="space-y-3 text-sm">
            <Row label="Supplier" value={`${po.supplier_name} (${po.supplier_code})`} />
            <Row label="Expected delivery" value={fmtDate(po.expected_date)} />
            <Row label="Created" value={fmtDateTime(po.created_at)} />
            <Row label="Submitted" value={fmtDateTime(po.submitted_at)} />
            <Row label="Fully received" value={fmtDateTime(po.received_at)} />
            {po.notes && <Row label="Notes" value={po.notes} />}
          </dl>
          <p className="mt-4 rounded-md bg-slate-50 p-3 text-xs text-slate-600">{NOT_SENT_NOTE}</p>
        </Card>
      </div>

      <Dialog title={`Edit ${po.po_number}`} open={dialog === "edit"} onClose={() => setDialog(null)} wide>
        <OrderForm order={po} suppliers={reference.data?.suppliers ?? []} onCancel={() => setDialog(null)}
                   onSaved={(saved) => { setOrder(saved); setDialog(null); setMessage({ kind: "ok", text: "Draft saved." }); }} />
      </Dialog>
      <Dialog title={`Receive ${po.po_number}`} open={dialog === "receive"} onClose={() => setDialog(null)} wide>
        <ReceiveForm order={po} onCancel={() => setDialog(null)}
                     onReceived={(saved) => {
                       setOrder(saved);
                       setDialog(null);
                       setMessage({ kind: "ok", text: saved.status === "received"
                         ? "Delivery booked. The order is fully received and stock has been updated."
                         : "Partial delivery booked. Stock has been updated; the rest is still expected." });
                     }} />
      </Dialog>
      <Dialog title={`Cancel ${po.po_number}?`} open={dialog === "cancel"} onClose={() => setDialog(null)}>
        <p className="text-sm text-slate-700">
          The order will be marked as cancelled and will no longer count as stock on order. Recommendations it came from go
          back to "approved", so they can be ordered again.
        </p>
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="secondary" onClick={() => setDialog(null)}>Keep order</Button>
          <Button variant="danger" disabled={busy} onClick={() => action("cancel", "Order cancelled.")}>Cancel order</Button>
        </div>
      </Dialog>
    </>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-4">
      <dt className="text-slate-500">{label}</dt>
      <dd className="text-right font-medium text-slate-800">{value}</dd>
    </div>
  );
}
