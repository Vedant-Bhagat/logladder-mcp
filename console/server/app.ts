// HTTP + WebSocket server for the console. API frozen in docs/specs/03-ayoub-console.md §3.1.
import { createReadStream, existsSync, statSync } from "node:fs";
import http from "node:http";
import path from "node:path";
import type { Duplex } from "node:stream";
import { WebSocketServer, WebSocket } from "ws";
import { WEB_DIST, type ConsoleSettings } from "./config.js";
import { PanelState, type PanelEvent, type Role } from "./state.js";
import { Terminal } from "./terminal.js";
import { createValidator, type Validator } from "./validate.js";

const MAX_BODY = 2 * 1024 * 1024;
const ROLES: Role[] = ["engineer", "team_lead", "manager"];

type Middleware = (req: http.IncomingMessage, res: http.ServerResponse, next: () => void) => void;

export interface ConsoleApp {
  server: http.Server;
  state: PanelState;
  terminal: Terminal;
  listen(): Promise<number>;
  close(): Promise<void>;
}

export interface AppOptions {
  settings: ConsoleSettings;
  validator?: Validator;
  /** Dev mode: Vite's middleware serves the page. Prod: files from dist/web. */
  web?: Middleware;
}

function send(res: http.ServerResponse, status: number, body: unknown): void {
  const text = JSON.stringify(body);
  res.writeHead(status, { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" });
  res.end(text);
}

function readBody(req: http.IncomingMessage): Promise<string> {
  return new Promise((resolve, reject) => {
    let size = 0;
    const chunks: Buffer[] = [];
    req.on("data", (c: Buffer) => {
      size += c.length;
      if (size > MAX_BODY) {
        reject(new Error("body too large"));
        req.destroy();
        return;
      }
      chunks.push(c);
    });
    req.on("end", () => resolve(Buffer.concat(chunks).toString("utf-8")));
    req.on("error", reject);
  });
}

const MIME: Record<string, string> = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".woff2": "font/woff2",
  ".woff": "font/woff",
  ".json": "application/json",
  ".ico": "image/x-icon",
};

/** Serves dist/web with an index.html fallback. */
export function staticFiles(root = WEB_DIST): Middleware {
  return (req, res) => {
    const url = new URL(req.url ?? "/", "http://x");
    let file = path.normalize(path.join(root, decodeURIComponent(url.pathname)));
    if (!file.startsWith(root)) {
      res.writeHead(403).end();
      return;
    }
    if (!existsSync(file) || statSync(file).isDirectory()) file = path.join(root, "index.html");
    if (!existsSync(file)) {
      res.writeHead(503, { "Content-Type": "text/plain; charset=utf-8" });
      res.end("Console page not built. Run `npm run build` in console/, or use `npm run dev`.");
      return;
    }
    const ext = path.extname(file);
    res.writeHead(200, {
      "Content-Type": MIME[ext] ?? "application/octet-stream",
      "Cache-Control": file.includes(`${path.sep}assets${path.sep}`) ? "public, max-age=31536000, immutable" : "no-cache",
    });
    createReadStream(file).pipe(res);
  };
}

function summary(e: PanelEvent): string {
  const p = e.payload as { kind?: string; receipt?: { receipt_id?: string } };
  return [e.type, p.kind, p.receipt?.receipt_id, e.role].filter(Boolean).join(" ");
}

export function createApp(opts: AppOptions): ConsoleApp {
  const { settings } = opts;
  const validator = opts.validator ?? createValidator();
  const state = new PanelState();
  const terminal = new Terminal(settings);
  const web = opts.web ?? staticFiles();

  const panelWss = new WebSocketServer({ noServer: true });
  const termWss = new WebSocketServer({ noServer: true });

  const broadcast = (wss: WebSocketServer, msg: unknown) => {
    const text = JSON.stringify(msg);
    for (const c of wss.clients) if (c.readyState === WebSocket.OPEN) c.send(text);
  };

  panelWss.on("connection", (ws) => {
    ws.send(JSON.stringify({ kind: "snapshot", events: state.events(), role: state.role }));
  });

  termWss.on("connection", (ws) => {
    if (terminal.status === "disabled") {
      ws.send(JSON.stringify({ type: "disabled", reason: terminal.reason }));
    } else {
      if (terminal.history) ws.send(JSON.stringify({ type: "output", data: terminal.history }));
      if (terminal.status === "exited") ws.send(JSON.stringify({ type: "exit", code: null }));
    }
    ws.on("message", (raw) => {
      let msg: { type?: string; data?: unknown; cols?: unknown; rows?: unknown };
      try {
        msg = JSON.parse(raw.toString());
      } catch {
        return;
      }
      if (msg.type === "input" && typeof msg.data === "string") terminal.write(msg.data);
      else if (msg.type === "resize") terminal.resize(Number(msg.cols), Number(msg.rows));
    });
  });
  terminal.on("data", (data: string) => broadcast(termWss, { type: "output", data }));
  terminal.on("exit", (code: number) => broadcast(termWss, { type: "exit", code }));

  async function handleApi(req: http.IncomingMessage, res: http.ServerResponse, pathname: string): Promise<void> {
    const method = req.method ?? "GET";
    if (pathname === "/api/panel") {
      if (method !== "POST") return send(res, 405, { ok: false, errors: ["use POST"] });
      let event: unknown;
      try {
        event = JSON.parse(await readBody(req));
      } catch (e) {
        return send(res, 400, { ok: false, errors: [`invalid JSON body: ${(e as Error).message}`] });
      }
      const result = validator(event);
      if (!result.ok) {
        console.warn(`[panel] rejected: ${result.errors.slice(0, 3).join(" | ")}`);
        return send(res, 400, { ok: false, errors: result.errors });
      }
      const ev = event as PanelEvent;
      if (!state.apply(ev)) {
        console.log(`[panel] duplicate ${ev.event_id} ignored`);
        return send(res, 202, { ok: true, duplicate: true });
      }
      console.log(`[panel] ${summary(ev)}`);
      broadcast(panelWss, { kind: "event", event: ev });
      return send(res, 202, { ok: true });
    }
    if (pathname === "/api/state" && method === "GET") {
      return send(res, 200, { events: state.events(), role: state.role });
    }
    if (pathname === "/api/health" && method === "GET") {
      return send(res, 200, { ok: true, panel_clients: panelWss.clients.size, terminal: terminal.status });
    }
    if (pathname === "/api/terminal/restart" && method === "POST") {
      if (terminal.status === "disabled") return send(res, 409, { ok: false, errors: [`terminal disabled: ${terminal.reason}`] });
      terminal.restart();
      broadcast(termWss, { type: "restarted" });
      return send(res, 200, { ok: true, terminal: terminal.status });
    }
    if (pathname === "/api/role" && method === "POST") {
      let role: unknown;
      try {
        role = JSON.parse(await readBody(req)).role;
      } catch {
        return send(res, 400, { ok: false, errors: ["body must be JSON {\"role\": ...}"] });
      }
      if (!ROLES.includes(role as Role)) return send(res, 400, { ok: false, errors: [`role must be one of ${ROLES.join(", ")}`] });
      state.role = role as Role;
      // Typed without Enter: Claude may be mid-answer, the presenter presses Enter.
      const typed = terminal.status === "running";
      if (typed) terminal.write(`/mcp__loglad__${role}`);
      broadcast(panelWss, { kind: "role", role });
      return send(res, 200, { ok: true, role, typed });
    }
    return send(res, 404, { ok: false, errors: [`no route ${method} ${pathname}`] });
  }

  const server = http.createServer((req, res) => {
    const pathname = new URL(req.url ?? "/", "http://x").pathname;
    if (pathname.startsWith("/api/")) {
      handleApi(req, res, pathname).catch((e) => {
        console.error("[api] error", e);
        if (!res.headersSent) send(res, 500, { ok: false, errors: [(e as Error).message] });
      });
      return;
    }
    web(req, res, () => {
      res.writeHead(404).end();
    });
  });

  server.on("upgrade", (req: http.IncomingMessage, socket: Duplex, head: Buffer) => {
    const pathname = new URL(req.url ?? "/", "http://x").pathname;
    const wss = pathname === "/ws/panels" ? panelWss : pathname === "/ws/terminal" ? termWss : null;
    if (!wss) return; // other upgrades (e.g. Vite) handle themselves
    wss.handleUpgrade(req, socket, head, (ws) => wss.emit("connection", ws, req));
  });

  return {
    server,
    state,
    terminal,
    async listen() {
      await terminal.init();
      await new Promise<void>((resolve, reject) => {
        server.once("error", reject);
        server.listen(settings.port, settings.host, () => resolve());
      });
      const addr = server.address();
      return typeof addr === "object" && addr ? addr.port : settings.port;
    },
    async close() {
      terminal.dispose();
      for (const c of [...panelWss.clients, ...termWss.clients]) c.terminate();
      await new Promise<void>((resolve) => server.close(() => resolve()));
    },
  };
}
