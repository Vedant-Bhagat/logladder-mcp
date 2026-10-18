"""The embedded shell behind WS /ws/terminal.

Windows: pywinpty (ConPTY, ready-built wheels, no compiler). macOS/Linux: the standard library's pty.
If neither works (or LOGLAD_TERMINAL=off) the console still runs, panels only.
"""
from __future__ import annotations

import asyncio
import codecs
import logging
import os
import shutil
import sys
import threading
from collections.abc import Callable
from typing import Any

from .config import REPO_ROOT

log = logging.getLogger("loglad.console.terminal")

SCROLLBACK_CHARS = 200_000
IS_WINDOWS = sys.platform == "win32"


def pick_shell(configured: str = "") -> str:
    if configured:
        return configured
    if IS_WINDOWS:
        return "pwsh.exe" if shutil.which("pwsh.exe") else "powershell.exe"
    return os.environ.get("SHELL") or "/bin/bash"


class _PosixPty:
    def __init__(self, shell: str, cwd: str, env: dict[str, str], cols: int, rows: int) -> None:
        import pty

        pid, fd = pty.fork()
        if pid == 0:  # child: become the shell
            try:
                os.chdir(cwd)
                os.execvpe(shell, [shell], env)
            finally:
                os._exit(127)
        self.pid, self.fd = pid, fd
        self.resize(cols, rows)
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")

    def read(self) -> str:
        """Blocking; returns '' at end of stream."""
        try:
            data = os.read(self.fd, 65536)
        except OSError:  # EIO when the child exits
            data = b""
        return self._decoder.decode(data, final=not data)

    def write(self, text: str) -> None:
        os.write(self.fd, text.encode("utf-8"))

    def resize(self, cols: int, rows: int) -> None:
        import fcntl
        import struct
        import termios

        fcntl.ioctl(self.fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))

    def wait(self) -> int:
        try:
            _, status = os.waitpid(self.pid, 0)
            return os.waitstatus_to_exitcode(status)
        except ChildProcessError:
            return 0

    def kill(self) -> None:
        import signal

        try:
            os.kill(self.pid, signal.SIGHUP)
        except ProcessLookupError:
            pass
        try:
            os.close(self.fd)
        except OSError:
            pass


class _WindowsPty:
    def __init__(self, shell: str, cwd: str, env: dict[str, str], cols: int, rows: int) -> None:
        from winpty import PtyProcess  # pywinpty

        self.proc = PtyProcess.spawn(shell, cwd=cwd, env=env, dimensions=(rows, cols))

    def read(self) -> str:
        try:
            return self.proc.read(65536)
        except EOFError:
            return ""

    def write(self, text: str) -> None:
        self.proc.write(text)

    def resize(self, cols: int, rows: int) -> None:
        self.proc.setwinsize(rows, cols)

    def wait(self) -> int:
        try:
            return int(self.proc.wait() or 0)
        except Exception:  # noqa: BLE001 - pywinpty raises various errors on a dead process
            return int(self.proc.exitstatus or 0)

    def kill(self) -> None:
        try:
            self.proc.terminate(force=True)
        except Exception as e:  # noqa: BLE001
            log.debug("terminate failed: %s", e)


def _backend_error() -> str | None:
    """Why the terminal can't run here, or None if it can."""
    if IS_WINDOWS:
        try:
            import winpty  # noqa: F401
        except ImportError:
            return "pywinpty is not installed (pip install -r console/requirements.txt)"
        return None
    try:
        import pty  # noqa: F401
    except ImportError:
        return "no pty support on this platform"
    return None


class Terminal:
    """One shared shell. `on_output(text)` and `on_exit(code)` are called on the asyncio loop."""

    def __init__(self, enabled: bool, shell: str = "", startup_command: str = "claude") -> None:
        self.enabled = enabled
        self.shell = pick_shell(shell)
        self.startup_command = startup_command
        self.status = "disabled"
        self.reason = "" if enabled else "LOGLAD_TERMINAL=off"
        self.history = ""
        self.cols, self.rows = 120, 32
        self._pty: Any = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self.on_output: Callable[[str], None] = lambda _t: None
        self.on_exit: Callable[[int], None] = lambda _c: None

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        if not self.enabled:
            return
        error = _backend_error()
        if error:
            self.reason = error
            log.warning("terminal disabled: %s", error)
            return
        env = {**os.environ, "TERM": "xterm-256color", "COLORTERM": "truecolor"}
        try:
            backend = _WindowsPty if IS_WINDOWS else _PosixPty
            pty = backend(self.shell, str(REPO_ROOT), env, self.cols, self.rows)
        except Exception as e:  # noqa: BLE001 - any spawn failure must leave the panels working
            self.status, self.reason = "disabled", f"could not start {self.shell}: {e}"
            log.warning("terminal %s", self.reason)
            return
        self._pty, self.history, self.status = pty, "", "running"
        log.info("terminal started %s in %s", self.shell, REPO_ROOT)
        threading.Thread(target=self._pump, args=(pty,), name="terminal-reader", daemon=True).start()
        if self.startup_command:
            pty.write(self.startup_command + "\r")

    def _pump(self, pty: Any) -> None:
        """Reader thread: forwards output to the loop until the shell ends."""
        while True:
            text = pty.read()
            if not text:
                break
            self._call(self._emit_output, text)
        code = pty.wait()
        self._call(self._emit_exit, pty, code)

    def _call(self, fn: Callable[..., None], *args: Any) -> None:
        if self._loop and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(fn, *args)

    def _emit_output(self, text: str) -> None:
        self.history = (self.history + text)[-SCROLLBACK_CHARS:]
        self.on_output(text)

    def _emit_exit(self, pty: Any, code: int) -> None:
        if pty is not self._pty:  # an old shell ending after a restart
            return
        self._pty, self.status = None, "exited"
        log.info("terminal exited with code %s", code)
        self.on_exit(code)

    def write(self, text: str) -> None:
        if self._pty is not None:
            try:
                self._pty.write(text)
            except OSError:
                pass

    def resize(self, cols: Any, rows: Any) -> None:
        try:
            cols, rows = int(cols), int(rows)
        except (TypeError, ValueError):
            return
        if not (2 <= cols <= 1000 and 2 <= rows <= 500):
            return
        self.cols, self.rows = cols, rows
        if self._pty is not None:
            try:
                self._pty.resize(cols, rows)
            except OSError:
                pass

    def restart(self) -> bool:
        if self.status == "disabled" or self._loop is None:
            return False
        self.stop()
        self.start(self._loop)
        return self.status == "running"

    def stop(self) -> None:
        pty, self._pty = self._pty, None
        if pty is not None:
            pty.kill()
