/**
 * Bikram Sambat (BS) dates for display and typing. The API always sends and receives AD dates (YYYY-MM-DD);
 * this file converts at the edges, using bs-calendar.json: for each BS year 2000-2090, the AD date of
 * 1 Baisakh and the 12 month lengths. That file is exported from the backend's converter
 * (backend/scripts/export_bs_calendar.py) and a backend test checks it, so browser and server always agree.
 * Dates outside the table are shown in AD.
 *
 * The chosen date style is remembered in this browser (localStorage) and read by lib/format.ts.
 */
import calendar from "./bs-calendar.json";

export type DateStyle = "bs" | "bs_np" | "ad" | "both";
export const DATE_STYLES: { value: DateStyle; label: string }[] = [
  { value: "bs", label: "BS (15 Kartik 2083)" },
  { value: "bs_np", label: "BS नेपाली (१५ कार्तिक २०८३)" },
  { value: "both", label: "BS and AD" },
  { value: "ad", label: "AD (1 Nov 2026)" },
];
// Same spellings as the backend (backend/app/services/bs_calendar.py).
export const BS_MONTHS = ["Baisakh", "Jestha", "Asar", "Shrawan", "Bhadra", "Asoj",
  "Kartik", "Mangsir", "Poush", "Magh", "Falgun", "Chaitra"];
const BS_MONTHS_NP = ["बैशाख", "जेठ", "असार", "साउन", "भदौ", "असोज", "कार्तिक", "मंसिर", "पुस", "माघ", "फागुन", "चैत"];
const NEPALI_DIGITS = "०१२३४५६७८९";
const toNepaliDigits = (text: string) => text.replace(/\d/g, (d) => NEPALI_DIGITS[Number(d)]);
const SHRAWAN = 4;
const STORAGE_KEY = "smart-inventory.date-style";

function stored(): DateStyle | null {
  try {
    const value = localStorage.getItem(STORAGE_KEY);
    return DATE_STYLES.some((s) => s.value === value) ? (value as DateStyle) : null;
  } catch {
    return null;                       // storage blocked: use the default
  }
}

let current: DateStyle = stored() ?? "bs";

export const dateStyle = (): DateStyle => current;

export function setDateStyle(style: DateStyle, remember = true): void {
  current = style;
  if (!remember) return;
  try {
    localStorage.setItem(STORAGE_KEY, style);
  } catch {
    // not remembered, but still used for this visit
  }
}

export interface BsDate { year: number; month: number; day: number }   // month: 1 = Baisakh ... 12 = Chaitra

const DAY_MS = 86_400_000;
const pad = (n: number) => String(n).padStart(2, "0");

function isoParts(iso: string): [number, number, number] | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  return match ? [Number(match[1]), Number(match[2]), Number(match[3])] : null;
}

/** Days since 1970-01-01 for an AD date (UTC arithmetic: no time-zone or daylight-saving surprises). */
function dayNumber(iso: string): number | null {
  const p = isoParts(iso);
  if (!p) return null;
  const time = Date.UTC(p[0], p[1] - 1, p[2]);
  const check = new Date(time);
  return check.getUTCMonth() === p[1] - 1 && check.getUTCDate() === p[2] ? time / DAY_MS : null;
}

const isoOfDay = (n: number) => new Date(n * DAY_MS).toISOString().slice(0, 10);

const YEARS = Object.entries(calendar.years)
  .map(([year, y]) => ({ year: Number(year), start: dayNumber(y.start)!, months: y.months }))
  .sort((a, b) => a.year - b.year);
const LAST = YEARS[YEARS.length - 1];
const TABLE_END = LAST.start + LAST.months.reduce((a, b) => a + b, 0);       // first day after the table

/** "2026-11-01" -> { year: 2083, month: 7, day: 15 }; null outside BS 2000-2090. */
export function adToBs(iso: string): BsDate | null {
  const n = dayNumber(iso);
  if (n === null || n < YEARS[0].start || n >= TABLE_END) return null;
  let i = YEARS.length - 1;
  while (YEARS[i].start > n) i--;
  let rest = n - YEARS[i].start;
  let month = 0;
  while (rest >= YEARS[i].months[month]) rest -= YEARS[i].months[month++];
  return { year: YEARS[i].year, month: month + 1, day: rest + 1 };
}

/** BS date -> "YYYY-MM-DD" (AD); null if that BS date does not exist (e.g. day 31 of a 30-day month). */
export function bsToAd(year: number, month: number, day: number): string | null {
  const y = YEARS.find((entry) => entry.year === year);
  if (!y || month < 1 || month > 12 || day < 1 || day > y.months[month - 1]) return null;
  return isoOfDay(y.start + y.months.slice(0, month - 1).reduce((a, b) => a + b, 0) + day - 1);
}

/** "2083-07-15", "2083/7/15" or "2083.07.15" (BS) -> AD "2026-11-01"; null if not a real BS date. */
export function parseBs(text: string): string | null {
  const match = /^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})$/.exec(text.trim());
  return match ? bsToAd(Number(match[1]), Number(match[2]), Number(match[3])) : null;
}

/** AD "2026-11-01" -> BS "2083-07-15" (for a BS text field); "" if it cannot be converted. */
export function bsInputValue(iso: string): string {
  const bs = iso ? adToBs(iso) : null;
  return bs ? `${bs.year}-${pad(bs.month)}-${pad(bs.day)}` : "";
}

/** "15 Kartik 2083", "15 Kar" (short), or in Nepali script "१५ कार्तिक २०८३"; null if it cannot be converted. */
export function formatBs(iso: string, { short = false, script = "en" }: { short?: boolean; script?: "en" | "np" } = {}): string | null {
  const bs = adToBs(iso);
  if (!bs) return null;
  if (script === "np") {
    const text = `${bs.day} ${BS_MONTHS_NP[bs.month - 1]}${short ? "" : ` ${bs.year}`}`;
    return toNepaliDigits(text);
  }
  const month = BS_MONTHS[bs.month - 1];
  return short ? `${bs.day} ${month.slice(0, 3)}` : `${bs.day} ${month} ${bs.year}`;
}

export interface FiscalYear { label: string; start: string; end: string }

/** The Nepali fiscal year (1 Shrawan to the end of Asar) containing an AD date, e.g. "2083/84". */
export function fiscalYear(iso: string): FiscalYear | null {
  const bs = adToBs(iso);
  if (!bs) return null;
  const startYear = bs.month >= SHRAWAN ? bs.year : bs.year - 1;
  const start = bsToAd(startYear, SHRAWAN, 1);
  const next = bsToAd(startYear + 1, SHRAWAN, 1);
  if (!start || !next) return null;
  return { label: `${startYear}/${pad((startYear + 1) % 100)}`, start, end: isoOfDay(dayNumber(next)! - 1) };
}
