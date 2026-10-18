// Console page: header, terminal pane, evidence + explainer panels. All panel data arrives over WS /ws/panels.
import "@awesome.me/webawesome/dist/styles/themes/default.css";
import "@awesome.me/webawesome/dist/components/split-panel/split-panel.js";
import "@awesome.me/webawesome/dist/components/drawer/drawer.js";
import "@awesome.me/webawesome/dist/components/tooltip/tooltip.js";
import "@awesome.me/webawesome/dist/components/copy-button/copy-button.js";
import "@fontsource-variable/inter";
import "@fontsource-variable/inter-tight";
import "@fontsource/jetbrains-mono/400.css";
import "@fontsource/jetbrains-mono/500.css";
import "./styles.css";

import { renderEvidenceBody, renderTrend, trendTooltip, type TrendGeometry } from "./evidence";
import { renderMarkdown, receiptChip } from "./explainer";
import { claimsState, countLabel, esc, fmtInt, scopeLabel } from "./format";
import { KIND_ICON, ROLE_ICON, icon } from "./icons";
import { ReceiptStore, receiptHtml } from "./receipts";
import { mountTerminal, type TerminalState } from "./terminal";
import type { EvidencePayload, ExplainerPayload, PanelEvent, Role, StatusPayload, TrendBody } from "./types";

const $ = <T extends HTMLElement = HTMLElement>(id: string) => document.getElementById(id) as T;
const wsBase = `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}`;

const HISTORY = 20;
const ROLES: { key: Exclude<Role, "unknown">; label: string }[] = [
  { key: "engineer", label: "Engineer" },
  { key: "team_lead", label: "Team lead" },
  { key: "manager", label: "Manager" },
];

const ui = {
  evidence: [] as PanelEvent[],
  viewing: null as number | null, // index into evidence; null = follow newest
  explainer: null as PanelEvent | null,
  status: null as PanelEvent | null,
  role: "unknown" as Role,
  receipts: new ReceiptStore(),
  trend: null as { body: TrendBody; geo: TrendGeometry } | null,
};

/* ---------- header ---------- */

function renderRoles(): void {
  $("roles").innerHTML = ROLES.map(
    (r) =>
      `<button class="role" data-role="${r.key}" aria-pressed="${ui.role === r.key}" title="${r.label}: stops Claude (Ctrl+C) and runs /mcp__loglad__${r.key}">${icon(ROLE_ICON[r.key])}<span>${r.label}</span></button>`,
  ).join("");
}

function renderHeader(): void {
  const latest = ui.evidence.at(-1)?.payload as EvidencePayload | undefined;
  const scope = scopeLabel(latest?.receipt?.scope);
  const scopeEl = $("scope");
  scopeEl.hidden = !scope;
  scopeEl.textContent = scope;
  scopeEl.title = scope ? `Scope of the latest evidence: ${scope}` : "";

  const status = ui.status?.payload as StatusPayload | undefined;
  const count = $("receiptCount");
  count.hidden = !status;
  if (status) count.innerHTML = `${icon("receipt")}<span>${fmtInt(status.receipt_count)}</span>`;

  const c = claimsState(status?.claims);
  const claims = $("claims");
  claims.className = `claims ${c.state}`;
  claims.innerHTML = `${icon(c.state === "ok" ? "shieldOk" : c.state === "warn" ? "shieldWarn" : "shield")}<span>${esc(c.text)}</span>`;
  const k = status?.claims;
  $("claimsTip").innerHTML = k
    ? `<b>Answer check</b><br>${fmtInt(k.backed)} backed · ${fmtInt(k.unbacked)} unbacked · ${fmtInt(k.mismatched)} mismatched · ${fmtInt(k.flagged)} flagged<br>${fmtInt(status!.receipt_count)} receipts this session`
    : "Claude hasn't checked an answer yet (check_answer).";
}

/* ---------- evidence ---------- */

function currentEvidence(): { ev: PanelEvent; index: number } | null {
  if (!ui.evidence.length) return null;
  const index = ui.viewing ?? ui.evidence.length - 1;
  return { ev: ui.evidence[index], index };
}

function drawTrend(): void {
  const host = $("evBody").querySelector<HTMLElement>(".trend");
  if (!host || !ui.trend) return;
  const { svg, geo } = renderTrend(ui.trend.body, host.clientWidth - 4);
  host.innerHTML = svg;
  ui.trend.geo = geo;
}

