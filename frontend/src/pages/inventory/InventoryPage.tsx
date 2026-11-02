import { useState } from "react";
import { useSearchParams } from "react-router-dom";

import { api } from "../../api/client";
import type { StockItem, TransactionRow } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { Dialog } from "../../components/Dialog";
import { TabPanel, Tabs } from "../../components/Tabs";
import { Card, ErrorMessage, PageHeader, SimulatedTag, Skeleton } from "../../components/ui";
import { useToast } from "../../components/Toast";
import { useApi } from "../../hooks/useApi";
import { useReference } from "../../hooks/useReference";
import { fmtInt } from "../../lib/format";
import { AdjustmentForm } from "./AdjustmentForm";
import { AlertsList } from "./AlertsList";
import { MovementsTable } from "./MovementsTable";
import { StockTable } from "./StockTable";

type Tab = "stock" | "alerts" | "movements";

export function InventoryPage() {
  const { can } = useAuth();
  const canAdjust = can("admin", "manager");
  const [params, setParams] = useSearchParams();
  const tab = (params.get("tab") as Tab) || "stock";
  const [adjusting, setAdjusting] = useState<StockItem | null>(null);
  const [historyFor, setHistoryFor] = useState<{ id: number; sku: string } | null>(null);
  const toast = useToast();
  const [refreshKey, setRefreshKey] = useState(0);
  const reference = useReference();
  const alerts = useApi((signal) => api.get<StockItem[]>("/inventory/alerts", undefined, signal), [refreshKey]);

  const selectTab = (next: Tab) => {
    const p = new URLSearchParams(params);
    p.set("tab", next);
    setParams(p, { replace: true });
  };

  function onSaved(txn: TransactionRow) {
    setAdjusting(null);
    toast(`Recorded: ${txn.sku} ${txn.quantity > 0 ? "+" : ""}${fmtInt(txn.quantity)} (${txn.txn_type}). Stock is now ${fmtInt(txn.balance_after)}.`);
    setRefreshKey((k) => k + 1);
  }

  return (
    <>
      <PageHeader
        title="Inventory"
        description={<span className="flex flex-wrap items-center gap-2">
          Current stock, low-stock alerts and the audit log of every movement. <SimulatedTag />
        </span>}
      />

      <Card>
        <Tabs label="Inventory views" selected={tab} onSelect={selectTab} tabs={[
          { id: "stock", label: "Stock levels" },
          { id: "alerts", label: "Low-stock alerts", count: alerts.data?.length },
          { id: "movements", label: "Movement history" },
        ]} />
        {tab === "stock" && (
          <TabPanel id="stock">
            <StockTable categories={reference.data?.categories ?? []} initialSearch={params.get("search") ?? ""}
                        canAdjust={canAdjust} onAdjust={setAdjusting} refreshKey={refreshKey}
                        onHistory={(item) => { setHistoryFor({ id: item.product_id, sku: item.sku }); selectTab("movements"); }} />
          </TabPanel>
        )}
        {tab === "alerts" && (
          <TabPanel id="alerts">
            {alerts.error && <ErrorMessage message={alerts.error} onRetry={alerts.reload} />}
            {alerts.loading && !alerts.data && <Skeleton label="Loading alerts…" />}
            {alerts.data && <AlertsList alerts={alerts.data} canAdjust={canAdjust} onAdjust={setAdjusting} />}
          </TabPanel>
        )}
        {tab === "movements" && (
          <TabPanel id="movements">
            <MovementsTable product={historyFor} onClearProduct={() => setHistoryFor(null)} refreshKey={refreshKey} />
          </TabPanel>
        )}
      </Card>

      <Dialog title="Record a stock movement" open={!!adjusting} onClose={() => setAdjusting(null)}>
        {adjusting && <AdjustmentForm item={adjusting} onSaved={onSaved} onCancel={() => setAdjusting(null)} />}
      </Dialog>
    </>
  );
}
