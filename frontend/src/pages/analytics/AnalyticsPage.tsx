import { useState } from "react";

import { ApiError, downloadFile } from "../../api/client";
import { Button, Card, ErrorMessage, PageHeader } from "../../components/ui";
import { ModelComparison } from "../forecasts/ModelComparison";
import { CategoryTable, WeeklyTrend } from "./CategorySection";
import { SimulationSection } from "./SimulationSection";

export const EXPORTS = [
  { dataset: "products", label: "Products" },
  { dataset: "inventory", label: "Current stock" },
  { dataset: "transactions", label: "Stock movements" },
  { dataset: "recommendations", label: "Latest recommendations" },
  { dataset: "purchase-orders", label: "Purchase orders" },
  { dataset: "forecast", label: "Latest forecast" },
] as const;

function Exports() {
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<{ kind: "ok" | "error"; text: string } | null>(null);

  async function download(dataset: string) {
    setBusy(dataset);
    setMessage(null);
    try {
      const name = await downloadFile(`/exports/${dataset}.csv`, `${dataset}.csv`);
      setMessage({ kind: "ok", text: `Downloaded ${name}` });
    } catch (err) {
      setMessage({ kind: "error", text: err instanceof ApiError ? err.message : "Download failed" });
    } finally {
      setBusy(null);
    }
  }

  return (
    <>
      <div className="flex flex-wrap gap-2">
        {EXPORTS.map((e) => (
          <Button key={e.dataset} variant="secondary" disabled={busy !== null} onClick={() => download(e.dataset)}>
            {busy === e.dataset ? "Preparing…" : `⬇ ${e.label}`}
          </Button>
        ))}
      </div>
      {message?.kind === "ok" && <p role="status" className="mt-3 text-sm text-emerald-700">{message.text}</p>}
      {message?.kind === "error" && <div className="mt-3"><ErrorMessage message={message.text} /></div>}
      <p className="mt-3 text-xs text-slate-500">
        CSV files open in Excel. Columns based on simulated data are marked "(simulated)" in their header; text cells are
        protected so a spreadsheet cannot run them as formulas.
      </p>
    </>
  );
}

export function AnalyticsPage({ pollMs }: { pollMs?: number }) {
  return (
    <>
      <PageHeader title="Analytics & reports"
                  description="Sales trends and category performance, forecast accuracy, simulated policy comparison, and CSV reports." />
      <div className="grid grid-cols-1 gap-6">
        <Card title="Category performance"><CategoryTable /></Card>
        <Card title="Weekly demand by category"><WeeklyTrend /></Card>
        <Card title="Forecast accuracy by model and demand pattern"><ModelComparison /></Card>
        <Card title="Inventory policy simulation: cost vs service"><SimulationSection pollMs={pollMs} /></Card>
        <Card title="Download reports (CSV)"><Exports /></Card>
      </div>
      <p className="mt-6 text-xs text-slate-500">
        Inventory aging (how long stock has been on the shelf) is not shown: the data has no batch or receipt dates for
        the opening stock, so it could not be calculated honestly.
      </p>
    </>
  );
}
