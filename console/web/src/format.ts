// Pure formatting helpers (unit-tested in test/format.test.ts). No DOM access here.
import type { Scope, Tone } from "./types";

const ESC: Record<string, string> = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };

export function esc(value: unknown): string {
  return String(value ?? "").replace(/[&<>"']/g, (c) => ESC[c]);
}

/**
 * Wrap highlight ranges in <mark>. Offsets are [start, end) in characters (code points) of the raw message.
 * Text is escaped piece by piece, so markup in log messages can never become HTML.
 */
export function highlight(message: string, ranges: [number, number][]): string {
  const chars = Array.from(message);
  const clean = ranges
    .map(([s, e]) => [Math.max(0, Math.min(s, chars.length)), Math.max(0, Math.min(e, chars.length))] as [number, number])
    .filter(([s, e]) => e > s)
    .sort((a, b) => a[0] - b[0]);
  let out = "";
  let pos = 0;
  for (const [s, e] of clean) {
    if (s < pos) continue; // overlapping range: keep the first
    out += esc(chars.slice(pos, s).join("")) + "<mark>" + esc(chars.slice(s, e).join("")) + "</mark>";
    pos = e;
  }
  return out + esc(chars.slice(pos).join(""));
}

export function fmtInt(v: unknown): string {
  const n = Number(v);
  return v === null || v === undefined || !Number.isFinite(n) ? "—" : Math.round(n).toLocaleString("en-US");
}

export function fmtFloat(v: unknown): string {
  const n = Number(v);
  if (v === null || v === undefined || !Number.isFinite(n)) return "—";
  const digits = Math.abs(n) >= 100 ? 1 : 2;
  return n.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: digits });
}

/** Percent columns carry shares in [0, 1] (envelope `share`); values above 1 are taken as already in percent. */
export function fmtPercent(v: unknown): string {
  const n = Number(v);
  if (v === null || v === undefined || !Number.isFinite(n)) return "—";
  const pct = Math.abs(n) <= 1 ? n * 100 : n;
  return `${pct.toLocaleString("en-US", { maximumFractionDigits: pct < 10 ? 1 : 0 })}%`;
}

/** change_pct → { arrow, text, dir }. null means "no previous period". */
export function fmtChange(v: unknown): { arrow: string; text: string; dir: "up" | "down" | "flat" | "new" } {
  if (v === null || v === undefined) return { arrow: "", text: "new", dir: "new" };
  const n = Number(v);
  if (!Number.isFinite(n)) return { arrow: "", text: "—", dir: "flat" };
  if (n === 0) return { arrow: "", text: "0%", dir: "flat" };
  const abs = Math.abs(n);
  return { arrow: n > 0 ? "▲" : "▼", text: `${abs.toLocaleString("en-US", { maximumFractionDigits: abs < 10 ? 1 : 0 })}%`, dir: n > 0 ? "up" : "down" };
}

/** "2005-06-14T09:05:41.100000" → "09:05:41". Falls back to the raw string. */
export function shortTime(ts: string): string {
  const m = /T?(\d{2}:\d{2}:\d{2})/.exec(ts);
  return m ? m[1] : ts;
}

/** "2005-06-14T09:05:41.100000" → "2005-06-14 09:05:41.100". */
export function fullTime(ts: string): string {
  return ts.replace("T", " ").replace(/(\.\d{3})\d+$/, "$1");
}

/** "2005-06-14T09:02:03" → "14 Jun 2005 09:02"; "2005-06-01" → "1 Jun 2005". */
export function niceDate(ts: string | null | undefined): string {
  if (!ts) return "";
  const m = /^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}:\d{2}))?/.exec(ts);
  if (!m) return ts;
  const month = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][Number(m[2]) - 1];
  return `${Number(m[3])} ${month} ${m[1]}${m[4] && m[4] !== "00:00" ? " " + m[4] : ""}`;
}

/** BGL node "R23-M0-N4-C:J12-U11" → "N4·J12"; anything else is returned as-is (the full value goes in a tooltip). */
export function shortSource(source: string): string {
  const bgl = /^R\d+-M\d+-(N[0-9A-F]+)-C:(J\d+)-U\d+$/.exec(source);
  if (bgl) return `${bgl[1]}·${bgl[2]}`;
  return source.length > 16 ? source.slice(0, 15) + "…" : source;
}

export function toneForLevel(level: string): Tone {
  const l = level.toUpperCase();
  if (["FATAL", "FAILURE", "CRITICAL"].includes(l)) return "critical";
  if (["ERROR", "SEVERE"].includes(l)) return "error";
  if (l === "WARNING" || l === "WARN") return "warning";
  return "info";
}

/** Stable colour per team name (hue from a string hash; fixed lightness/chroma so all badges sit together). */
export function teamColor(team: string): string {
  let h = 0;
  for (const ch of team) h = (h * 31 + ch.codePointAt(0)!) >>> 0;
  return `oklch(0.74 0.11 ${h % 360})`;
}

/** Header scope chip: "bgl · 1 Jun 2005 → 30 Jun 2005 · episodes · gap 10m". */
export function scopeLabel(scope: Scope | null | undefined): string {
  if (!scope) return "";
  const parts: string[] = [];
  if (scope.dataset) parts.push(String(scope.dataset));
  if (scope.from || scope.to) parts.push(`${niceDate(scope.from)} → ${niceDate(scope.to)}`);
  if (scope.unit) parts.push(String(scope.unit));
  if (scope.episode_gap) parts.push(`gap ${scope.episode_gap}`);
  return parts.join(" · ");
}

/** stability_top3 in [0,1] → "top 3 in 9 of 10 weightings". */
export function stabilityText(share: number): string {
  return `top 3 in ${Math.round(share * 10)} of 10 weightings`;
}

/** "4 / 316" style counter for the evidence corner. */
export function countLabel(returned: number, total: number | null): string {
  return total === null || total === undefined ? `${fmtInt(returned)} shown` : `${fmtInt(returned)} / ${fmtInt(total)}`;
}

/** Claim indicator state for the header shield. */
export function claimsState(claims: { backed: number; unbacked: number; mismatched: number; flagged: number } | null | undefined): {
  state: "unchecked" | "ok" | "warn";
  text: string;
} {
  if (!claims) return { state: "unchecked", text: "not checked" };
  const unbacked = claims.unbacked + claims.mismatched;
  if (unbacked === 0 && claims.flagged === 0) return { state: "ok", text: "all claims backed" };
  const parts: string[] = [];
  if (claims.flagged) parts.push(`${claims.flagged} flagged`);
  if (unbacked) parts.push(`${unbacked} unbacked`);
  return { state: "warn", text: parts.join(" / ") };
}
