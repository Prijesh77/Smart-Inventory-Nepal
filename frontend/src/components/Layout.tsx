import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";
import { DATE_STYLES, dateStyle, setDateStyle, type DateStyle } from "../lib/nepaliDate";
import { Icon, type IconName } from "./Icons";
import { Badge } from "./ui";

export const NAV_ITEMS = [
  { to: "/", label: "Overview", icon: "dashboard", group: "Dashboard" },
  { to: "/products", label: "Products", icon: "box", group: "Operations" },
  { to: "/inventory", label: "Inventory", icon: "warehouse", group: "Operations" },
  { to: "/purchase-orders", label: "Purchase orders", icon: "clipboard", group: "Operations" },
  { to: "/forecasts", label: "Forecasting", icon: "trend", group: "Planning" },
  { to: "/recommendations", label: "Reorder", icon: "cart", group: "Planning" },
  { to: "/analytics", label: "Analytics", icon: "chart", group: "Insights" },
  { to: "/settings", label: "Settings & import", icon: "settings", group: "Admin" },
] as const satisfies readonly { to: string; label: string; icon: IconName; group: string }[];

const GROUPS = [...new Set(NAV_ITEMS.map((item) => item.group))];
const ROLE_TONE = { admin: "red", manager: "blue", viewer: "gray" } as const;

function currentItem(pathname: string) {
  return NAV_ITEMS.find((item) => item.to !== "/" && pathname.startsWith(item.to)) ?? NAV_ITEMS[0];
}

export function Layout() {
  const { user, logout } = useAuth();
  const { pathname } = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  const [dates, setDates] = useState<DateStyle>(dateStyle);
  const current = currentItem(pathname);

  useEffect(() => setMenuOpen(false), [pathname]);

  const nav = (
    <nav aria-label="Main" className="space-y-6">
      {GROUPS.map((group) => (
        <div key={group}>
          <p className="px-3 pb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">{group}</p>
          <ul className="space-y-0.5">
            {NAV_ITEMS.filter((item) => item.group === group).map((item) => {
              const ItemIcon = Icon[item.icon];
              return (
                <li key={item.to}>
                  <NavLink
                    to={item.to}
                    end={item.to === "/"}
                    className={({ isActive }) =>
                      `group relative flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                        isActive ? "bg-white/10 text-white" : "text-slate-300 hover:bg-white/5 hover:text-white"}`}
                  >
                    {({ isActive }) => (
                      <>
                        {isActive && <span aria-hidden className="absolute inset-y-1.5 left-0 w-0.5 rounded-full bg-brand-400" />}
                        <ItemIcon className={`h-[18px] w-[18px] ${isActive ? "text-brand-300" : "text-slate-400 group-hover:text-slate-200"}`} />
                        {item.label}
                      </>
                    )}
                  </NavLink>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );

  // Which shop's data is on screen. Demo shops say clearly that their data is made up.
  const dataNote = user && (
    <section aria-label="Shop" className="rounded-lg bg-white/5 p-3 text-xs leading-relaxed text-slate-400 ring-1 ring-inset ring-white/10">
      <p className="mb-1 flex items-center gap-1.5 font-medium text-slate-200">
        <Icon.box className="h-3.5 w-3.5" /> {user.shop.name}
      </p>
      {user.shop.is_demo
        ? <>Demo shop: <span className="text-violet-300">synthetic</span> sales, stock, costs and lead times · amounts in Rs</>
        : <>Your shop&apos;s own data · amounts in Rs</>}
    </section>
  );

  return (
    <div className="min-h-screen lg:flex">
      {/* Sidebar on large screens */}
      <aside className="hidden w-64 shrink-0 bg-slate-900 lg:block">
        <div className="sticky top-0 flex h-screen flex-col">
          <div className="flex h-16 items-center border-b border-white/10 px-5"><Brand /></div>
          <div className="flex-1 overflow-y-auto px-3 py-5">{nav}</div>
          <div className="p-4">{dataNote}</div>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-16 items-center justify-between gap-3 border-b border-slate-200 bg-white/90 px-4 backdrop-blur lg:px-8">
          <div className="flex min-w-0 items-center gap-3">
            <button type="button" className="rounded-md p-2 text-slate-600 hover:bg-slate-100 lg:hidden"
                    aria-label="Open menu" aria-expanded={menuOpen} onClick={() => setMenuOpen((open) => !open)}>
              {menuOpen ? <Icon.close /> : <Icon.menu />}
            </button>
            <p className="truncate text-sm text-slate-500">
              <span className="hidden sm:inline">{current.group} <span aria-hidden className="mx-1.5 text-slate-300">/</span></span>
              <span className="font-medium text-slate-900">{current.label}</span>
            </p>
          </div>
          {user && (
            <div className="flex items-center gap-3">
              <div className="hidden items-center gap-3 sm:flex">
                <Avatar name={user.full_name} />
                <div className="text-right leading-tight">
                  <p className="text-sm font-medium text-slate-800">{user.full_name}</p>
                  <p className="text-xs text-slate-500">{user.email}</p>
                </div>
              </div>
              <Badge tone={ROLE_TONE[user.role]}>{user.role}</Badge>
              <label className="flex items-center gap-1.5 text-xs text-slate-500">
                <span className="hidden md:inline">Dates</span>
                <select aria-label="Show dates as" value={dates}
                        onChange={(e) => { setDateStyle(e.target.value as DateStyle); setDates(e.target.value as DateStyle); }}
                        className="rounded-md border border-slate-300 bg-white py-1 pl-2 pr-7 text-xs text-slate-700">
                  {DATE_STYLES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
                </select>
              </label>
              <span aria-hidden className="hidden h-6 w-px bg-slate-200 sm:block" />
              <button type="button" onClick={() => logout()}
                      className="inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-sm font-medium text-slate-600 hover:bg-slate-100 hover:text-slate-900">
                <Icon.logout className="h-4 w-4" />
                Log out
              </button>
            </div>
          )}
        </header>

        {/* Drop-down menu on small screens */}
        {menuOpen && (
          <div className="space-y-4 border-b border-slate-800 bg-slate-900 p-4 lg:hidden">
            {nav}
            {dataNote}
          </div>
        )}

        {/* Re-drawn when the date style changes, so every date on the page switches together. */}
        <main key={dates} className="mx-auto w-full max-w-7xl flex-1 px-4 py-8 lg:px-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

function Brand() {
  return (
    <div className="flex items-center gap-3">
      <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-brand-400 to-brand-700 text-white shadow-sm">
        <Icon.box className="h-5 w-5" />
      </span>
      <span className="leading-tight">
        <span className="block text-sm font-semibold text-white">Smart Inventory</span>
        <span className="block text-[11px] text-slate-400">Forecast &amp; reorder</span>
      </span>
    </div>
  );
}

function Avatar({ name }: { name: string }) {
  const initials = name.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]!.toUpperCase()).join("");
  return (
    <span aria-hidden className="flex h-8 w-8 items-center justify-center rounded-full bg-brand-100 text-xs font-semibold text-brand-700">
      {initials || "?"}
    </span>
  );
}
