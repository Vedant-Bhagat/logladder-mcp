import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import WebSocket from "ws";
import { createApp, type ConsoleApp } from "../server/app";
import { REPO_ROOT } from "../server/config";

const FIXTURES = path.join(REPO_ROOT, "contracts", "fixtures", "panel_events");
const fixture = (name: string) => JSON.parse(readFileSync(path.join(FIXTURES, name), "utf-8"));

let app: ConsoleApp;
let base: string;

beforeAll(async () => {
  app = createApp({ settings: { host: "127.0.0.1", port: 0, terminal: false, shell: "", startupCommand: "" }, web: (_q, res) => res.end("page") });
  const port = await app.listen();
  base = `http://127.0.0.1:${port}`;
});
afterAll(() => app.close());

const post = (p: string, body: unknown) =>
  fetch(base + p, { method: "POST", headers: { "Content-Type": "application/json" }, body: typeof body === "string" ? body : JSON.stringify(body) });

describe("console API", () => {
  it("accepts every fixture with 202", async () => {
    for (const f of readdirSync(FIXTURES).filter((n) => n.endsWith(".json") && !n.startsWith("07"))) {
      const ev = { ...fixture(f), event_id: `test-${f}` };
      const r = await post("/api/panel", ev);
      expect(r.status, f).toBe(202);
      expect(await r.json()).toMatchObject({ ok: true });
    }
  });

  it("returns state with evidence, explainer and status", async () => {
    const s = await (await fetch(base + "/api/state")).json();
    expect(s.events.map((e: { type: string }) => e.type)).toEqual(["evidence", "evidence", "evidence", "evidence", "explainer", "status"]);
    const roles = ["01", "02", "03", "04", "05", "06"]
      .map((n) => readdirSync(FIXTURES).find((f) => f.startsWith(n))!)
      .map((f) => fixture(f).role)
      .filter((r: string) => r !== "unknown");
    expect(s.role).toBe(roles.at(-1)); // role follows the latest event that names one
  });

  it("ignores a duplicate event_id with 202", async () => {
    const r = await post("/api/panel", { ...fixture("06_status.json"), event_id: "test-06_status.json" });
    expect(r.status).toBe(202);
    expect(await r.json()).toMatchObject({ duplicate: true });
  });

  it("rejects invalid events and bad JSON with 400 and an error list", async () => {
    const bad = fixture("02_evidence_table.json");
    delete bad.payload.receipt;
    const r = await post("/api/panel", bad);
    expect(r.status).toBe(400);
    const body = await r.json();
    expect(body.ok).toBe(false);
    expect(body.errors.length).toBeGreaterThan(0);
    expect((await post("/api/panel", "{not json")).status).toBe(400);
  });

  it("broadcasts snapshot then events on /ws/panels", async () => {
    const ws = new WebSocket(base.replace("http", "ws") + "/ws/panels");
    const msgs: { kind: string; events?: unknown[] }[] = [];
    ws.on("message", (m) => msgs.push(JSON.parse(m.toString())));
    await new Promise((r) => ws.on("open", r));
    await new Promise((r) => setTimeout(r, 50));
    await post("/api/panel", { ...fixture("07_reset.json"), event_id: "test-reset-1" });
    await new Promise((r) => setTimeout(r, 50));
    ws.close();
    expect(msgs[0].kind).toBe("snapshot");
    expect(msgs[0].events?.length).toBe(6);
    expect(msgs.at(-1)).toMatchObject({ kind: "event", event: { type: "reset" } });
    const s = await (await fetch(base + "/api/state")).json();
    expect(s.events).toEqual([]);
  });

  it("keeps at most 20 evidence events", async () => {
    for (let i = 0; i < 25; i++) await post("/api/panel", { ...fixture("03_evidence_trend.json"), event_id: `test-hist-${i}` });
    const s = await (await fetch(base + "/api/state")).json();
    expect(s.events.length).toBe(20);
  });

  it("reports health with the terminal disabled", async () => {
    expect(await (await fetch(base + "/api/health")).json()).toMatchObject({ ok: true, terminal: "disabled" });
  });

  it("sets the role and validates it", async () => {
    const ok = await post("/api/role", { role: "manager" });
    expect(await ok.json()).toEqual({ ok: true, role: "manager", typed: false });
    expect((await post("/api/role", { role: "ceo" })).status).toBe(400);
  });
});
