import { useState } from "react";

import { api } from "../../api/client";
import type { ImportJob, PolicyDefaults } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { Badge, Card, EmptyState, ErrorMessage, PageHeader, Skeleton } from "../../components/ui";
import { useToast } from "../../components/Toast";
import { useApi } from "../../hooks/useApi";
import { fmtDateTime, fmtInt } from "../../lib/format";
import { PolicyForm } from "./PolicyForm";
import { CatalogSetup } from "./CatalogSetup";
import { DataImport, IMPORT_STEPS } from "./DataImport";
import { FestivalCalendar } from "./FestivalCalendar";
import { UsersAdmin } from "./UsersAdmin";

const JOB_TONE = { pending: "gray", running: "blue", completed: "green", failed: "red" } as const;

export function SettingsPage() {
  const { can } = useAuth();
  const isAdmin = can("admin");
  const policy = useApi((signal) => api.get<PolicyDefaults>("/settings/policy", undefined, signal));
  const jobs = useApi((signal) => api.get<ImportJob[]>("/imports/jobs", undefined, signal));
  const toast = useToast();
  const [imports, setImports] = useState(0);        // bumps after each import, so the supplier/category lists refresh

  return (
    <>
      <PageHeader title="Settings & data import"
                  description="Import your shop's data from Excel, set up suppliers and categories, default reorder settings and (for admins) user accounts." />
      <div className="grid grid-cols-1 gap-6">
        <Card title="Reorder and forecast settings">
          {policy.error && <ErrorMessage message={policy.error} onRetry={policy.reload} />}
          {policy.loading && !policy.data && <Skeleton variant="text" />}
          {policy.data && <PolicyForm key={JSON.stringify(policy.data)} policy={policy.data} canEdit={isAdmin}
                                      onSaved={() => { toast("Settings saved. New recommendation runs will use them."); policy.reload(); }} />}
        </Card>

        <Card title="Import data (Excel or CSV)">
          {can("admin", "manager")
            ? <DataImport onImported={() => { jobs.reload(); setImports((n) => n + 1); }} />
            : <p className="text-sm text-slate-600">Only managers and admins can import data.</p>}
        </Card>

        <Card title="Suppliers and categories">
          <CatalogSetup canEdit={can("admin", "manager")} version={imports} />
        </Card>

        <Card title="Import history">
          {jobs.error && <ErrorMessage message={jobs.error} onRetry={jobs.reload} />}
          {jobs.data && jobs.data.length === 0 && <EmptyState icon="upload" title="No imports yet">Your Excel and CSV imports will be listed here.</EmptyState>}
          {jobs.data && jobs.data.length > 0 && (
            <table className="min-w-full text-sm">
              <thead className="text-left text-xs uppercase tracking-wide text-slate-500">
                <tr>
                  <th scope="col" className="py-2 pr-3 font-medium">When</th>
                  <th scope="col" className="py-2 pr-3 font-medium">Type</th>
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
                    <td className="py-2 pr-3">{IMPORT_STEPS.find((s) => s.type === j.import_type)?.label ?? j.import_type}</td>
                    <td className="py-2 pr-3">{j.filename}</td>
                    <td className="py-2 pr-3"><Badge tone={JOB_TONE[j.status]}>{j.status === "failed" ? "Rejected" : j.status}</Badge></td>
                    <td className="py-2 pr-3 text-right tabular-nums">{fmtInt(j.rows_total)}</td>
                    <td className="py-2 text-slate-600">
                      {j.status === "completed"
                        ? `${fmtInt(j.errors?.added ?? 0)} added, ${fmtInt(j.errors?.replaced ?? 0)} ${j.import_type === "sales" ? "replaced" : "updated"}`
                        : `${fmtInt(j.rows_invalid)} invalid row(s); nothing imported`}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>

        <Card title="Festival calendar">
          <FestivalCalendar />
        </Card>

        {isAdmin && <Card title="User accounts"><UsersAdmin /></Card>}
      </div>
    </>
  );
}
