// Renders the four evidence kinds into HTML. Every value is escaped; tolerant of unexpected optional fields.
import { esc, fmtChange, fmtFloat, fmtInt, fmtPercent, fullTime, highlight, shortSource, shortTime, stabilityText, teamColor, toneForLevel } from "./format";
import { icon, levelIcon } from "./icons";
import type { Annotation, EvidencePayload, Factor, LinesBody, RisksBody, TableBody, TableColumn, TrendBody } from "./types";

const GROUP_LABEL: Record<string, string> = { matches: "matches", before: "before", anchor: "anchor", after: "after", trace: "trace" };

export function teamBadge(team: unknown): string {
  const name = String(team ?? "");
  if (!name) return "—";
  return `<span class="team" title="${esc(name)}"><i style="background:${teamColor(name)}"></i>${esc(name)}</span>`;
}

function annotationTag(a: Annotation): string {
  return `<span class="note t-${a.tone}" title="${esc(a.label)}">${esc(a.label)}</span>`;
}

function renderLines(body: LinesBody, annotations: Annotation[]): string {
  const notes = new Map<number, Annotation[]>();
  for (const a of annotations ?? []) notes.set(a.line_id, [...(notes.get(a.line_id) ?? []), a]);
  let html = "";
  for (const group of body.groups ?? []) {
    html += `<div class="grp"><span>${esc(GROUP_LABEL[group.label] ?? group.label)}</span><b>${fmtInt(group.lines?.length ?? 0)}</b></div>`;
    for (const l of group.lines ?? []) {
      const tone = l.tone ?? toneForLevel(l.level ?? "");
      const tags = (notes.get(l.id) ?? []).map(annotationTag).join("");
      const rep = l.repeat_count > 1 ? `<span class="rep" title="${fmtInt(l.repeat_count)} lines of this message collapsed">× ${fmtInt(l.repeat_count)}</span>` : "";
      html += `<div class="ln${l.is_anchor ? " anchor" : ""}" tabindex="0" role="button" aria-expanded="false" data-line="${l.id}">
  <span class="stripe t-${tone}"></span>${levelIcon(tone, esc(l.level))}
  <span class="tm" title="${esc(fullTime(l.ts))}">${esc(shortTime(l.ts))}</span>
  <span class="src" title="${esc(l.source)}">${esc(shortSource(l.source))}</span>
  <span class="msg">${highlight(l.message ?? "", l.highlights ?? [])}</span>
  <span class="tags">${rep}${tags}</span>
  <div class="more" hidden>
    <div class="full">${highlight(l.message ?? "", l.highlights ?? [])}</div>
    <dl><dt>time</dt><dd>${esc(fullTime(l.ts))}</dd><dt>source</dt><dd>${esc(l.source)}</dd><dt>component</dt><dd>${esc(l.component ?? "—")}</dd><dt>level</dt><dd>${esc(l.level)}</dd><dt>line</dt><dd>#${esc(l.id)} · ${esc(l.dataset)}</dd>${l.repeat_count > 1 ? `<dt>repeats</dt><dd>${fmtInt(l.repeat_count)} lines</dd>` : ""}</dl>
  </div>
</div>`;
    }
  }
  return `<div class="lines">${html}</div>`;
}

function cell(col: TableColumn, v: unknown): string {
  switch (col.type) {
    case "int":
      return `<td class="n">${fmtInt(v)}</td>`;
    case "float":
      return `<td class="n">${fmtFloat(v)}</td>`;
    case "percent":
      return `<td class="n">${fmtPercent(v)}</td>`;
    case "change": {
      const c = fmtChange(v);
      return `<td class="n chg ${c.dir}">${c.arrow ? `<span aria-hidden="true">${c.arrow}</span> ` : ""}${esc(c.text)}</td>`;
    }
    case "team":
      return `<td>${teamBadge(v)}</td>`;
    case "level": {
      const level = String(v ?? "");
      return `<td class="c">${level ? levelIcon(toneForLevel(level), esc(level)) : "—"}</td>`;
    }
    default:
      return `<td class="txt" title="${esc(v)}">${esc(v ?? "—")}</td>`;
  }
}

