// Lucide icons as SVG strings, bundled (no network at demo time).
import {
  ArrowRight,
  BookOpen,
  Briefcase,
  ChartLine,
  ChevronLeft,
  ChevronRight,
  CircleAlert,
  Dot,
  Flag,
  List,
  OctagonX,
  Receipt,
  RotateCcw,
  Scissors,
  Shield,
  ShieldAlert,
  ShieldCheck,
  SquareTerminal,
  Table,
  TriangleAlert,
  Users,
  Wrench,
  createElement,
  type IconNode,
} from "lucide";
import type { Tone } from "./types";

const ICONS = {
  arrow: ArrowRight,
  book: BookOpen,
  briefcase: Briefcase,
  chart: ChartLine,
  prev: ChevronLeft,
  next: ChevronRight,
  error: CircleAlert,
  info: Dot,
  flag: Flag,
  list: List,
  critical: OctagonX,
  receipt: Receipt,
  restart: RotateCcw,
  cut: Scissors,
  shield: Shield,
  shieldWarn: ShieldAlert,
  shieldOk: ShieldCheck,
  terminal: SquareTerminal,
  table: Table,
  warning: TriangleAlert,
  users: Users,
  wrench: Wrench,
} satisfies Record<string, IconNode>;

export type IconName = keyof typeof ICONS;

const cache = new Map<IconName, string>();

export function icon(name: IconName, label?: string): string {
  let svg = cache.get(name);
  if (!svg) {
    const el = createElement(ICONS[name]);
    el.setAttribute("class", "i");
    el.setAttribute("aria-hidden", "true");
    svg = el.outerHTML;
    cache.set(name, svg);
  }
  return label ? `<span class="ic" role="img" aria-label="${label}">${svg}</span>` : svg;
}

/** Distinct shapes per severity, so level is never shown by colour alone. */
export function levelIcon(tone: Tone, level: string): string {
  const name: IconName = tone === "critical" ? "critical" : tone === "error" ? "error" : tone === "warning" ? "warning" : "info";
  return `<span class="lv t-${tone}" title="${level}" role="img" aria-label="${level}">${icon(name)}</span>`;
}

export const KIND_ICON: Record<string, IconName> = { lines: "list", table: "table", trend: "chart", risks: "flag" };
export const ROLE_ICON: Record<string, IconName> = { engineer: "wrench", team_lead: "users", manager: "briefcase" };
