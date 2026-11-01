import { afterEach, describe, expect, it } from "vitest";

import calendar from "./bs-calendar.json";
import { fmtDate, fmtDateTime, fmtShortDate } from "./format";
import { adToBs, bsInputValue, bsToAd, fiscalYear, formatBs, parseBs, setDateStyle } from "./nepaliDate";

afterEach(() => setDateStyle("ad", false));

describe("BS conversion", () => {
  it("converts every day of the backend's table there and back", () => {
    // bs-calendar.json is exported from the backend's converter; a backend test checks it is up to date.
    let checked = 0;
    for (const [year, y] of Object.entries(calendar.years)) {
      let iso = y.start;
      y.months.forEach((length, m) => {
        for (let day = 1; day <= length; day++) {
          const ad = bsToAd(Number(year), m + 1, day);
          if (day === 1 && ad !== iso) throw new Error(`${year}-${m + 1}: ${ad} != ${iso}`);
          expect(adToBs(ad!)).toEqual({ year: Number(year), month: m + 1, day });
          checked++;
        }
        iso = new Date(Date.parse(`${iso}T00:00:00Z`) + length * 86_400_000).toISOString().slice(0, 10);
      });
    }
    expect(checked).toBeGreaterThan(33_000);                      // 91 years of days
  });

  it("converts known dates both ways", () => {
    expect(adToBs("2026-04-14")).toEqual({ year: 2083, month: 1, day: 1 });       // Nepali New Year 2083
    expect(adToBs("2026-11-01")).toEqual({ year: 2083, month: 7, day: 15 });
    expect(bsToAd(2083, 7, 15)).toBe("2026-11-01");
    expect(bsInputValue("2026-11-01")).toBe("2083-07-15");
  });

  it("reads typed BS dates and refuses dates that do not exist", () => {
    expect(parseBs("2083-07-15")).toBe("2026-11-01");
    expect(parseBs(" 2083/7/15 ")).toBe("2026-11-01");
    expect(parseBs("2083.07.15")).toBe("2026-11-01");
    expect(parseBs("2083-07-31")).toBeNull();          // Kartik 2083 has 30 days (same rule as the backend test)
    expect(parseBs("2083-13-01")).toBeNull();
    expect(parseBs("15/07/2083")).toBeNull();
    expect(parseBs("")).toBeNull();
  });

  it("finds the Nepali fiscal year, 1 Shrawan to the end of Asar", () => {
    expect(fiscalYear("2026-11-01")).toEqual({ label: "2083/84", start: "2026-07-17", end: "2027-07-16" });
    expect(fiscalYear("2026-07-16")?.label).toBe("2082/83");     // the day before 1 Shrawan 2083
    expect(fiscalYear("2026-07-17")?.label).toBe("2083/84");
  });
});

describe("date display styles", () => {
  it("shows BS by default style, in Nepali script, both, or AD", () => {
    setDateStyle("bs", false);
    expect(fmtDate("2026-11-01")).toBe("15 Kartik 2083");
    expect(fmtShortDate("2026-11-01")).toBe("15 Kar");
    setDateStyle("bs_np", false);
    expect(fmtDate("2026-11-01")).toBe("१५ कार्तिक २०८३");
    setDateStyle("both", false);
    expect(fmtDate("2026-11-01")).toBe("15 Kartik 2083 (1 Nov 2026)");
    setDateStyle("ad", false);
    expect(fmtDate("2026-11-01")).toBe("1 Nov 2026");
    expect(fmtShortDate("2026-11-01")).toBe("1 Nov");
  });

  it("falls back to AD outside the supported years, and shows times with BS dates", () => {
    setDateStyle("bs", false);
    expect(fmtDate("1900-01-01")).toBe("1 Jan 1900");
    expect(formatBs("not a date")).toBeNull();
    expect(fmtDateTime(new Date(2026, 10, 1, 9, 5).toISOString())).toBe("15 Kar, 09:05");
  });
});
