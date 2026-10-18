// Left pane: xterm.js mirrored to the server's pty over WS /ws/terminal.
import { FitAddon } from "@xterm/addon-fit";
import { Terminal } from "@xterm/xterm";
import "@xterm/xterm/css/xterm.css";

const THEME = {
  background: "#0B0D11",
  foreground: "#DADDE2",
  cursor: "#8B78FF",
  cursorAccent: "#0B0D11",
  selectionBackground: "rgba(139,120,255,.35)",
  black: "#0E1116",
  red: "#FF6B5E",
  green: "#3CC47C",
  yellow: "#E6B53A",
  blue: "#6E9BF5",
  magenta: "#B4A6FF",
  cyan: "#4FB3D9",
  white: "#C9CDD3",
  brightBlack: "#5E6673",
  brightRed: "#FF8F85",
  brightGreen: "#67D99A",
  brightYellow: "#F0CB6B",
  brightBlue: "#97B8FA",
  brightMagenta: "#CFC5FF",
  brightCyan: "#7CCBE6",
  brightWhite: "#F6F5F1",
};

export interface TerminalView {
  focus(): void;
  fit(): void;
}

export type TerminalState = "running" | "exited" | "disabled";

export function mountTerminal(host: HTMLElement, onState: (s: TerminalState, reason?: string) => void, wsUrl: string): TerminalView {
  const term = new Terminal({
    theme: THEME,
    fontFamily: '"JetBrains Mono", ui-monospace, Consolas, monospace',
    fontSize: window.innerWidth >= 1700 ? 16 : 13, // bigger on a 1920-wide projector
    lineHeight: 1.25,
    cursorBlink: true,
    scrollback: 5000,
    allowProposedApi: false,
  });
  const fit = new FitAddon();
  term.loadAddon(fit);
  term.open(host);

  let ws: WebSocket | null = null;
  let retry = 500;
  const sendResize = () => {
    if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: "resize", cols: term.cols, rows: term.rows }));
  };
  const doFit = () => {
    if (!host.clientWidth || !host.clientHeight) return;
    try {
      fit.fit();
    } catch {
      /* not visible yet */
    }
    sendResize();
  };

  term.onData((data) => {
    if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: "input", data }));
  });

  const connect = () => {
    ws = new WebSocket(wsUrl);
    ws.onopen = () => {
      retry = 500;
      onState("running");
      term.reset();
      doFit();
    };
    ws.onmessage = (ev) => {
      let msg: { type: string; data?: string; code?: number | null; reason?: string };
      try {
        msg = JSON.parse(ev.data);
      } catch {
        return;
      }
      if (msg.type === "output" && msg.data) term.write(msg.data);
      else if (msg.type === "exit") onState("exited");
      else if (msg.type === "restarted") {
        onState("running");
        term.reset();
        doFit();
      } else if (msg.type === "disabled") onState("disabled", msg.reason);
    };
    ws.onclose = () => {
      setTimeout(connect, retry);
      retry = Math.min(retry * 2, 5000);
    };
  };
  connect();

  new ResizeObserver(() => doFit()).observe(host);
  window.addEventListener("resize", doFit);
  return { focus: () => term.focus(), fit: doFit };
}
