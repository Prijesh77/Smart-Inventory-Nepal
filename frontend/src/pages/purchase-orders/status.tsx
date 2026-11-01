import type { PurchaseOrderStatus } from "../../api/types";
import { Badge } from "../../components/ui";

export const PO_STATUS: Record<PurchaseOrderStatus, { label: string; tone: "gray" | "blue" | "amber" | "green" | "red" }> = {
  draft: { label: "Draft", tone: "gray" },
  submitted: { label: "Submitted", tone: "blue" },
  partially_received: { label: "Partly received", tone: "amber" },
  received: { label: "Received", tone: "green" },
  cancelled: { label: "Cancelled", tone: "red" },
};

export function PoStatusBadge({ status }: { status: PurchaseOrderStatus }) {
  return <Badge tone={PO_STATUS[status].tone}>{PO_STATUS[status].label}</Badge>;
}

export const NOT_SENT_NOTE = "Orders are only recorded in this app. Nothing is ever sent to a supplier.";
