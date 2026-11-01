import { describe, expect, it } from "vitest";

import { fmtMoney } from "./format";

describe("rupee formatting", () => {
  it("uses South Asian grouping, and lakh/crore when compact", () => {
    expect(fmtMoney("8216.03")).toBe("Rs 8,216.03");
    expect(fmtMoney(1254259.14)).toBe("Rs 12,54,259.14");
    expect(fmtMoney(30200, true)).toBe("Rs 30,200.00");            // below 1 lakh: shown in full
    expect(fmtMoney(4610000, true)).toBe("Rs 46.1L");
    expect(fmtMoney(46000000, true)).toBe("Rs 4.6Cr");
    expect(fmtMoney(-2)).toBe("-Rs 2.00");
    expect(fmtMoney(null)).toBe("—");
  });
});
