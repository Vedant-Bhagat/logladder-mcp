// One command to run the console: `python tasks.py console` (or `npm start` in console/).
// First run sets everything up: the repo .venv (via `tasks.py setup`), the console's Python packages,
// node_modules and the built page. Later runs skip what is already done. Then it starts the FastAPI server
// (python -m loglad_console) and opens the browser.
// `--dev` also rebuilds the page on every change (vite build --watch); reload the browser to see it.
// Env: LOGLAD_PYTHON (python used to create the venv), LOGLAD_OPEN_BROWSER=off, LOGLAD_CONSOLE_PORT.
import { spawn, spawnSync } from "node:child_process";
import { existsSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const repo = path.dirname(here);
const win = process.platform === "win32";
const dev = process.argv.includes("--dev");
const venvPython = win ? path.join(repo, ".venv", "Scripts", "python.exe") : path.join(repo, ".venv", "bin", "python");
const port = process.env.LOGLAD_CONSOLE_PORT || "7777";

const say = (msg) => console.log(`\x1b[35m[console]\x1b[0m ${msg}`);
const fail = (msg) => {
  console.error(`\x1b[31m[console]\x1b[0m ${msg}`);
  process.exit(1);
};

/** Run a command to completion with live output; returns true on success. */
function step(cmd, args, opts = {}) {
  const r = spawnSync(cmd, args, { cwd: here, stdio: "inherit", ...opts });
  return !r.error && r.status === 0;
}
const quiet = (cmd, args) => {
  const r = spawnSync(cmd, args, { cwd: here, stdio: "ignore" });
  return !r.error && r.status === 0;
};

// npm: reuse the npm that launched us when possible (avoids shell quirks with npm.cmd on Windows).
function npm(args) {
  if (process.env.npm_execpath) return step(process.execPath, [process.env.npm_execpath, ...args]);
  return step(win ? "npm.cmd" : "npm", args, { shell: win });
}

function newestMtime(dir) {
  let newest = 0;
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, entry.name);
    newest = Math.max(newest, entry.isDirectory() ? newestMtime(p) : statSync(p).mtimeMs);
  }
  return newest;
}
const mtime = (p) => (existsSync(p) ? statSync(p).mtimeMs : 0);

// 1. Python environment (.venv with the project, created the same way as `python tasks.py setup`).
if (!existsSync(venvPython)) {
  const candidates = [process.env.LOGLAD_PYTHON, ...(win ? ["py", "python"] : ["python3", "python"])].filter(Boolean);
  const sysPython = candidates.find((c) => quiet(c, ["-c", "import sys; raise SystemExit(sys.version_info < (3, 11))"]));
  if (!sysPython) fail("Python 3.11+ not found. Install it from https://www.python.org/downloads/ and run this again.");
  say("First run: creating the Python environment (.venv) — this takes a minute…");
  if (!step(sysPython, [path.join(repo, "tasks.py"), "setup"], { cwd: repo })) fail("`python tasks.py setup` failed (see above).");
}
const python = venvPython;

// 2. The console's own Python packages (fastapi, websockets, pywinpty on Windows).
const imports = ["fastapi", "uvicorn", "websockets", ...(win ? ["winpty"] : [])].join(", ");
if (!quiet(python, ["-c", `import ${imports}`])) {
  say("Installing the console's Python packages…");
  if (!step(python, ["-m", "pip", "install", "-q", "-r", path.join(here, "requirements.txt")])) fail("pip install failed (see above).");
}

// 3. Node packages for the page.
if (mtime(path.join(here, "package-lock.json")) > mtime(path.join(here, "node_modules", ".package-lock.json"))) {
  say("Installing the page's packages (npm ci)…");
  if (!npm(["ci", "--no-audit", "--no-fund"])) fail("npm ci failed (see above).");
}

// 4. Build the page when it's missing or older than its sources.
const built = path.join(here, "dist", "web", "index.html");
if (!dev && mtime(built) < Math.max(newestMtime(path.join(here, "web")), mtime(path.join(here, "package-lock.json")))) {
  say("Building the page…");
  if (!npm(["run", "build"])) fail("Page build failed (see above).");
}

// 5. Claude Code is what the terminal starts.
if (!quiet(win ? "where" : "which", [win ? "claude.cmd" : "claude"]) && !quiet(win ? "where" : "which", ["claude"])) {
  say("Note: `claude` (Claude Code) isn't on PATH, so the terminal will open without it. Install: npm install -g @anthropic-ai/claude-code");
}

// 6. Run.
const children = [];
const run = (cmd, args) => {
  const child = spawn(cmd, args, { cwd: here, stdio: "inherit" });
  child.on("error", (e) => fail(`Could not start ${cmd}: ${e.message}`));
  children.push(child);
  return child;
};
if (dev) run(process.execPath, [path.join(here, "node_modules", "vite", "bin", "vite.js"), "build", "--watch"]);
const server = run(python, ["-m", "loglad_console"]);
server.on("exit", (code) => {
  for (const c of children) if (c !== server) c.kill();
  process.exit(code ?? 0);
});
for (const sig of ["SIGINT", "SIGTERM"]) process.on(sig, () => children.forEach((c) => c.kill(sig)));

// 7. Open the browser once the server answers.
if ((process.env.LOGLAD_OPEN_BROWSER ?? "on").toLowerCase() !== "off") {
  const url = `http://127.0.0.1:${port}`;
  const open = () =>
    win ? spawn("cmd", ["/c", "start", "", url], { stdio: "ignore", detached: true })
    : spawn(process.platform === "darwin" ? "open" : "xdg-open", [url], { stdio: "ignore", detached: true }).on("error", () => {});
  let tries = 0;
  const poll = setInterval(async () => {
    tries += 1;
    try {
      if ((await fetch(`${url}/api/health`)).ok) {
        clearInterval(poll);
        say(`Open ${url}`);
        open().unref();
      }
    } catch {
      if (tries > 60) clearInterval(poll);
    }
  }, 500);
}
