// Paths and settings for the console server. Everything comes from env (plus an optional repo-root .env).
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));

/** Walk up from this file to the console package (works from server/ in dev and dist/server/ in prod). */
function findConsoleRoot(start: string): string {
  let dir = start;
  for (;;) {
    const pkg = path.join(dir, "package.json");
    if (existsSync(pkg)) {
      try {
        if (JSON.parse(readFileSync(pkg, "utf-8")).name === "loglad-console") return dir;
      } catch {
        /* keep walking */
      }
    }
    const parent = path.dirname(dir);
    if (parent === dir) throw new Error("console package.json not found above " + start);
    dir = parent;
  }
}

export const CONSOLE_ROOT = findConsoleRoot(here);
export const REPO_ROOT = path.dirname(CONSOLE_ROOT);
export const SCHEMA_PATH = path.join(REPO_ROOT, "contracts", "panel_event.schema.json");
export const WEB_DIST = path.join(CONSOLE_ROOT, "dist", "web");

/** Load KEY=VALUE pairs from the repo-root .env without overriding real env vars. */
export function loadDotEnv(file = path.join(REPO_ROOT, ".env")): void {
  if (!existsSync(file)) return;
  for (const raw of readFileSync(file, "utf-8").split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || line.startsWith("#")) continue;
    const eq = line.indexOf("=");
    if (eq < 1) continue;
    const key = line.slice(0, eq).trim();
    let value = line.slice(eq + 1).trim();
    if (/^(['"]).*\1$/.test(value)) value = value.slice(1, -1);
    if (process.env[key] === undefined) process.env[key] = value;
  }
}

export interface ConsoleSettings {
  host: string;
  port: number;
  terminal: boolean;
  shell: string;
  startupCommand: string;
}

export function readSettings(env: NodeJS.ProcessEnv = process.env): ConsoleSettings {
  const port = Number.parseInt(env.LOGLAD_CONSOLE_PORT ?? "", 10);
  return {
    host: "127.0.0.1",
    port: Number.isFinite(port) && port > 0 ? port : 7777,
    terminal: (env.LOGLAD_TERMINAL ?? "on").trim().toLowerCase() !== "off",
    shell: (env.LOGLAD_SHELL ?? "").trim(),
    // Unset → `claude`; set to an empty string → no startup command.
    startupCommand: env.LOGLAD_STARTUP_COMMAND === undefined ? "claude" : env.LOGLAD_STARTUP_COMMAND.trim(),
  };
}