function renderEvidence(pulse = false): void {
  const cur = currentEvidence();
  const body = $("evBody");
  ui.trend = null;
  if (!cur) {
    $("evKind").innerHTML = icon("list");
    $("evTitle").textContent = "Evidence";
    $("evCount").textContent = "";
    $("evTrunc").hidden = true;
    $("evChip").replaceChildren();
    $("evFoot").hidden = true;
    body.innerHTML = `<div class="empty">${icon("list")}<p>Waiting for Claude to show evidence…</p></div>`;
    return;
  }
  const p = cur.ev.payload as EvidencePayload;
  $("evKind").innerHTML = icon(KIND_ICON[p.kind] ?? "list");
  $("evKind").title = p.kind;
  $("evTitle").textContent = p.title;
  $("evTitle").title = p.title;
  $("evCount").textContent = countLabel(p.receipt.returned, p.receipt.total_matches);
  $("evCount").title = p.receipt.total_matches === null ? `${p.receipt.returned} rows shown` : `showing ${fmtInt(p.receipt.returned)} of ${fmtInt(p.receipt.total_matches)}`;
  const trunc = $("evTrunc");
  trunc.hidden = !p.receipt.truncated;
  trunc.innerHTML = `${icon("cut")}`;
  trunc.title = "Truncated: more rows exist than shown";
  const chip = receiptChip(p.receipt.receipt_id, true);
  if (pulse) chip.classList.add("pulse");
  $("evChip").replaceChildren(chip);

  if (p.kind === "trend") {
    body.innerHTML = `<div class="trend"></div>`;
    ui.trend = { body: p.body as TrendBody, geo: null as unknown as TrendGeometry };
    drawTrend();
  } else {
    body.innerHTML = renderEvidenceBody(p);
  }
  body.scrollTop = 0;
  if (pulse) {
    body.classList.remove("arrive");
    void body.offsetWidth;
    body.classList.add("arrive");
  }

  const foot = $("evFoot");
  foot.hidden = ui.evidence.length < 2;
  $("evDots").innerHTML = ui.evidence
    .map((e, i) => {
      const ep = e.payload as EvidencePayload;
      return `<button class="dot${i === cur.index ? " on" : ""}" data-i="${i}" title="${esc(ep.title)}" aria-label="Evidence ${i + 1}: ${esc(ep.title)}"></button>`;
    })
    .join("");
  ($("evPrev") as HTMLButtonElement).disabled = cur.index === 0;
  ($("evNext") as HTMLButtonElement).disabled = cur.index === ui.evidence.length - 1;
  const live = $("evLive");
  live.classList.toggle("on", ui.viewing === null);
  live.title = ui.viewing === null ? "Following the newest evidence" : "Jump back to the newest evidence";
}

function step(delta: number): void {
  const cur = currentEvidence();
  if (!cur) return;
  const next = Math.max(0, Math.min(ui.evidence.length - 1, cur.index + delta));
  ui.viewing = next === ui.evidence.length - 1 ? null : next;
  renderEvidence();
}

/* ---------- explainer ---------- */

function renderExplainer(): void {
  const body = $("xpBody");
  $("xpKind").innerHTML = icon("book");
  if (!ui.explainer) {
    $("xpTitle").textContent = "Explainer";
    body.innerHTML = `<div class="empty">${icon("book")}<p>Explanations appear here.</p></div>`;
    return;
  }
  const p = ui.explainer.payload as ExplainerPayload;
  $("xpTitle").textContent = p.title;
  $("xpTitle").title = p.title;
  renderMarkdown(body, p.markdown, new Set((p.receipts ?? []).map((r) => r.receipt_id)));
  body.scrollTop = 0;
}

/* ---------- receipts drawer ---------- */

function openReceipt(id: string): void {
  const r = ui.receipts.get(id);
  const drawer = $("drawer") as HTMLElement & { open: boolean; label: string };
  drawer.label = `Receipt ${id}`;
  drawer.innerHTML = r
    ? receiptHtml(r)
    : `<p class="muted">Receipt ${esc(id)} was not included in the events received so far, so its SQL can't be shown here. Ask Claude to run <code>get_receipt</code> for it.</p>`;
  drawer.open = true;
}

/* ---------- events ---------- */

