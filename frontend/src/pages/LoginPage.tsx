import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { Icon, type IconName } from "../components/Icons";
import { Button, ErrorMessage } from "../components/ui";

export function LoginPage() {
  const { user, login, notice } = useAuth();
  const navigate = useNavigate();
  const from = (useLocation().state as { from?: string } | null)?.from ?? "/";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (user) return <Navigate to={from} replace />;

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email.trim(), password);
      navigate(from, { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Login failed. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="grid min-h-screen bg-white lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
      {/* Brand panel (large screens) */}
      <section aria-hidden className="relative hidden overflow-hidden bg-slate-900 p-12 text-white lg:flex lg:flex-col lg:justify-between">
        <div className="pointer-events-none absolute -right-24 -top-24 h-96 w-96 rounded-full bg-brand-600/30 blur-3xl" />
        <div className="pointer-events-none absolute -bottom-32 -left-16 h-80 w-80 rounded-full bg-violet-600/20 blur-3xl" />
        <div className="relative flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-gradient-to-br from-brand-400 to-brand-700">
            <Icon.box className="h-5 w-5" />
          </span>
          <span className="text-lg font-semibold">Smart Inventory</span>
        </div>
        <div className="relative max-w-md">
          <p className="text-3xl font-semibold leading-tight tracking-tight">
            Know what to reorder, how much, and why.
          </p>
          <ul className="mt-8 space-y-4 text-sm text-slate-300">
            {FEATURES.map(({ icon, text }) => {
              const FeatureIcon = Icon[icon];
              return (
                <li key={text} className="flex items-start gap-3">
                  <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-white/10 text-brand-300">
                    <FeatureIcon className="h-4 w-4" />
                  </span>
                  <span className="pt-1.5">{text}</span>
                </li>
              );
            })}
          </ul>
        </div>
        <p className="relative text-xs text-slate-500">Undergraduate IT capstone project · Prijesh</p>
      </section>

      {/* Sign-in form */}
      <div className="flex items-center justify-center px-4 py-12 sm:px-8">
        <div className="w-full max-w-sm">
          <div className="mb-8">
            <span className="mb-6 flex h-11 w-11 items-center justify-center rounded-lg bg-gradient-to-br from-brand-400 to-brand-700 text-white lg:hidden">
              <Icon.box className="h-5 w-5" />
            </span>
            <h1 className="text-2xl font-semibold tracking-tight text-slate-900">Smart Inventory</h1>
            <p className="mt-1.5 text-sm text-slate-500">Sign in to see forecasts and reorder recommendations.</p>
          </div>
          <form onSubmit={onSubmit} className="space-y-5" noValidate>
            {notice && !error && <p role="status" className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">{notice}</p>}
            {error && <ErrorMessage message={error} />}
            <div>
              <label htmlFor="email" className="block text-sm font-medium text-slate-700">Email</label>
              <input
                id="email" type="email" autoComplete="username" required value={email}
                onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com"
                className="mt-1.5 w-full rounded-md border border-slate-300 px-3 py-2.5 text-sm"
              />
            </div>
            <div>
              <label htmlFor="password" className="block text-sm font-medium text-slate-700">Password</label>
              <input
                id="password" type="password" autoComplete="current-password" required value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="mt-1.5 w-full rounded-md border border-slate-300 px-3 py-2.5 text-sm"
              />
            </div>
            <Button type="submit" className="w-full py-2.5" disabled={submitting || !email || !password}>
              {submitting ? "Logging in…" : "Log in"}
            </Button>
          </form>
          <p className="mt-8 flex items-start gap-2 rounded-lg bg-slate-50 p-3 text-xs leading-relaxed text-slate-500 ring-1 ring-inset ring-slate-200">
            <Icon.info className="mt-px h-4 w-4 shrink-0 text-slate-400" />
            Sales: real M5 data (Walmart store CA_1). Stock, costs and lead times are simulated.
          </p>
        </div>
      </div>
    </main>
  );
}

const FEATURES = [
  { icon: "trend", text: "Machine-learning demand forecasts for every product" },
  { icon: "cart", text: "Reorder recommendations that explain their own numbers" },
  { icon: "clipboard", text: "Purchase orders, deliveries and a full stock audit trail" },
] as const satisfies readonly { icon: IconName; text: string }[];
