// Shapes from contracts/panel_event.schema.json (the server has already validated every event).

export type Role = "engineer" | "team_lead" | "manager" | "unknown";
export type Tone = "critical" | "error" | "warning" | "info" | "accent" | "good";

export interface Scope {
  dataset?: string;
  from?: string | null;
  to?: string | null;
  filters?: Record<string, unknown> | null;
  unit?: string | null;
  episode_gap?: string | null;
  group_by?: string | null;
  bucket?: string | null;
  [k: string]: unknown;
}

export interface ReceiptRef {
  receipt_id: string;
  tool: string;
  sql: string[];
  scope: Scope;
  total_matches: number | null;
  returned: number;
  truncated: boolean;
  runtime_ms: number;
}

export interface PanelLine {
  id: number;
  ts: string;
  dataset: "bgl" | "openstack";
  source: string;
  component: string | null;
  level: string;
  tone: Tone;
  message: string;
  highlights: [number, number][];
  repeat_count: number;
  is_anchor?: boolean;
}

export interface Annotation {
  line_id: number;
  label: string;
  tone: Tone;
}

export interface LinesBody {
  groups: { label: string; lines: PanelLine[] }[];
}
export interface TableColumn {
  key: string;
  label: string;
  type: "text" | "int" | "float" | "percent" | "team" | "level" | "change";
}
export interface TableBody {
  columns: TableColumn[];
  rows: Record<string, unknown>[];
  total_row: Record<string, unknown> | null;
}
export interface TrendBody {
  metric: string;
  bucket: "day" | "week";
  unit_label: string;
  series: { name: string; points: { t: string; v: number | null }[] }[];
}
export type Factor = "F" | "S" | "T" | "V" | "L";
export interface RiskItem {
  rank: number;
  title: string;
  dataset: string;
  team: string;
  score: number;
  inputs: Record<Factor, number>;
  stability_top3: number;
  action: string | null;
}
export interface RisksBody {
  weights: Record<Factor, number>;
  items: RiskItem[];
}

export interface EvidencePayload {
  kind: "lines" | "table" | "trend" | "risks";
  title: string;
  receipt: ReceiptRef;
  annotations: Annotation[];
  body: LinesBody | TableBody | TrendBody | RisksBody;
}
export interface ExplainerPayload {
  title: string;
  markdown: string;
  receipts: ReceiptRef[];
}
export interface StatusPayload {
  receipt_count: number;
  claims: { backed: number; unbacked: number; mismatched: number; flagged: number } | null;
}

export interface PanelEvent {
  contract: 1;
  event_id: string;
  ts: string;
  type: "evidence" | "explainer" | "status" | "reset";
  role: Role;
  payload: EvidencePayload | ExplainerPayload | StatusPayload | Record<string, never>;
}
