import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

import { api } from "../api/client";
import { DEFAULT_RATE, setDisplayCurrency, type CurrencyCode, type CurrencyRate } from "../lib/currency";
import { useAuth } from "./AuthContext";

const STORAGE_KEY = "smart-inventory.currency";

interface CurrencyState {
  code: CurrencyCode;
  setCode: (code: CurrencyCode) => void;
  rate: CurrencyRate;
  reloadRate: () => void;
}

const CurrencyContext = createContext<CurrencyState | null>(null);

function storedCode(): CurrencyCode | null {
  try {
    const value = localStorage.getItem(STORAGE_KEY);
    return value === "NPR" || value === "USD" ? value : null;
  } catch {
    return null;                                     // storage blocked: fall back to the default
  }
}

/** Rupees by default (the app is for Nepali shops); the choice is remembered in this browser. */
export function CurrencyProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const [code, setCodeState] = useState<CurrencyCode>(() => storedCode() ?? "NPR");
  const [rate, setRate] = useState<CurrencyRate>(DEFAULT_RATE);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    if (!user) return;
    const controller = new AbortController();
    // If the saved rate cannot be loaded, the published default rate stays in use.
    api.get<CurrencyRate>("/settings/currency", undefined, controller.signal).then(setRate).catch(() => undefined);
    return () => controller.abort();
  }, [user, version]);

  const setCode = useCallback((next: CurrencyCode) => {
    setCodeState(next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // not remembered, but still switched for this visit
    }
  }, []);
  const reloadRate = useCallback(() => setVersion((v) => v + 1), []);

  setDisplayCurrency(code, rate.npr_per_usd);         // before the pages below format any amount
  return <CurrencyContext.Provider value={{ code, setCode, rate, reloadRate }}>{children}</CurrencyContext.Provider>;
}

/** Without a provider (page tests render pages on their own) amounts stay in dollars and cannot be switched. */
const DOLLARS_ONLY: CurrencyState = { code: "USD", setCode: () => undefined, rate: DEFAULT_RATE, reloadRate: () => undefined };

export function useCurrency(): CurrencyState {
  return useContext(CurrencyContext) ?? DOLLARS_ONLY;
}
