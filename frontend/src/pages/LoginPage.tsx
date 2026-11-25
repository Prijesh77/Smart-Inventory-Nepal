import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { Icon, type IconName } from "../components/Icons";
import { Button, ErrorMessage, Notice } from "../components/ui";
import { LANGUAGES, lang, setLang, t, type Lang } from "../lib/i18n";

export function LoginPage() {
  const { user, login, notice } = useAuth();
  const navigate = useNavigate();
  const from = (useLocation().state as { from?: string } | null)?.from ?? "/";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [language, setLanguage] = useState<Lang>(lang);     // re-draws this page when the language changes

  if (user) return <Navigate to={from} replace />;

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email.trim(), password, remember);
      navigate(from, { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("Login failed. Please try again."));
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
          <span className="text-lg font-semibold">Smart Inventory Nepal</span>
        </div>
        <div className="relative max-w-md">
          <p className="text-3xl font-semibold leading-tight tracking-tight">
            {t("Know what to reorder, how much, and why.")}
          </p>
          <ul className="mt-8 space-y-4 text-sm text-slate-300">
            {FEATURES.map(({ icon, text }) => {
              const FeatureIcon = Icon[icon];
              return (
                <li key={text} className="flex items-start gap-3">
                  <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-white/10 text-brand-300">
                    <FeatureIcon className="h-4 w-4" />
                  </span>
                  <span className="pt-1.5">{t(text)}</span>
                </li>
              );
            })}
          </ul>
        </div>
        <p className="relative text-xs text-slate-500">{t("For kirana shops, pharmacies, hardware stores and wholesalers in Nepal · © 2026 Prijesh")}</p>
      </section>

      {/* Sign-in form */}
      <div className="flex items-center justify-center px-4 py-12 sm:px-8">
        <div className="w-full max-w-sm">
          <div role="group" aria-label={t("Language")} className="mb-6 flex justify-end gap-1 text-xs">
            {LANGUAGES.map((l) => (
              <button key={l.value} type="button" aria-pressed={language === l.value}
                      onClick={() => { setLang(l.value); setLanguage(l.value); }}
                      className={`rounded-md px-2.5 py-1 font-medium ${language === l.value ? "bg-brand-50 text-brand-700 ring-1 ring-inset ring-brand-200" : "text-slate-500 hover:bg-slate-100"}`}>
                {l.label}
              </button>
            ))}
          </div>
          <div className="mb-8">
            <span className="mb-6 flex h-11 w-11 items-center justify-center rounded-lg bg-gradient-to-br from-brand-400 to-brand-700 text-white lg:hidden">
              <Icon.box className="h-5 w-5" />
            </span>
            <h1 className="text-2xl font-semibold tracking-tight text-slate-900">Smart Inventory Nepal</h1>
            <p className="mt-1.5 text-sm text-slate-500">{t("Sign in to see forecasts and reorder recommendations.")}</p>
          </div>
          <form onSubmit={onSubmit} className="space-y-5" noValidate>
            {notice && !error && <Notice tone="warning">{notice}</Notice>}
            {error && <ErrorMessage message={error} />}
            <div>
              <label htmlFor="email" className="block text-sm font-medium text-slate-700">{t("Email")}</label>
              <input
                id="email" type="email" autoComplete="username" required value={email}
                onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com"
                className="mt-1.5 w-full rounded-md border border-slate-300 px-3 py-2.5 text-sm"
              />
            </div>
            <div>
              <label htmlFor="password" className="block text-sm font-medium text-slate-700">{t("Password")}</label>
              <input
                id="password" type="password" autoComplete="current-password" required value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="mt-1.5 w-full rounded-md border border-slate-300 px-3 py-2.5 text-sm"
              />
            </div>
            <div>
              <label className="flex items-center gap-2 text-sm text-slate-700">
                <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)}
                       aria-describedby="remember-hint" className="h-4 w-4 rounded border-slate-300" />
                {t("Remember me on this device")}
              </label>
              <p id="remember-hint" className="mt-1 pl-6 text-xs text-slate-500">
                {t("Stay logged in for 30 days. Do not tick this on a shared computer.")}
              </p>
            </div>
            <Button type="submit" className="w-full py-2.5" disabled={submitting || !email || !password}>
              {submitting ? t("Logging in…") : t("Log in")}
            </Button>
          </form>
          <p className="mt-8 flex items-start gap-2 rounded-lg bg-slate-50 p-3 text-xs leading-relaxed text-slate-500 ring-1 ring-inset ring-slate-200">
            <Icon.info className="mt-px h-4 w-4 shrink-0 text-slate-400" />
            {t("Each shop sees only its own products, stock, sales and orders. Demo shops use synthetic data. Amounts are in Nepalese rupees.")}
          </p>
        </div>
      </div>
    </main>
  );
}

const FEATURES = [
  { icon: "trend", text: "Demand forecasts that learn your shop's sales and know Dashain and Tihar" },
  { icon: "cart", text: "Reorder suggestions in rupees that explain their own numbers" },
  { icon: "clipboard", text: "Bikram Sambat dates, Excel import, orders and a full stock audit trail" },
] as const satisfies readonly { icon: IconName; text: string }[];