function apply(ev: PanelEvent, live: boolean): void {
  if (ev.role && ev.role !== "unknown") ui.role = ev.role;
  switch (ev.type) {
    case "evidence": {
      const p = ev.payload as EvidencePayload;
      ui.receipts.add(p.receipt);
      ui.evidence.push(ev);
      if (ui.evidence.length > HISTORY) {
        ui.evidence.splice(0, ui.evidence.length - HISTORY);
        if (ui.viewing !== null) ui.viewing = Math.max(0, ui.viewing - 1);
      }
      if (live) renderEvidence(ui.viewing === null);
      break;
    }
    case "explainer": {
      for (const r of (ev.payload as ExplainerPayload).receipts ?? []) ui.receipts.add(r);
      ui.explainer = ev;
      if (live) renderExplainer();
      break;
    }
    case "status":
      ui.status = ev;
      break;
    case "reset":
      ui.evidence = [];
      ui.viewing = null;
      ui.explainer = null;
      ui.status = null;
      ui.receipts.clear();
      if (live) {
        renderEvidence();
        renderExplainer();
      }
      break;
  }
  if (live) {
    renderRoles();
    renderHeader();
  }
}

function snapshot(events: PanelEvent[], role: Role): void {
  ui.evidence = [];
  ui.viewing = null;
  ui.explainer = null;
  ui.status = null;
  ui.receipts.clear();
  ui.role = role ?? "unknown";
  for (const ev of events) apply(ev, false);
  if (role && role !== "unknown") ui.role = role;
  renderRoles();
  renderHeader();
  renderEvidence();
  renderExplainer();
}

function connectPanels(retry = 500): void {
  const ws = new WebSocket(`${wsBase}/ws/panels`);
  const conn = $("conn");
  ws.onopen = () => {
    retry = 500;
    $("banner").hidden = true;
    conn.className = "conn ok";
    conn.title = "Connected to the console server";
  };
  ws.onmessage = (m) => {
    let msg: { kind: string; events?: PanelEvent[]; event?: PanelEvent; role?: Role };
    try {
      msg = JSON.parse(m.data);
    } catch {
      return;
    }
    try {
      if (msg.kind === "snapshot") snapshot(msg.events ?? [], msg.role ?? "unknown");
      else if (msg.kind === "event" && msg.event) apply(msg.event, true);
      else if (msg.kind === "role" && msg.role) {
        ui.role = msg.role;
        renderRoles();
      }
    } catch (e) {
      console.error("render failed", e); // a bad event must never take the page down
    }
  };
  ws.onclose = () => {
    $("banner").hidden = false;
    conn.className = "conn down";
    conn.title = "Disconnected — reconnecting";
    setTimeout(() => connectPanels(Math.min(retry * 2, 5000)), retry);
  };
}

/* ---------- terminal ---------- */

let termState: TerminalState = "disabled";

let toastTimer = 0;
function toast(html: string): void {
  const t = $("toast");
  t.innerHTML = html;
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => (t.hidden = true), 3200);
}

/** Terminal not running in the page: copy the role command so it can be pasted into Claude elsewhere. */
async function copyRoleCommand(role: Role): Promise<void> {
  const cmd = `/mcp__loglad__${role}`;
  try {
    await navigator.clipboard.writeText(cmd);
    toast(`${icon(ROLE_ICON[role])}<span>Copied <code>${esc(cmd)}</code> — paste it into Claude</span>`);
  } catch {
    toast(`${icon(ROLE_ICON[role])}<span>Type <code>${esc(cmd)}</code> in Claude</span>`);
  }
}

function terminalState(s: TerminalState, reason?: string): void {
  termState = s;
  const overlay = $("termOverlay");
  if (s === "running") {
    overlay.hidden = true;
    return;
  }
  overlay.hidden = false;
  if (s === "exited") {
    overlay.innerHTML = `<div class="ov">${icon("terminal")}<p>The terminal session ended.</p><button class="btn" id="restartTerm">${icon("restart")} Restart</button></div>`;
    $("restartTerm").onclick = () => fetch("/api/terminal/restart", { method: "POST" });
  } else {
    overlay.innerHTML = `<div class="ov">${icon("terminal")}<p><b>Terminal disabled</b> — run <code>claude</code> in Windows Terminal next to this window.</p><p class="muted small">${esc(reason ?? "")}</p></div>`;
  }
}

/* ---------- wiring ---------- */