function renderTable(body: TableBody): string {
  const cols = body.columns ?? [];
  const head = cols.map((c) => `<th class="${["int", "float", "percent", "change"].includes(c.type) ? "n" : ""}">${esc(c.label)}</th>`).join("");
  const rows = (body.rows ?? []).map((r) => `<tr>${cols.map((c) => cell(c, r[c.key])).join("")}</tr>`).join("");
  const total = body.total_row ? `<tfoot><tr>${cols.map((c) => cell(c, body.total_row![c.key])).join("")}</tr></tfoot>` : "";
  return `<div class="table-wrap"><table class="tbl"><thead><tr>${head}</tr></thead><tbody>${rows}</tbody>${total}</table></div>`;
}

const SERIES_COLORS = ["#8B78FF", "#4FB3D9", "#E6B53A", "#FF6B5E", "#3CC47C", "#F08A4B", "#D77BDB", "#9AA1AB"];

function niceMax(v: number): number {
  if (v <= 0) return 1;
  const p = 10 ** Math.floor(Math.log10(v));
  const n = v / p;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10) * p;
}

function tickLabel(t: string, bucket: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(t);
  if (!m) return t;
  const month = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][Number(m[2]) - 1];
  return bucket === "week" || bucket === "day" ? `${Number(m[3])} ${month}` : t;
}

export interface TrendGeometry {
  times: string[];
  x: (i: number) => number;
  W: number;
  H: number;
}

/** Draws the chart at the given pixel width. Hover tooltip wiring lives in main.ts (it needs the DOM). */
export function renderTrend(body: TrendBody, width: number): { svg: string; geo: TrendGeometry } {
  const series = (body.series ?? []).slice(0, 8);
  const times = [...new Set(series.flatMap((s) => s.points.map((p) => p.t)))].sort();
  const W = Math.max(260, Math.round(width));
  const H = Math.max(160, Math.min(320, Math.round(W * 0.48)));
  const L = 40, R = 12, T = 12, B = 24;
  const values = series.flatMap((s) => s.points.map((p) => p.v)).filter((v): v is number => typeof v === "number");
  const tick = niceMax(Math.max(0, ...values) / 4);
  const max = Math.max(tick, Math.ceil(Math.max(0, ...values) / tick) * tick);
  const ticks = Math.round(max / tick);
  const x = (i: number) => (times.length <= 1 ? L + (W - L - R) / 2 : L + (i * (W - L - R)) / (times.length - 1));
  const y = (v: number) => T + (H - T - B) * (1 - v / max);
  let g = "";
  for (let k = 0; k <= ticks; k++) {
    const v = tick * k;
    g += `<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}" class="grid"/><text x="${L - 6}" y="${y(v) + 3}" class="axis" text-anchor="end">${esc(fmtFloat(v))}</text>`;
  }
  const step = Math.max(1, Math.ceil(times.length / Math.floor((W - L - R) / 56)));
  times.forEach((t, i) => {
    if (i % step === 0 || i === times.length - 1) g += `<text x="${x(i)}" y="${H - 6}" class="axis" text-anchor="middle">${esc(tickLabel(t, body.bucket))}</text>`;
  });
  series.forEach((s, si) => {
    const color = SERIES_COLORS[si % SERIES_COLORS.length];
    const byT = new Map(s.points.map((p) => [p.t, p.v]));
    let d = "";
    let pen = false;
    let last: [number, number] | null = null;
    times.forEach((t, i) => {
      const v = byT.get(t);
      if (typeof v !== "number") {
        pen = false; // null = gap
        return;
      }
      d += `${pen ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)} `;
      pen = true;
      last = [x(i), y(v)];
    });
    g += `<path d="${d}" fill="none" stroke="${color}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>`;
    if (last) g += `<circle cx="${(last as [number, number])[0]}" cy="${(last as [number, number])[1]}" r="3.5" fill="${color}"/>`;
  });
  g += `<line class="cross" x1="0" x2="0" y1="${T}" y2="${H - B}" visibility="hidden"/>`;
  const legend = series
    .map((s, si) => `<span class="key"><i style="background:${SERIES_COLORS[si % SERIES_COLORS.length]}"></i>${esc(s.name)}</span>`)
    .join("");
  const svg = `<div class="legend">${legend}<span class="unit">${esc(body.unit_label)}</span></div>
<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="${esc(body.unit_label)} by ${esc(body.bucket)}">${g}</svg>`;
  return { svg, geo: { times, x, W, H } };
}

