/**
 * Screen language: English or Nepali. The English text is the key, so a string with no Nepali
 * translation yet simply stays in English and nothing breaks:
 *
 *   t("Log out")                                   -> "लग आउट"
 *   t("{n} units on hand", { n: fmtInt(5510) })    -> "5,510 एकाइ मौज्दातमा"
 *
 * The choice is remembered in this browser (localStorage), like the date style. Text that comes
 * from the server (error messages, product names) is not translated.
 */
import { NE } from "./ne";

export type Lang = "en" | "ne";

export const LANGUAGES: { value: Lang; label: string }[] = [
  { value: "en", label: "English" },
  { value: "ne", label: "नेपाली" },
];

const STORAGE_KEY = "smart-inventory.language";

function stored(): Lang | null {
  try {
    const value = localStorage.getItem(STORAGE_KEY);
    return LANGUAGES.some((l) => l.value === value) ? (value as Lang) : null;
  } catch {
    return null;                       // storage blocked: use the default
  }
}

let current: Lang = stored() ?? "en";
if (typeof document !== "undefined") document.documentElement.lang = current;

export const lang = (): Lang => current;

export function setLang(next: Lang, remember = true): void {
  current = next;
  if (typeof document !== "undefined") document.documentElement.lang = next;
  if (!remember) return;
  try {
    localStorage.setItem(STORAGE_KEY, next);
  } catch {
    // not remembered, but still used for this visit
  }
}

/** Translate `text` into the chosen language and fill in `{name}` placeholders. */
export function t(text: string, vars?: Record<string, string | number>): string {
  const translated = current === "ne" ? NE[text] ?? text : text;
  return vars ? translated.replace(/\{(\w+)\}/g, (whole, name: string) => (name in vars ? String(vars[name]) : whole)) : translated;
}
