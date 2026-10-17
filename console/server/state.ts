// In-memory panel state: the last 20 evidence events, the latest explainer and status, and the current role.

export type Role = "engineer" | "team_lead" | "manager" | "unknown";

export interface PanelEvent {
  contract: 1;
  event_id: string;
  ts: string;
  type: "evidence" | "explainer" | "status" | "reset";
  role: Role;
  payload: Record<string, unknown>;
  fixture?: boolean;
}

export const EVIDENCE_HISTORY = 20;
const SEEN_IDS = 1000;

export class PanelState {
  private evidence: PanelEvent[] = [];
  private explainer: PanelEvent | null = null;
  private status: PanelEvent | null = null;
  private seen: string[] = [];
  private seenSet = new Set<string>();
  role: Role = "unknown";

  /** Returns false for a duplicate event_id (already applied), true otherwise. */
  apply(event: PanelEvent): boolean {
    if (this.seenSet.has(event.event_id)) return false;
    this.remember(event.event_id);
    if (event.role !== "unknown") this.role = event.role;
    switch (event.type) {
      case "evidence":
        this.evidence.push(event);
        if (this.evidence.length > EVIDENCE_HISTORY) this.evidence.splice(0, this.evidence.length - EVIDENCE_HISTORY);
        break;
      case "explainer":
        this.explainer = event;
        break;
      case "status":
        this.status = event;
        break;
      case "reset":
        this.evidence = [];
        this.explainer = null;
        this.status = null;
        break;
    }
    return true;
  }

  /** Events a fresh client needs, oldest first. */
  events(): PanelEvent[] {
    const out = [...this.evidence];
    if (this.explainer) out.push(this.explainer);
    if (this.status) out.push(this.status);
    return out.sort((a, b) => this.order(a) - this.order(b));
  }

  private order(e: PanelEvent): number {
    return this.seen.indexOf(e.event_id);
  }

  private remember(id: string): void {
    this.seen.push(id);
    this.seenSet.add(id);
    if (this.seen.length > SEEN_IDS) {
      const dropped = this.seen.shift();
      if (dropped !== undefined) this.seenSet.delete(dropped);
    }
  }
}
