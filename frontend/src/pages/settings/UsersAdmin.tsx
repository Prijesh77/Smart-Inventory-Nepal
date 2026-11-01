import { useState, type FormEvent } from "react";

import { api, ApiError } from "../../api/client";
import type { Role, User } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { SelectField, TextField } from "../../components/fields";
import { Badge, Button, ErrorMessage, Spinner } from "../../components/ui";
import { useApi } from "../../hooks/useApi";
import { fmtDate } from "../../lib/format";

const ROLE_HELP: Record<Role, string> = {
  admin: "Everything, including users and settings",
  manager: "Products, stock, forecasts, approvals and orders",
  viewer: "Read-only",
};

/** Admin-only list of accounts: add users, change role, deactivate. */
export function UsersAdmin() {
  const { user: me } = useAuth();
  const { data, error, loading, reload } = useApi((signal) => api.get<User[]>("/users", undefined, signal));
  const [message, setMessage] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const [form, setForm] = useState({ email: "", full_name: "", password: "", role: "viewer" as Role });
  const [saving, setSaving] = useState(false);

  async function change(user: User, body: Partial<Pick<User, "role" | "is_active">>, text: string) {
    setMessage(null);
    try {
      await api.patch(`/users/${user.id}`, body);
      setMessage({ kind: "ok", text });
      reload();
    } catch (err) {
      setMessage({ kind: "error", text: err instanceof ApiError ? err.message : "Could not update the account" });
    }
  }

  async function add(event: FormEvent) {
    event.preventDefault();
    if (form.password.length < 10) return setMessage({ kind: "error", text: "The password needs at least 10 characters" });
    setSaving(true);
    setMessage(null);
    try {
      const created = await api.post<User>("/users", form);
      setMessage({ kind: "ok", text: `Account ${created.email} created (${created.role}).` });
      setForm({ email: "", full_name: "", password: "", role: "viewer" });
      reload();
    } catch (err) {
      setMessage({ kind: "error", text: err instanceof ApiError ? err.message : "Could not create the account" });
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-4">
      {message && (
        <p role={message.kind === "error" ? "alert" : "status"}
           className={`rounded-md p-3 text-sm ${message.kind === "error" ? "bg-red-50 text-red-800" : "bg-emerald-50 text-emerald-800"}`}>
          {message.text}
        </p>
      )}
      {error && <ErrorMessage message={error} onRetry={reload} />}
      {loading && !data && <Spinner />}
      {data && (
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead className="text-left text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th scope="col" className="py-2 pr-3 font-medium">Name</th>
                <th scope="col" className="py-2 pr-3 font-medium">Email</th>
                <th scope="col" className="py-2 pr-3 font-medium">Role</th>
                <th scope="col" className="py-2 pr-3 font-medium">Status</th>
                <th scope="col" className="py-2 pr-3 font-medium">Since</th>
                <th scope="col" className="py-2 font-medium"><span className="sr-only">Actions</span></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {data.map((u) => (
                <tr key={u.id}>
                  <td className="py-2 pr-3 font-medium">{u.full_name}{u.id === me?.id && <span className="ml-1 text-xs text-slate-500">(you)</span>}</td>
                  <td className="py-2 pr-3">{u.email}</td>
                  <td className="py-2 pr-3">
                    <select aria-label={`Role for ${u.email}`} value={u.role} disabled={u.id === me?.id}
                            onChange={(e) => change(u, { role: e.target.value as Role }, `${u.email} is now ${e.target.value}.`)}
                            className="rounded-md border border-slate-300 bg-white px-2 py-1 text-sm">
                      {(Object.keys(ROLE_HELP) as Role[]).map((r) => <option key={r} value={r}>{r}</option>)}
                    </select>
                  </td>
                  <td className="py-2 pr-3"><Badge tone={u.is_active ? "green" : "gray"}>{u.is_active ? "Active" : "Inactive"}</Badge></td>
                  <td className="py-2 pr-3 text-slate-500">{fmtDate(u.created_at)}</td>
                  <td className="py-2 text-right">
                    {u.id !== me?.id && (
                      <Button variant="ghost" onClick={() => change(u, { is_active: !u.is_active },
                        `${u.email} ${u.is_active ? "deactivated (can no longer log in)" : "reactivated"}.`)}>
                        {u.is_active ? "Deactivate" : "Reactivate"}
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <form onSubmit={add} noValidate className="space-y-3 border-t border-slate-100 pt-4">
        <h3 className="text-sm font-semibold text-slate-800">Add an account</h3>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <TextField id="new-name" label="Full name" value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
          <TextField id="new-email" label="Email" type="email" autoComplete="off" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
          <TextField id="new-password" label="First password" type="password" autoComplete="new-password" value={form.password}
                     hint="At least 10 characters; share it privately" onChange={(e) => setForm({ ...form, password: e.target.value })} />
          <SelectField id="new-role" label="Role" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as Role })}>
            {(Object.keys(ROLE_HELP) as Role[]).map((r) => <option key={r} value={r}>{r}: {ROLE_HELP[r]}</option>)}
          </SelectField>
        </div>
        <div className="flex justify-end">
          <Button type="submit" disabled={saving || !form.email || !form.full_name}>{saving ? "Adding…" : "Add account"}</Button>
        </div>
      </form>
    </div>
  );
}
