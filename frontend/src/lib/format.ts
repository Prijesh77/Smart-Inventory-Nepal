/** Number and date formatting used across pages, so every page shows values the same way. */
import { dateStyle, formatBs } from "./nepaliDate";

const integer = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
const oneDecimal = new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 });
// Rupees use South Asian grouping: Rs 1,23,456.00, and lakh (L) / crore (Cr) when compact.
const rupees = new Intl.NumberFormat("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const compactRupees = new Intl.NumberFormat("en-IN", { notation: "compact", maximumFractionDigits: 1 });

type Num = number | string | null | undefined;

function toNumber(value: Num): number | null {
  if (value === null || value === undefined || value === "") return null;
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n : null;
}

export const DASH = "—";

export function fmtInt(value: Num): string {
  const n = toNumber(value);
  return n === null ? DASH : integer.format(n);
}

export function fmtDecimal(value: Num): string {
  const n = toNumber(value);
  return n === null ? DASH : oneDecimal.format(n);
}

/** An amount in Nepalese rupees (every amount in the app is stored in NPR). */
export function fmtMoney(value: Num, compact = false): string {
  const n = toNumber(value);
  if (n === null) return DASH;
  const text = compact && Math.abs(n) >= 100_000 ? compactRupees.format(Math.abs(n)) : rupees.format(Math.abs(n));
  return `${n < 0 ? "-" : ""}Rs ${text}`;
}

/** 0.0523 -> "+5.2%" (signed) or "5.2%". */
export function fmtPct(value: Num, signed = false): string {
  const n = toNumber(value);
  if (n === null) return DASH;
  const text = `${oneDecimal.format(Math.abs(n * 100))}%`;
  if (!signed) return n < 0 ? `-${text}` : text;
  return n > 0 ? `+${text}` : n < 0 ? `-${text}` : text;
}

function adDate(value: string, withYear = true): string {
  const [y, m, d] = value.slice(0, 10).split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString("en-GB", {
    day: "numeric", month: "short", ...(withYear ? { year: "numeric" } : {}), timeZone: "UTC" });
}

/** A date in the style chosen in the header (lib/nepaliDate.ts): "15 Kartik 2083", "१५ कार्तिक २०८३",
 * "15 Kartik 2083 (1 Nov 2026)" or "1 Nov 2026". Dates the BS converter cannot handle are shown in AD. */
export function fmtDate(value: string | null | undefined): string {
  if (!value) return DASH;
  const style = dateStyle();
  const ad = adDate(value);
  if (style === "ad") return ad;
  const bs = formatBs(value.slice(0, 10), { script: style === "bs_np" ? "np" : "en" });
  if (!bs) return ad;
  return style === "both" ? `${bs} (${ad})` : bs;
}

/** Day and month only, for chart axes: "15 Kar", "१५ कार्तिक" or "1 Nov". */
export function fmtShortDate(value: string): string {
  const style = dateStyle();
  const bs = style === "ad" ? null : formatBs(value.slice(0, 10), { short: true, script: style === "bs_np" ? "np" : "en" });
  return bs ?? adDate(value, false);
}

/** A moment (e.g. when an import ran) as date and local time: "15 Kartik, 10:26". */
export function fmtDateTime(value: string | null | undefined): string {
  if (!value) return DASH;
  const moment = new Date(value);
  const time = moment.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
  const local = `${moment.getFullYear()}-${String(moment.getMonth() + 1).padStart(2, "0")}-${String(moment.getDate()).padStart(2, "0")}`;
  return `${fmtShortDate(local)}, ${time}`;
}

/** "critical_stockout_risk" -> "Critical stockout risk" */
export function humanize(value: string): string {
  const text = value.replace(/_/g, " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}
