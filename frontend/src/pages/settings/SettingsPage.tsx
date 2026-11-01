import { useState } from "react";

import { api } from "../../api/client";
import type { ImportJob, PolicyDefaults } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { Badge, Card, EmptyState, ErrorMessage, PageHeader, Spinner } from "../../components/ui";
import { useApi } from "../../hooks/useApi";
import { fmtDateTime, fmtInt } from "../../lib/format";
import { CurrencyForm } from "./CurrencyForm";
import { PolicyForm } from "./PolicyForm";
import { SalesImport } from "./SalesImport";
import { UsersAdmin } from "./UsersAdmin";

const JOB_TONE = { pending: "gray", running: "blue", completed: "green", failed: "red" } as const;

export function SettingsPage() {
  const { can } = useAuth();
  const isAdmin = can("admin");
  const policy = useApi((signal) => api.get<PolicyDefaults>("/settings/policy", undefined, signal));
  const jobs = useApi((signal) => api.get<ImportJob[]>("/imports/jobs", undefined, signal));
  const [saved, setSaved] = useState(false);

  return (
    <>
      <PageHeader title="Settings & data import"
                  description="Default reorder settings, sales data import, and (for admins) user accounts." />
      <div className="grid grid-cols-1 gap-6">
        <Card title="Reorder and forecast settings">
          {saved && <p role="status" className="mb-4 rounded-md bg-emerald-50 p-3 text-sm text-emerald-800">Settings saved. New recommendation runs will use them.</p>}
          {policy.error && <ErrorMessage message={policy.error} onRetry={policy.reload} />}
          {policy.loading && !policy.data && <Spinner />}
          {policy.data && <PolicyForm key={JSON.stringify(policy.data)} policy={policy.data} canEdit={isAdmin}
                                      onSaved={() => { setSaved(true); policy.reload(); }} />}
        </Card>

        <Card title="Currency">
          <CurrencyForm canEdit={isAdmin} />
        </Card>

        <Card title="Import sales data (CSV)">
          {can("admin", "manager")
            ? <SalesImport onImported={() => jobs.reload()} />
            : <p className="text-sm text-slate-600">Only managers and admins can import data.</p>}
        </Card>

        <Card title="Import history">
          {jobs.error && <ErrorMessage message={jobs.error} onRetry={jobs.reload} />}
          {jobs.data && jobs.data.length === 0 && <EmptyState title="No imports yet" />}
          {jobs.data && jobs.data.length > 0 && (
            <table className="min-w-full text-sm">
              <thead className="text-left text-xs uppercase tracking-wide text-slate-500">
                <tr>
                  <th scope="col" className="py-2 pr-3 font-medium">When</th>
                  <th scope="col" className="py-2 pr-3 font-medium">File</th>
                  <th scope="col" className="py-2 pr-3 font-medium">Result</th>
                  <th scope="col" className="py-2 pr-3 text-right font-medium">Rows</th>
                  <th scope="col" className="py-2 font-medium">Details</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {jobs.data.map((j) => (
                  <tr key={j.id}>
                    <td className="whitespace-nowrap py-2 pr-3 text-slate-500">{fmtDateTime(j.created_at)}</td>
                    <td className="py-2 pr-3">{j.filename}</td>
                    <td className="py-2 pr-3"><Badge tone={JOB_TONE[j.status]}>{j.status === "failed" ? "Rejected" : j.status}</Badge></td>
                    <td className="py-2 pr-3 text-right tabular-nums">{fmtInt(j.rows_total)}</td>
                    <td className="py-2 text-slate-600">
                      {j.status === "completed"
                        ? `${fmtInt(j.errors?.added ?? 0)} added, ${fmtInt(j.errors?.replaced ?? 0)} replaced`
                        : `${fmtInt(j.rows_invalid)} invalid row(s); nothing imported`}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>

        {isAdmin && <Card title="User accounts"><UsersAdmin /></Card>}
      </div>
    </>
  );
}
