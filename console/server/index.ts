// Entry point: `npm start` (built page from dist/web) or `npm run dev` (Vite middleware, page rebuilt on change).
import { createApp, staticFiles } from "./app.js";
import path from "node:path";
import { CONSOLE_ROOT, loadDotEnv, readSettings } from "./config.js";

loadDotEnv();
const settings = readSettings();
const dev = process.argv.includes("--dev");

async function main(): Promise<void> {
  let web = staticFiles();
  if (dev) {
    const { createServer } = await import("vite");
    const vite = await createServer({ configFile: path.join(CONSOLE_ROOT, "vite.config.ts"), server: { middlewareMode: true, hmr: false }, appType: "spa" });
    web = vite.middlewares as unknown as typeof web;
  }
  const app = createApp({ settings, web });
  let port: number;
  try {
    port = await app.listen();
  } catch (e) {
    const err = e as NodeJS.ErrnoException;
    console.error(err.code === "EADDRINUSE" ? `Port ${settings.port} is already in use. Is the console already running?` : err.message);
    process.exit(1);
  }
  console.log(`LogLadder console on http://${settings.host}:${port}${dev ? " (dev)" : ""} · terminal: ${app.terminal.status}${app.terminal.reason ? ` (${app.terminal.reason})` : ""}`);

  const stop = () => {
    app.close().finally(() => process.exit(0));
  };
  process.on("SIGINT", stop);
  process.on("SIGTERM", stop);
}

main();
