"""Console API tests (FastAPI TestClient; no network, no build needed). Run: pytest console/tests"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make loglad_console importable from the repo root

from loglad_console.app import create_app, make_validator, schema_errors
from loglad_console.config import REPO_ROOT, read_settings

FIXTURES = REPO_ROOT / "contracts" / "fixtures" / "panel_events"
ALL = sorted(p.name for p in FIXTURES.glob("*.json"))


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    (tmp_path / "index.html").write_text("<!doctype html><title>console</title>", encoding="utf-8")
    return TestClient(create_app(web_root=tmp_path))


def post_all(client: TestClient, names: list[str]) -> None:
    for name in names:
        r = client.post("/api/panel", json={**fixture(name), "event_id": f"t-{name}"})
        assert r.status_code == 202, (name, r.text)


def test_seven_fixtures() -> None:
    assert len(ALL) == 7


@pytest.mark.parametrize("name", ALL)
def test_schema_accepts_fixture(name: str) -> None:
    assert schema_errors(make_validator(), fixture(name)) == []


def test_schema_rejects_broken_events() -> None:
    v = make_validator()
    ev = fixture("01_evidence_lines.json")
    ev["payload"]["receipt"]["receipt_id"] = "R-2"
    assert any("receipt_id" in e for e in schema_errors(v, ev))
    status = fixture("06_status.json")
    status["type"], status["extra"] = "banner", 1
    assert schema_errors(v, status)
    reset = fixture("07_reset.json")
    reset["payload"] = {"anything": True}
    assert schema_errors(v, reset)


def test_post_panel_and_state(client: TestClient) -> None:
    post_all(client, [n for n in ALL if not n.startswith("07")])
    state = client.get("/api/state").json()
    assert [e["type"] for e in state["events"]] == ["evidence"] * 4 + ["explainer", "status"]
    roles = [fixture(n)["role"] for n in ALL[:6] if fixture(n)["role"] != "unknown"]
    assert state["role"] == roles[-1]  # follows the latest event that names a role


def test_duplicate_is_ignored(client: TestClient) -> None:
    post_all(client, ["06_status.json"])
    r = client.post("/api/panel", json={**fixture("06_status.json"), "event_id": "t-06_status.json"})
    assert r.status_code == 202 and r.json() == {"ok": True, "duplicate": True}


def test_invalid_event_and_bad_json(client: TestClient) -> None:
    bad = fixture("02_evidence_table.json")
    del bad["payload"]["receipt"]
    r = client.post("/api/panel", json=bad)
    assert r.status_code == 400
    body = r.json()
    assert body["ok"] is False and body["errors"]
    r = client.post("/api/panel", content=b"{not json", headers={"Content-Type": "application/json"})
    assert r.status_code == 400


def test_websocket_snapshot_then_events(client: TestClient) -> None:
    post_all(client, ["01_evidence_lines.json", "05_explainer.json"])
    with client.websocket_connect("/ws/panels") as ws:
        snap = ws.receive_json()
        assert snap["kind"] == "snapshot" and len(snap["events"]) == 2
        client.post("/api/panel", json={**fixture("07_reset.json"), "event_id": "t-reset-1"})
        msg = ws.receive_json()
        assert msg["kind"] == "event" and msg["event"]["type"] == "reset"
        client.post("/api/role", json={"role": "team_lead"})
        assert ws.receive_json() == {"kind": "role", "role": "team_lead"}
    assert client.get("/api/state").json()["events"] == []


def test_history_keeps_20(client: TestClient) -> None:
    for i in range(25):
        client.post("/api/panel", json={**fixture("03_evidence_trend.json"), "event_id": f"t-hist-{i}"})
    assert len(client.get("/api/state").json()["events"]) == 20


def test_health_role_terminal(client: TestClient) -> None:
    assert client.get("/api/health").json() == {"ok": True, "panel_clients": 0, "terminal": "disabled"}
    assert client.post("/api/role", json={"role": "manager"}).json() == {"ok": True, "role": "manager", "typed": False}
    assert client.post("/api/role", json={"role": "ceo"}).status_code == 400
    assert client.post("/api/terminal/restart").status_code == 409
    assert client.get("/api/nope").status_code == 404


def test_page_and_spa_fallback(client: TestClient) -> None:
    assert "console" in client.get("/").text
    assert "console" in client.get("/some/deep/link").text
    assert client.get("/../../pyproject.toml").status_code in (200, 404)
    assert "loglad" not in client.get("/../../pyproject.toml").text


def test_settings_port() -> None:
    assert read_settings({}).port == 7777
    assert read_settings({"LOGLAD_CONSOLE_PORT": "8001"}).port == 8001
    assert read_settings({"LOGLAD_CONSOLE_PORT": "x"}).port == 7777


# ---------- embedded terminal (stdlib pty; Windows uses pywinpty and is tested by hand) ----------

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="POSIX pty test")


def read_until(ws, marker: str, limit: int = 200) -> str:
    seen = ""
    for _ in range(limit):
        msg = ws.receive_json()
        if msg.get("type") == "output":
            seen += msg["data"]
        if marker in seen:
            return seen
    raise AssertionError(f"{marker!r} not seen in terminal output: {seen[-500:]!r}")


def wait_for_type(ws, kind: str, limit: int = 200) -> dict:
    for _ in range(limit):
        msg = ws.receive_json()
        if msg.get("type") == kind:
            return msg
    raise AssertionError(f"no {kind!r} message")


@posix_only
def test_terminal_runs_startup_command_and_input(tmp_path: Path) -> None:
    from loglad_console.terminal import Terminal

    term = Terminal(enabled=True, shell="/bin/sh", startup_command="echo LADDER-$((40+2))")
    with TestClient(create_app(web_root=tmp_path, terminal=term)) as client:
        assert client.get("/api/health").json()["terminal"] == "running"
        with client.websocket_connect("/ws/terminal") as ws:
            read_until(ws, "LADDER-42")  # startup command ran in the shell
            ws.send_json({"type": "resize", "cols": 100, "rows": 30})
            ws.send_json({"type": "input", "data": "echo TYPED-$((1+1))\r"})
            read_until(ws, "TYPED-2")
            assert client.post("/api/role", json={"role": "engineer"}).json()["typed"] is True
            read_until(ws, "/mcp__loglad__engineer")  # Ctrl+C, then the command is typed and run
            ws.send_json({"type": "input", "data": "exit 0\r"})
            assert wait_for_type(ws, "exit")["code"] == 0
        assert client.get("/api/health").json()["terminal"] == "exited"
        assert client.post("/api/terminal/restart").json() == {"ok": True, "terminal": "running"}


def test_terminal_off_reports_disabled(tmp_path: Path) -> None:
    from loglad_console.terminal import Terminal

    with TestClient(create_app(web_root=tmp_path, terminal=Terminal(enabled=False))) as client:
        with client.websocket_connect("/ws/terminal") as ws:
            assert ws.receive_json() == {"type": "disabled", "reason": "LOGLAD_TERMINAL=off"}
        assert client.post("/api/terminal/restart").status_code == 409
        assert client.post("/api/role", json={"role": "manager"}).json()["typed"] is False
