/// <reference types="vite/client" />
import { afterEach, describe, expect, it } from "vitest";

import { lang, setLang, t } from "./i18n";
import { NE } from "./ne";

afterEach(() => setLang("en", false));

/** The text of every source file under src, except tests. */
const SOURCES = Object.entries(
  import.meta.glob<string>("../**/*.{ts,tsx}", { query: "?raw", import: "default", eager: true }),
).filter(([path]) => !/\.test\.tsx?$/.test(path)).map(([, text]) => text);

describe("t", () => {
  it("returns English by default and Nepali when chosen", () => {
    expect(lang()).toBe("en");
    expect(t("Log out")).toBe("Log out");
    setLang("ne", false);
    expect(t("Log out")).toBe("लग आउट");
  });

  it("fills in placeholders in both languages and leaves unknown ones alone", () => {
    expect(t("{n} units on hand", { n: "5,510" })).toBe("5,510 units on hand");
    expect(t("{a} and {b}", { a: 1 })).toBe("1 and {b}");
    setLang("ne", false);
    expect(t("{n} units on hand", { n: "5,510" })).toBe("5,510 एकाइ मौज्दातमा");
  });

  it("falls back to English for text with no translation yet", () => {
    setLang("ne", false);
    expect(t("Something not translated")).toBe("Something not translated");
  });
});

describe("Nepali dictionary", () => {
  it("has an entry for every text passed to t(\"...\") in the app", () => {
    const missing = new Set<string>();
    expect(SOURCES.length).toBeGreaterThan(40);
    for (const source of SOURCES) {
      for (const match of source.matchAll(/\bt\("((?:[^"\\]|\\.)+)"/g)) {
        const text = JSON.parse(`"${match[1]}"`) as string;
        if (!(text in NE)) missing.add(text);
      }
    }
    expect([...missing]).toEqual([]);
  });

  it("keeps the same placeholders as the English text", () => {
    const names = (text: string) => [...text.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort();
    const wrong = Object.entries(NE).filter(([en, ne]) => names(en).join() !== names(ne).join()).map(([en]) => en);
    expect(wrong).toEqual([]);
  });
});
