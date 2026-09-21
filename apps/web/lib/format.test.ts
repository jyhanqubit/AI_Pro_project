// Pure rider/operator formatting logic. These run in CI (vitest, no browser) and pin the
// thresholds the UI shows riders; the components themselves are covered by typecheck + lint.
import { describe, expect, it } from "vitest";

import { availability, deltaClass, freeDocks, signed } from "./format";

describe("deltaClass", () => {
  it("treats |delta| <= 0.001 as flat so float noise never renders as a change", () => {
    expect(deltaClass(0)).toBe("flat");
    expect(deltaClass(0.001)).toBe("flat");
    expect(deltaClass(-0.001)).toBe("flat");
    expect(deltaClass(0.0011)).toBe("up");
    expect(deltaClass(-0.0011)).toBe("down");
  });
});

describe("signed", () => {
  it("prefixes positives with + and keeps the digits", () => {
    expect(signed(1.234)).toBe("+1.23");
    expect(signed(-1.234)).toBe("-1.23");
    expect(signed(0)).toBe("0.00");
    expect(signed(2, 0)).toBe("+2");
  });
});

describe("availability", () => {
  it("reports 'low' whenever the backend flags a shortage, regardless of surplus", () => {
    const a = availability(20, 5, 3);
    expect(a.level).toBe("low");
    expect(a.surplus).toBe(15);
  });

  it("grades the surplus (bikes - target) at the 6 and 2 thresholds", () => {
    expect(availability(16, 10, 0).level).toBe("plenty"); // surplus 6
    expect(availability(15, 10, 0).level).toBe("ok"); // surplus 5
    expect(availability(12, 10, 0).level).toBe("ok"); // surplus 2
    expect(availability(11, 10, 0).level).toBe("tight"); // surplus 1
    expect(availability(3, 10, 0).level).toBe("tight"); // negative surplus, no shortage flag
  });

  it("always carries a Korean label and one line of advice", () => {
    for (const [bikes, target, shortage] of [
      [20, 5, 3],
      [16, 10, 0],
      [12, 10, 0],
      [3, 10, 0],
    ] as const) {
      const a = availability(bikes, target, shortage);
      expect(a.label.length).toBeGreaterThan(0);
      expect(a.advice.length).toBeGreaterThan(0);
    }
  });
});

describe("freeDocks", () => {
  it("never goes negative when bikes exceed capacity (bad inventory data)", () => {
    expect(freeDocks(3, 10)).toBe(7);
    expect(freeDocks(12, 10)).toBe(0);
  });
});
