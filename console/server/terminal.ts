// The embedded shell. node-pty is optional: if it can't load (or LOGLAD_TERMINAL=off) the console still runs, panels only.
import { spawnSync } from "node:child_process";
import { EventEmitter } from "node:events";
import { REPO_ROOT, type ConsoleSettings } from "./config.js";

export type TerminalStatus = "running" | "exited" | "disabled";

interface Pty {
  onData(cb: (data: string) => void): void;
  onExit(cb: (e: { exitCode: number }) => void): void;
  write(data: string): void;
  resize(cols: number, rows: number): void;
  kill(): void;
}
interface PtyModule {
  spawn(file: string, args: string[], opts: Record<string, unknown>): Pty;
}

const PTY_PACKAGES = ["node-pty", "@homebridge/node-pty-prebuilt-multiarch"];
const SCROLLBACK_CHARS = 200_000;

async function loadPty(): Promise<{ mod: PtyModule; name: string } | { error: string }> {
  const errors: string[] = [];
  for (const name of PTY_PACKAGES) {
    try {
      const mod = (await import(name)) as PtyModule & { default?: PtyModule };
      return { mod: typeof mod.spawn === "function" ? mod : (mod.default as PtyModule), name };
    } catch (e) {
      errors.push(`${name}: ${(e as Error).message.split("\n")[0]}`);
    }
  }
  return { error: errors.join("; ") };
}

function onPath(cmd: string): boolean {
  const probe = spawnSync(process.platform === "win32" ? "where" : "which", [cmd], { stdio: "ignore" });
  return probe.status === 0;
}

export function pickShell(configured: string): string {
  if (configured) return configured;
  if (process.platform === "win32") return onPath("pwsh.exe") ? "pwsh.exe" : "powershell.exe";
  return process.env.SHELL || "/bin/bash";
}

/** Emits "data" (string) and "exit" (code). Keeps a scrollback so new browser tabs see the current screen. */
export class Terminal extends EventEmitter {
  status: TerminalStatus = "disabled";
  reason = "";
  private pty: Pty | null = null;
  private mod: PtyModule | null = null;
  private scrollback = "";
  private cols = 120;
  private rows = 32;

  constructor(private settings: ConsoleSettings) {
    super();
  }

  async init(): Promise<void> {
    if (!this.settings.terminal) {
      this.reason = "LOGLAD_TERMINAL=off";
      return;
    }
    const loaded = await loadPty();
    if ("error" in loaded) {
      this.reason = `node-pty not available (${loaded.error})`;
      console.warn(`[terminal] disabled: ${this.reason}`);
      return;
    }
    this.mod = loaded.mod;
    console.log(`[terminal] using ${loaded.name}`);
    this.start();
  }

  get history(): string {
    return this.scrollback;
  }

  start(): void {
    if (!this.mod) return;
    const shell = pickShell(this.settings.shell);
    this.scrollback = "";
    try {
      this.pty = this.mod.spawn(shell, [], {
        name: "xterm-256color",
        cols: this.cols,
        rows: this.rows,
        cwd: REPO_ROOT,
        env: { ...process.env, TERM: "xterm-256color", COLORTERM: "truecolor" },
      });
    } catch (e) {
      this.status = "disabled";
      this.reason = `could not start ${shell}: ${(e as Error).message}`;
      console.warn(`[terminal] ${this.reason}`);
      return;
    }
    this.status = "running";
    console.log(`[terminal] started ${shell} in ${REPO_ROOT}`);
    const pty = this.pty;
    pty.onData((data) => {
      this.scrollback = (this.scrollback + data).slice(-SCROLLBACK_CHARS);
      this.emit("data", data);
    });
    pty.onExit(({ exitCode }) => {
      if (this.pty !== pty) return; // an old shell exiting after a restart
      this.status = "exited";
      this.pty = null;
      console.log(`[terminal] exited with code ${exitCode}`);
      this.emit("exit", exitCode);
    });
    if (this.settings.startupCommand) pty.write(this.settings.startupCommand + "\r");
  }

  restart(): void {
    const old = this.pty;
    this.pty = null;
    if (old) {
      try {
        old.kill();
      } catch {
        /* already gone */
      }
    }
    this.start();
  }

  write(data: string): void {
    this.pty?.write(data);
  }

  resize(cols: number, rows: number): void {
    if (!Number.isInteger(cols) || !Number.isInteger(rows) || cols < 2 || rows < 2 || cols > 1000 || rows > 500) return;
    this.cols = cols;
    this.rows = rows;
    try {
      this.pty?.resize(cols, rows);
    } catch {
      /* pty closing */
    }
  }

  dispose(): void {
    const old = this.pty;
    this.pty = null;
    try {
      old?.kill();
    } catch {
      /* ignore */
    }
  }
}
