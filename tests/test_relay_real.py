"""Real-Brave integration test for the CDP relay (marker ``desk``).

Launches an actual Brave window through the real ``BraveLauncher`` and
the full keeper FastAPI app -- exactly like ``tests/test_browsers_real.py``
-- then drives a live CDP exchange over the authenticated WebSocket
relay: ``Browser.getVersion`` and ``Target.createTarget``, the two
checks the Task 6 brief calls out by name.

Excluded from the default test run (``addopts = "-m 'not desk ...'"`` in
pyproject.toml); run explicitly with ``uv run pytest -m desk
tests/test_relay_real.py -q``.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from roost.config import RoostConfig
from roost.desk.signing import signed_headers
from roost.keeper.app import create_app

pytestmark = pytest.mark.desk

_SECRET = "z" * 32
_BOT_ID = "44444444-4444-4444-8444-444444444444"
_BRAVE_WARMUP_S = 1.5


@pytest.fixture
def config(tmp_path: Path) -> RoostConfig:
    return RoostConfig(
        server_secret="x" * 32,
        database_dir=tmp_path / "data",
        desks_dir=tmp_path / "desks",
        keeper_secret=_SECRET,
    )


@pytest.fixture
def client(config: RoostConfig):
    test_client = TestClient(create_app(config))
    try:
        yield test_client
    finally:
        stop_path = f"/desks/{_BOT_ID}/browser/stop"
        test_client.post(stop_path, headers=signed_headers(_SECRET, "POST", stop_path, b"{}"), content=b"{}")


def _start_browser_and_get_token(client: TestClient) -> str:
    path = f"/desks/{_BOT_ID}/browser/start"
    response = client.post(path, headers=signed_headers(_SECRET, "POST", path, b"{}"), content=b"{}")
    assert response.status_code == 200
    time.sleep(_BRAVE_WARMUP_S)  # give Brave a moment to finish starting before talking CDP
    return response.json()["cdp_token"]


def test_browser_get_version_round_trips_over_the_relay(client: TestClient):
    token = _start_browser_and_get_token(client)
    headers = {"x-roost-desk-token": token}

    with client.websocket_connect(f"/desks/{_BOT_ID}/cdp", headers=headers) as ws:
        ws.send_text(json.dumps({"id": 1, "method": "Browser.getVersion"}))
        reply = json.loads(ws.receive_text())
        assert "product" in reply.get("result", {})
        ws.close()
        time.sleep(0.2)


def test_target_create_target_returns_a_target_id(client: TestClient):
    token = _start_browser_and_get_token(client)
    headers = {"x-roost-desk-token": token}

    with client.websocket_connect(f"/desks/{_BOT_ID}/cdp", headers=headers) as ws:
        ws.send_text(
            json.dumps({"id": 1, "method": "Target.createTarget", "params": {"url": "about:blank"}})
        )
        reply = json.loads(ws.receive_text())
        assert "targetId" in reply.get("result", {})
        ws.close()
        time.sleep(0.2)
