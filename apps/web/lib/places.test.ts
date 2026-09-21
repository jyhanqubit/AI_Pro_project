// Zone / station -> human place names. Unknown ids must degrade to a readable code, never crash.
import { describe, expect, it } from "vitest";

import { stationLabel, stationPlace, zoneLabel, zoneNameKo, zonePlace } from "./places";

describe("zonePlace", () => {
  it("maps a known H3 zone to its Korean and English names", () => {
    const p = zonePlace("892a1072e7bffff");
    expect(p.ko).toBe("그로브 스트리트");
    expect(p.en).toBe("Grove St PATH");
    expect(p.area).toBe("저지시티");
  });

  it("falls back to the short code for an unknown zone", () => {
    const p = zonePlace("892a1072ffffff9");
    expect(p.ko).toBe("…fffff9"); // last six characters
    expect(p.en).toBe("…fffff9");
    expect(p.area).toBe("");
  });

  it("handles an empty id without throwing", () => {
    expect(zonePlace("").ko).toBe("—");
  });
});

describe("labels", () => {
  it("shows 'ko (en)' for a known zone and just the code when ko === en", () => {
    expect(zoneLabel("892a1072e7bffff")).toBe("그로브 스트리트 (Grove St PATH)");
    expect(zoneLabel("nope")).toBe("…nope");
    expect(zoneNameKo("892a107216bffff")).toBe("호보켄 터미널");
  });

  it("maps stations, including the multi-region ones, and echoes unknown ids", () => {
    expect(stationLabel("JC_GROVE")).toBe("그로브 스트리트 (Grove St PATH)");
    expect(stationPlace("NY_WALL").area).toBe("맨해튼");
    expect(stationLabel("XX_UNKNOWN")).toBe("XX_UNKNOWN");
  });
});
