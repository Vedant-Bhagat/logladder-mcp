// Validates panel events against contracts/panel_event.schema.json, read from the repo at startup (never copied).
import { readFileSync } from "node:fs";
import * as ajv2020 from "ajv/dist/2020.js";
import type { ErrorObject, ValidateFunction } from "ajv";
import { SCHEMA_PATH } from "./config.js";

// ajv ships CJS; under NodeNext the class sits on .default, under bundler resolution on .default.default or the module.
type AjvLike = new (opts: object) => { compile(schema: object): ValidateFunction };
const mod = ajv2020 as unknown as { default?: AjvLike & { default?: AjvLike } };
const AjvCtor = (mod.default?.default ?? mod.default ?? ajv2020) as AjvLike;

export type Validator = (event: unknown) => { ok: true } | { ok: false; errors: string[] };

function describe(e: ErrorObject): string {
  const where = e.instancePath || "(root)";
  const extra = e.keyword === "additionalProperties" ? ` '${(e.params as { additionalProperty: string }).additionalProperty}'` : "";
  return `${where} ${e.message ?? e.keyword}${extra}`;
}

export function createValidator(schemaPath = SCHEMA_PATH): Validator {
  const schema = JSON.parse(readFileSync(schemaPath, "utf-8"));
  // strict:false — the frozen schema uses `description` next to `$ref` and other annotations ajv's strict mode dislikes.
  const ajv = new AjvCtor({ allErrors: true, strict: false });
  const check = ajv.compile(schema);
  return (event) => {
    if (check(event)) return { ok: true };
    const errors: string[] = [...new Set((check.errors ?? []).map(describe))];
    return { ok: false, errors };
  };
}
