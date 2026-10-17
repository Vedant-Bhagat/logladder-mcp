import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { REPO_ROOT } from "../server/config";
import { createValidator } from "../server/validate";

const FIXTURES = path.join(REPO_ROOT, "contracts", "fixtures", "panel_events");
const load = (name: string) => JSON.parse(readFileSync(path.join(FIXTURES, name), "utf-8"));
const validate = createValidator();

describe("panel event schema validation", () => {
  const files = readdirSync(FIXTURES).filter((f) => f.endsWith(".json"));

  it("finds all 7 fixtures", () => {
    expect(files.length).toBe(7);
  });

  it.each(files)("accepts %s", (file) => {
    expect(validate(load(file))).toEqual({ ok: true });
  });

  it("rejects an evidence event with a malformed receipt id", () => {
    const ev = load("01_evidence_lines.json");
    ev.payload.receipt.receipt_id = "R-2";
    const r = validate(ev);
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.errors.join(" ")).toMatch(/receipt_id/);
  });

  it("rejects an unknown event type and extra fields", () => {
    const ev = load("06_status.json");
    ev.type = "banner";
    ev.extra = 1;
    expect(validate(ev).ok).toBe(false);
  });

  it("rejects a reset with a payload", () => {
    const ev = load("07_reset.json");
    ev.payload = { anything: true };
    expect(validate(ev).ok).toBe(false);
  });
});
