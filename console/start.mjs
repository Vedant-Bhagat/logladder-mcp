// `npm start` / `npm run dev`: runs the Python console server (python -m loglad_console) with the repo's venv if present.
// `--dev` also rebuilds the page on every change (vite build --watch); reload the browser to see it.
import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const repo = path.dirname(here);
const win = process.platform === "win32";
const venvPython = win ? path.join(repo, ".venv", "Scripts", "python.exe") : path.join(repo, ".venv", "bin", "python");
const python = process.env.LOGLAD_PYTHON || (existsSync(venvPython) ? venvPython : win ? "python" : "python3");

const children = [];
const run = (cmd, args) => {
  const child = spawn(cmd, args, { cwd: here, stdio: "inherit" });
  child.on("error", (e) => {
    console.error(`Could not start ${cmd}: ${e.message}`);
    process.exit(1);
  });
  children.push(child);
  return child;
};

if (process.argv.includes("--dev")) run(process.execPath, [path.join(here, "node_modules", "vite", "bin", "vite.js"), "build", "--watch"]);
const server = run(python, ["-m", "loglad_console"]);
server.on("exit", (code) => {
  for (const c of children) if (c !== server) c.kill();
  process.exit(code ?? 0);
});
for (const sig of ["SIGINT", "SIGTERM"]) process.on(sig, () => children.forEach((c) => c.kill(sig)));
