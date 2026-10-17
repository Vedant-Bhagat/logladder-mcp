"""HTTP + WebSocket API, frozen in docs/specs/03-ayoub-console.md §3.1 (panels only: no embedded terminal)."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from jsonschema import Draft202012Validator

from .config import SCHEMA_PATH, WEB_DIST
from .state import PanelState

log = logging.getLogger("loglad.console")

ROLES = ("engineer", "team_lead", "manager")
MAX_BODY = 2 * 1024 * 1024
NO_STORE = {"Cache-Control": "no-store"}


def make_validator(schema_path: Path = SCHEMA_PATH) -> Draft202012Validator:
    """The schema is read from contracts/ at startup, never copied."""
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def schema_errors(validator: Draft202012Validator, event: Any) -> list[str]:
    errors = []
    for e in sorted(validator.iter_errors(event), key=lambda e: list(e.absolute_path)):
        where = "/" + "/".join(str(p) for p in e.absolute_path) if e.absolute_path else "(root)"
        errors.append(f"{where} {e.message}")
    return list(dict.fromkeys(errors))


def _summary(event: dict[str, Any]) -> str:
    payload = event.get("payload") or {}
    receipt = payload.get("receipt") or {}
    parts = [event.get("type"), payload.get("kind"), receipt.get("receipt_id"), event.get("role")]
    return " ".join(str(p) for p in parts if p)


class Hub:
    """Connected /ws/panels clients."""

    def __init__(self) -> None:
        self.clients: set[WebSocket] = set()

    async def broadcast(self, message: dict[str, Any]) -> None:
        text = json.dumps(message)
        for ws in list(self.clients):
            try:
                await ws.send_text(text)
            except (WebSocketDisconnect, RuntimeError, OSError):  # client went away mid-send
                self.clients.discard(ws)


def create_app(web_root: Path = WEB_DIST, schema_path: Path = SCHEMA_PATH) -> FastAPI:
    app = FastAPI(title="LogLadder console", docs_url=None, redoc_url=None, openapi_url=None)
    validator = make_validator(schema_path)
    state = PanelState()
    hub = Hub()
    app.state.panel_state = state
    app.state.hub = hub

    def error(status: int, *messages: str) -> JSONResponse:
        return JSONResponse({"ok": False, "errors": list(messages)}, status_code=status, headers=NO_STORE)

    @app.post("/api/panel")
    async def post_panel(request: Request) -> JSONResponse:
        body = await request.body()
        if len(body) > MAX_BODY:
            return error(413, "body too large (max 2 MB)")
        try:
            event = json.loads(body)
        except (ValueError, UnicodeDecodeError) as e:
            return error(400, f"invalid JSON body: {e}")
        errors = schema_errors(validator, event)
        if errors:
            log.warning("panel rejected: %s", " | ".join(errors[:3]))
            return error(400, *errors)
        if not state.apply(event):
            log.info("panel duplicate %s ignored", event["event_id"])
            return JSONResponse({"ok": True, "duplicate": True}, status_code=202, headers=NO_STORE)
        log.info("panel %s", _summary(event))
        await hub.broadcast({"kind": "event", "event": event})
        return JSONResponse({"ok": True}, status_code=202, headers=NO_STORE)

    @app.get("/api/state")
    async def get_state() -> JSONResponse:
        return JSONResponse({"events": state.events(), "role": state.role}, headers=NO_STORE)

    @app.get("/api/health")
    async def health() -> JSONResponse:
        return JSONResponse({"ok": True, "panel_clients": len(hub.clients), "terminal": "disabled"}, headers=NO_STORE)

    @app.post("/api/role")
    async def set_role(request: Request) -> JSONResponse:
        try:
            role = (await request.json()).get("role")
        except (ValueError, AttributeError, UnicodeDecodeError):
            return error(400, 'body must be JSON {"role": ...}')
        if role not in ROLES:
            return error(400, f"role must be one of {', '.join(ROLES)}")
        state.role = role
        await hub.broadcast({"kind": "role", "role": role})
        # No embedded terminal: the page copies /mcp__loglad__<role> for the presenter to paste into Claude.
        return JSONResponse({"ok": True, "role": role, "typed": False}, headers=NO_STORE)

    @app.post("/api/terminal/restart")
    async def restart_terminal() -> JSONResponse:
        return error(409, "terminal disabled: run claude in your own terminal next to this window")

    @app.websocket("/ws/panels")
    async def ws_panels(ws: WebSocket) -> None:
        await ws.accept()
        hub.clients.add(ws)
        try:
            await ws.send_text(json.dumps({"kind": "snapshot", "events": state.events(), "role": state.role}))
            while True:
                await ws.receive_text()  # clients don't send anything; this just waits for disconnect
        except WebSocketDisconnect:
            pass
        finally:
            hub.clients.discard(ws)

    @app.api_route("/api/{rest:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
    async def api_not_found(rest: str, request: Request) -> JSONResponse:
        return error(404, f"no route {request.method} /api/{rest}")

    root = web_root.resolve()

    @app.get("/{path:path}")
    async def page(path: str) -> Response:
        """Built page from dist/web; unknown paths fall back to index.html."""
        target = (root / path).resolve()
        if path and target.is_file() and root in target.parents:
            cache = "public, max-age=31536000, immutable" if "assets" in target.parts else "no-cache"
            return FileResponse(target, headers={"Cache-Control": cache})
        index = root / "index.html"
        if index.is_file():
            return FileResponse(index, headers={"Cache-Control": "no-cache"})
        return PlainTextResponse("Console page not built. Run `npm ci && npm run build` in console/.", status_code=503)

    return app
