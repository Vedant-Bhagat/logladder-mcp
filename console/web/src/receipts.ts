// Receipts arrive inside events (evidence.receipt, explainer.receipts); the console never asks the backend for them.
import { esc, fmtInt, niceDate } from "./format";
import { icon } from "./icons";
import type { ReceiptRef } from "./types";

export class ReceiptStore {
  private byId = new Map<string, ReceiptRef>();
  add(r: ReceiptRef | undefined | null): void {
    if (r?.receipt_id) this.byId.set(r.receipt_id, r);
  }
  get(id: string): ReceiptRef | undefined {
    return this.byId.get(id);
  }
  has(id: string): boolean {
    return this.byId.has(id);
  }
  ids(): Set<string> {
    return new Set(this.byId.keys());
  }
  clear(): void {
    this.byId.clear();
  }
}

function filters(f: Record<string, unknown> | null | undefined): string {
  const entries = Object.entries(f ?? {}).filter(([, v]) => v !== null && v !== undefined && v !== "");
  return entries.length ? entries.map(([k, v]) => `<span class="kv">${esc(k)} = ${esc(typeof v === "object" ? JSON.stringify(v) : v)}</span>`).join("") : "none";
}

const SQL_KW = /\b(SELECT|FROM|WHERE|AND|OR|NOT|GROUP BY|ORDER BY|JOIN|LEFT JOIN|USING|ON|BETWEEN|AS|DESC|ASC|LIMIT|WITH|COUNT|DISTINCT|FILTER|OVER|PARTITION BY|CASE|WHEN|THEN|ELSE|END|IN|IS|NULL|TIMESTAMP|INTERVAL|UNION|ALL)\b/gi;

/** Escape first, then colour keywords (keywords are plain ASCII words, so escaping can't be broken). */
export function sqlHtml(sql: string): string {
  return esc(sql).replace(SQL_KW, '<span class="kw">$1</span>');
}

export function receiptHtml(r: ReceiptRef): string {
  const s = r.scope ?? {};
  const rows: [string, string][] = [
    ["tool", `<code>${esc(r.tool)}</code>`],
    ["dataset", esc(s.dataset ?? "—")],
    ["window", s.from || s.to ? `${esc(niceDate(s.from))} → ${esc(niceDate(s.to))}` : "full span"],
    ["filters", filters(s.filters as Record<string, unknown>)],
  ];
  if (s.unit) rows.push(["unit", esc(s.unit)]);
  if (s.episode_gap) rows.push(["episode gap", esc(s.episode_gap)]);
  if (s.group_by) rows.push(["group by", esc(s.group_by)]);
  if (s.bucket) rows.push(["bucket", esc(s.bucket)]);
  const result = `${fmtInt(r.returned)} returned${r.total_matches === null ? "" : ` of ${fmtInt(r.total_matches)}`}${r.truncated ? ' · <span class="trunc">truncated</span>' : ""} · ${fmtInt(r.runtime_ms)} ms`;
  rows.push(["result", result]);
  const sql = (r.sql ?? [])
    .map(
      (q, i) => `<div class="sql">
  <div class="sql-head"><span>statement ${i + 1}</span><wa-copy-button value="${esc(q)}" copy-label="Copy SQL" success-label="Copied"></wa-copy-button></div>
  <pre>${sqlHtml(q)}</pre>
</div>`,
    )
    .join("");
  return `<dl class="rcpt">${rows.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join("")}</dl>
<h4>${icon("receipt")} SQL that produced this evidence</h4>${sql || '<p class="muted">No SQL recorded.</p>'}`;
}