export function trendTooltip(body: TrendBody, t: string): string {
  const rows = (body.series ?? [])
    .slice(0, 8)
    .map((s, si) => {
      const v = s.points.find((p) => p.t === t)?.v;
      return `<div><i style="background:${SERIES_COLORS[si % SERIES_COLORS.length]}"></i><span>${esc(s.name)}</span><b>${typeof v === "number" ? esc(fmtFloat(v)) : "—"}</b></div>`;
    })
    .join("");
  return `<div class="tt-head">${esc(tickLabel(t, body.bucket))}${body.bucket === "week" ? " (week)" : ""}</div>${rows}`;
}

const FACTORS: { key: Factor; name: string }[] = [
  { key: "F", name: "Frequency" },
  { key: "S", name: "Spread" },
  { key: "T", name: "Trend" },
  { key: "V", name: "Severity" },
  { key: "L", name: "Labelled" },
];

function renderRisks(body: RisksBody): string {
  const items = [...(body.items ?? [])].sort((a, b) => a.rank - b.rank).slice(0, 5);
  const cards = items
    .map((r) => {
      const score = Math.max(0, Math.min(100, Number(r.score) || 0));
      const tone = score >= 80 ? "critical" : score >= 65 ? "error" : score >= 45 ? "warning" : "info";
      const bars = FACTORS.map(({ key, name }) => {
        const v = Math.max(0, Math.min(1, Number(r.inputs?.[key]) || 0));
        const w = body.weights?.[key];
        return `<span class="fx" title="${name} ${fmtFloat(v)} · weight ${w ?? "—"}"><b>${key}</b><span class="track"><span style="width:${(v * 100).toFixed(0)}%"></span></span></span>`;
      }).join("");
      const action = r.action
        ? `<div class="act">${icon("arrow")}<span>${esc(r.action)}</span></div>`
        : `<div class="act none">No action given</div>`;
      return `<article class="risk">
  <div class="rk">${esc(r.rank)}</div>
  <div class="rbody">
    <div class="rtop"><span class="rtitle" title="${esc(r.title)}">${esc(r.title)}</span><span class="score t-${tone}">${fmtFloat(score)}</span></div>
    <div class="scorebar"><span class="t-${tone}" style="width:${score}%"></span></div>
    <div class="rmeta">${teamBadge(r.team)}<span class="stab" title="Rank stability under 10 small weight changes">${esc(stabilityText(r.stability_top3))}</span></div>
    <div class="fxs">${bars}</div>
    ${action}
  </div>
</article>`;
    })
    .join("");
  return `<div class="risks">${cards}</div>`;
}

/** Everything except `trend` (which needs the panel width; see main.ts). */
export function renderEvidenceBody(p: EvidencePayload): string {
  switch (p.kind) {
    case "lines":
      return renderLines(p.body as LinesBody, p.annotations ?? []);
    case "table":
      return renderTable(p.body as TableBody);
    case "risks":
      return renderRisks(p.body as RisksBody);
    default:
      return `<div class="empty">Unsupported evidence kind: ${esc(p.kind)}</div>`;
  }
}
