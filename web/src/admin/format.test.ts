import { describe, expect, it } from "vitest";
import { rangeQuery } from "./api";
import { addDays, daysBetween, fmtAxis, fmtPct, parseSsh, fmtTime, niceMax, presetRange, shorten, vnDay } from "./format";

describe("admin format helpers", () => {
  it("uses Vietnam days whatever the browser's zone", () => {
    expect(vnDay(new Date("2026-11-25T18:30:00Z"))).toBe("2026-11-26");
    expect(vnDay(new Date("2026-11-25T16:59:00Z"))).toBe("2026-11-25");
    expect(fmtTime("2026-11-25T18:30:00+00:00")).toBe("26/11 01:30");
  });

  it("builds date ranges and fills every day", () => {
    const now = new Date("2026-11-26T03:00:00Z");
    expect(presetRange("today", now)).toEqual({ since: "2026-11-26", until: "2026-11-26" });
    expect(presetRange("7d", now)).toEqual({ since: "2026-11-20", until: "2026-11-26" });
    expect(presetRange("all", now)).toEqual({ since: null, until: null });
    expect(addDays("2026-11-30", 1)).toBe("2026-12-01");
    expect(daysBetween("2026-11-29", "2026-12-02")).toEqual(["2026-11-29", "2026-11-30", "2026-12-01", "2026-12-02"]);
  });

  it("writes query strings without empty filters", () => {
    expect(rangeQuery({ since: "2026-11-26", until: null }, { route: "rag", rating: "", limit: 50 }))
      .toBe("?since=2026-11-26&route=rag&limit=50");
    expect(rangeQuery({ since: null, until: null })).toBe("");
  });

  it("reads a GPU's SSH address from what the provider shows", () => {
    expect(parseSsh("ssh -p 41413 root@122.117.118.68 -L 8080:localhost:8080")).toEqual({ host: "122.117.118.68", port: 41413 });
    expect(parseSsh("ssh -i ~/.ssh/k -p 35411 root@ssh4.vast.ai")).toEqual({ host: "ssh4.vast.ai", port: 35411 });
    expect(parseSsh("root@1.2.3.4:2222")).toEqual({ host: "1.2.3.4", port: 2222 });
    expect(parseSsh("1.2.3.4 2222")).toEqual({ host: "1.2.3.4", port: 2222 });
    expect(parseSsh("1.2.3.4")).toEqual({ host: "1.2.3.4", port: null });
    expect(parseSsh("   ")).toBeNull();
  });

  it("formats numbers for cards and axes", () => {
    expect(niceMax(0)).toBe(1);
    expect(niceMax(7)).toBe(10);
    expect(niceMax(13)).toBe(20);
    expect(niceMax(41)).toBe(50);
    expect(fmtPct(0.666)).toBe("67%");
    expect(fmtPct(null)).toBe("–");
    expect(shorten("abcdef", 4)).toBe("abc…");
    expect([fmtAxis(0), fmtAxis(0.01), fmtAxis(0.02), fmtAxis(2.5), fmtAxis(50)]).toEqual(["0", "0.01", "0.02", "2.5", "50"]);
  });
});
