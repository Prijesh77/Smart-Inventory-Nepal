/** Number and date formatting used across pages, so every page shows values the same way. */

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

/** "2016-05-22" -> "22 May 2016" without time-zone surprises. */
export function fmtDate(value: string | null | undefined): string {
  if (!value) return DASH;
  const [y, m, d] = value.slice(0, 10).split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString("en-GB", {
    day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
}

export function fmtShortDate(value: string): string {
  const [y, m, d] = value.slice(0, 10).split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString("en-GB", { day: "numeric", month: "short",
    timeZone: "UTC" });
}

export function fmtDateTime(value: string | null | undefined): string {
  if (!value) return DASH;
  return new Date(value).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

/** "critical_stockout_risk" -> "Critical stockout risk" */
export function humanize(value: string): string {
  const text = value.replace(/_/g, " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}
