import { describe, expect, it } from "vitest";
import {
  claimsState,
  countLabel,
  esc,
  fmtChange,
  fmtFloat,
  fmtInt,
  fmtPercent,
  highlight,
  scopeLabel,
  shortSource,
  shortTime,
  stabilityText,
} from "../web/src/format";

describe("highlight", () => {
  it("wraps character ranges in <mark>", () => {
    expect(highlight("data TLB error interrupt", [[5, 8]])).toBe("data <mark>TLB</mark> error interrupt");
  });
  it("escapes HTML in the message before inserting marks", () => {
    const out = highlight('<img src=x onerror="alert(1)"> TLB', [[31, 34]]);
    expect(out).not.toContain("<img");
    expect(out).toContain("&lt;img src=x onerror=&quot;alert(1)&quot;&gt;");
    expect(out).toContain("<mark>TLB</mark>");
  });
  it("escapes text inside a highlighted range", () => {
    expect(highlight("a <b> c", [[2, 5]])).toBe("a <mark>&lt;b&gt;</mark> c");
  });
  it("uses code-point offsets, clamps out-of-range and skips overlaps", () => {
    expect(highlight("é😀 ab", [[3, 5]])).toBe("é😀 <mark>ab</mark>");
    expect(highlight("abc", [[1, 99], [0, 2]])).toBe("<mark>ab</mark>c");
    expect(highlight("abc", [[2, 1]])).toBe("abc");
  });
});

describe("number formatting", () => {
  it("formats ints with thousands separators", () => {
    expect(fmtInt(4747963)).toBe("4,747,963");
    expect(fmtInt(null)).toBe("—");
  });
  it("formats floats with 1–2 decimals", () => {
    expect(fmtFloat(0.2477829)).toBe("0.25");
    expect(fmtFloat(86.5)).toBe("86.5");
    expect(fmtFloat(121.14)).toBe("121.1");
  });
  it("formats shares as percent", () => {
    expect(fmtPercent(0.684)).toBe("68%");
    expect(fmtPercent(0.052)).toBe("5.2%");
  });
  it("formats change with arrows", () => {
    expect(fmtChange(121.1)).toEqual({ arrow: "▲", text: "121%", dir: "up" });
    expect(fmtChange(-5.9)).toEqual({ arrow: "▼", text: "5.9%", dir: "down" });
    expect(fmtChange(null).dir).toBe("new");
  });
});

describe("labels", () => {
  it("shortens times and BGL node ids", () => {
    expect(shortTime("2005-06-14T09:05:41.100000")).toBe("09:05:41");
    expect(shortSource("R23-M0-N4-C:J12-U11")).toBe("N4·J12");
    expect(shortSource("nova-api")).toBe("nova-api");
  });
  it("builds the scope chip", () => {
    expect(scopeLabel({ dataset: "bgl", from: "2005-06-01", to: "2005-06-30", unit: "episodes", episode_gap: "10m" })).toBe(
      "bgl · 1 Jun 2005 → 30 Jun 2005 · episodes · gap 10m",
    );
  });
  it("counts, stability and claims", () => {
    expect(countLabel(4, 316)).toBe("4 / 316");
    expect(countLabel(3, null)).toBe("3 shown");
    expect(stabilityText(0.9)).toBe("top 3 in 9 of 10 weightings");
    expect(claimsState(null).state).toBe("unchecked");
    expect(claimsState({ backed: 3, unbacked: 0, mismatched: 0, flagged: 0 })).toEqual({ state: "ok", text: "all claims backed" });
    expect(claimsState({ backed: 3, unbacked: 1, mismatched: 1, flagged: 1 })).toEqual({ state: "warn", text: "1 flagged / 2 unbacked" });
  });
  it("escapes", () => {
    expect(esc(`<a href="x">'&`)).toBe("&lt;a href=&quot;x&quot;&gt;&#39;&amp;");
  });
});
