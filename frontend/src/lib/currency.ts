/**
 * Display currency. Every amount in the database and API is in US dollars (the M5 data's own currency);
 * rupees are only a display conversion at one exchange rate that an admin sets in Settings.
 *
 * The selected currency is kept here (set by CurrencyProvider) so fmtMoney and the money inputs can use it
 * without every page passing it around. Without a provider (e.g. in unit tests) everything stays in dollars.
 */

export type CurrencyCode = "NPR" | "USD";

export interface CurrencyRate {
  npr_per_usd: number;
  rate_date: string | null;
  rate_source: string;
}

/** Used until the saved rate has loaded: NRB selling rate published for 29 Oct 2026. */
export const DEFAULT_RATE: CurrencyRate = {
  npr_per_usd: 152.66, rate_date: "2026-10-29", rate_source: "Nepal Rastra Bank (selling rate)",
};

let current: { code: CurrencyCode; perUsd: number } = { code: "USD", perUsd: 1 };

export function setDisplayCurrency(code: CurrencyCode, nprPerUsd: number): void {
  current = { code, perUsd: code === "NPR" ? nprPerUsd : 1 };
}

export const displayCurrency = (): CurrencyCode => current.code;
export const currencySymbol = (): string => (current.code === "NPR" ? "Rs" : "$");

/** US dollars -> selected currency. */
export const toDisplay = (usd: number): number => usd * current.perUsd;

/** Selected currency -> US dollars. */
export const toBase = (amount: number): number => amount / current.perUsd;

/** An API amount (dollars) as the text a money input should start with, in the selected currency. */
export function moneyToInput(usd: string | number | null | undefined): string {
  if (usd === null || usd === undefined || usd === "") return "";
  if (current.code === "USD") return String(usd);
  return toDisplay(Number(usd)).toFixed(2);
}

/** Text typed in a money input (selected currency) as the dollar string the API expects, to the cent. */
export function inputToMoney(text: string): string {
  const value = text.trim();
  if (!value || current.code === "USD") return value;
  return toBase(Number(value)).toFixed(2);
}