document.addEventListener("click", (e) => {
  const t = e.target as HTMLElement;
  const chip = t.closest<HTMLElement>("[data-receipt]");
  if (chip) {
    openReceipt(chip.dataset.receipt!);
    return;
  }
  const role = t.closest<HTMLElement>("[data-role]");
  if (role) {
    ui.role = role.dataset.role as Role;
    renderRoles();
    if (termState !== "running") copyRoleCommand(ui.role);
    fetch("/api/role", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ role: ui.role }) })
      .catch(() => {})
      .finally(() => term.focus());
    return;
  }
  const dot = t.closest<HTMLElement>(".dot[data-i]");
  if (dot) {
    const i = Number(dot.dataset.i);
    ui.viewing = i === ui.evidence.length - 1 ? null : i;
    renderEvidence();
    return;
  }
  const line = t.closest<HTMLElement>(".ln");
  if (line && !t.closest(".more")) {
    const more = line.querySelector<HTMLElement>(".more")!;
    more.hidden = !more.hidden;
    line.setAttribute("aria-expanded", String(!more.hidden));
  }
});

$("evBody").addEventListener("keydown", (e) => {
  const line = (e.target as HTMLElement).closest?.(".ln");
  if (line && (e.key === "Enter" || e.key === " ")) {
    e.preventDefault();
    (line as HTMLElement).click();
  }
});
$("evidence").addEventListener("keydown", (e) => {
  if (e.key === "ArrowLeft") step(-1);
  if (e.key === "ArrowRight") step(1);
});
$("evPrev").innerHTML = icon("prev");
$("evNext").innerHTML = icon("next");
$("evPrev").onclick = () => step(-1);
$("evNext").onclick = () => step(1);
$("evLive").onclick = () => {
  ui.viewing = null;
  renderEvidence();
};

// Trend hover: crosshair + exact values for the nearest bucket.
$("evBody").addEventListener("mousemove", (e) => {
  const tip = $("chartTip");
  const svg = (e.target as Element).closest?.(".trend svg") as SVGSVGElement | null;
  if (!svg || !ui.trend?.geo) {
    tip.hidden = true;
    return;
  }
  const { geo, body } = ui.trend;
  const box = svg.getBoundingClientRect();
  const px = ((e.clientX - box.left) / box.width) * geo.W;
  let best = 0;
  geo.times.forEach((_, i) => {
    if (Math.abs(geo.x(i) - px) < Math.abs(geo.x(best) - px)) best = i;
  });
  const cross = svg.querySelector(".cross")!;
  cross.setAttribute("x1", String(geo.x(best)));
  cross.setAttribute("x2", String(geo.x(best)));
  cross.setAttribute("visibility", "visible");
  tip.innerHTML = trendTooltip(body, geo.times[best]);
  tip.hidden = false;
  const left = Math.min(window.innerWidth - tip.offsetWidth - 8, e.clientX + 14);
  tip.style.left = `${left}px`;
  tip.style.top = `${e.clientY + 14}px`;
});
$("evBody").addEventListener("mouseleave", () => {
  $("chartTip").hidden = true;
  $("evBody").querySelector(".cross")?.setAttribute("visibility", "hidden");
});
new ResizeObserver(() => drawTrend()).observe($("evBody"));

// Show/hide the terminal (button left of the logo, or Ctrl/Cmd+Shift+F) so the panels can fill the screen.
let savedSplit = 58;
function setTerminalVisible(visible: boolean): void {
  const split = $("mainSplit") as HTMLElement & { position: number };
  if (!visible && split.position > 1) savedSplit = split.position;
  split.position = visible ? savedSplit : 0;
  const btn = $("termToggle");
  btn.setAttribute("aria-pressed", String(visible));
  btn.title = visible ? "Hide the terminal (Ctrl+Shift+F)" : "Show the terminal (Ctrl+Shift+F)";
  btn.setAttribute("aria-label", btn.title);
  btn.innerHTML = icon(visible ? "hideTerm" : "showTerm");
  if (visible) setTimeout(() => term.fit(), 50);
}
const terminalVisible = () => ($("mainSplit") as HTMLElement & { position: number }).position > 1;
$("termToggle").onclick = () => setTerminalVisible(!terminalVisible());
// Capture phase, so the shortcut still works while the terminal has focus.
window.addEventListener(
  "keydown",
  (e) => {
    if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key.toLowerCase() === "f") {
      e.preventDefault();
      e.stopPropagation();
      setTerminalVisible(!terminalVisible());
    }
  },
  true,
);

renderRoles();
renderHeader();
renderEvidence();
renderExplainer();
const term = mountTerminal($("termHost"), terminalState, `${wsBase}/ws/terminal`);
setTerminalVisible(true);
connectPanels();
