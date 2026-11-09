"""HTTP-level tests for the keeper app (``roost.keeper.app``).

Covers the three failure modes the Task 5 brief calls out explicitly
(unsigned -> 401, bad bot id -> 400, extra body field -> 422), plus replay
rejection and the browser start/stop happy path — all through a real
``BraveLauncher`` wired to a fake spawner, so nothing here ever touches a
real Brave process (that's ``tests/test_browsers_real.py``, marker
``desk``).

Note on the brief's literal ``../etc`` bad-bot-id example: Starlette
decodes ``%2F`` before route matching, so a bot id containing an actual
``/`` never reaches our handler at all — it 404s at the router, before our
400 validator runs (verified empirically against this FastAPI/Starlette
version; see the Task 5 report's Concerns). This file uses a slash-free
malformed id (``..etc``) to exercise the *validator*, and
``tests/test_keeper_paths.py`` separately proves a slash-bearing id can
never resolve outside ``desks_dir`` at the filesystem layer regardless of
how it arrives.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from roost.config import RoostConfig
from roost.desk.signing import signed_headers
from roost.keeper.app import create_app
from roost.keeper.browsers import BraveLauncher

_SECRET = "k" * 32
_VALID_BOT_ID = "77777777-7777-4777-8777-777777777777"


class _FakeSpawner:
    def __init__(self) -> None:
        self.calls = 0
        self._next_pid = 909090

    def __call__(self, path, argv, env, *, file_actions):
        self.calls += 1
        pid = self._next_pid
        self._next_pid += 1
        return pid


@pytest.fixture
def config(tmp_path: Path) -> RoostConfig:
    return RoostConfig(
        server_secret="x" * 32,
        database_dir=tmp_path / "data",
        desks_dir=tmp_path / "desks",
        keeper_secret=_SECRET,
    )


@pytest.fixture
def client(config: RoostConfig) -> TestClient:
    app = create_app(config)
    app.state.launcher = BraveLauncher(config, spawner=_FakeSpawner())
    return TestClient(app)


def _signed_request(client: TestClient, method: str, path: str, body: bytes = b"{}"):
    headers = signed_headers(_SECRET, method, path, body)
    return client.request(method, path, headers=headers, content=body)


def test_unsigned_request_is_rejected_401(client: TestClient):
    response = client.get(f"/desks/{_VALID_BOT_ID}")
    assert response.status_code == 401


def test_bad_bot_id_is_rejected_400(client: TestClient):
    path = "/desks/..etc"
    response = _signed_request(client, "GET", path, body=b"")
    assert response.status_code == 400


def test_extra_body_field_is_rejected_422(client: TestClient):
    path = f"/desks/{_VALID_BOT_ID}/browser/start"
    body = b'{"unexpected_field": 1}'
    response = _signed_request(client, "POST", path, body=body)
    assert response.status_code == 422


def test_replayed_request_is_rejected_401(client: TestClient):
    path = f"/desks/{_VALID_BOT_ID}"
    headers = signed_headers(_SECRET, "GET", path, b"")
    first = client.get(path, headers=headers)
    second = client.get(path, headers=headers)
    assert first.status_code == 200
    assert second.status_code == 401


def test_get_desk_status_when_nothing_running(client: TestClient):
    response = _signed_request(client, "GET", f"/desks/{_VALID_BOT_ID}", body=b"")
    assert response.status_code == 200
    assert response.json() == {"browser": "stopped", "workspace": "absent", "computer": "absent"}


def test_browser_start_then_status_then_stop(client: TestClient):
    start_path = f"/desks/{_VALID_BOT_ID}/browser/start"
    start_resp = _signed_request(client, "POST", start_path, body=b"{}")
    assert start_resp.status_code == 200
    start_body = start_resp.json()
    assert start_body["browser"] == "running"
    token = start_body["cdp_token"]
    assert isinstance(token, str) and len(token) >= 32

    status_resp = _signed_request(client, "GET", f"/desks/{_VALID_BOT_ID}", body=b"")
    assert status_resp.json()["browser"] == "running"

    stop_path = f"/desks/{_VALID_BOT_ID}/browser/stop"
    stop_resp = _signed_request(client, "POST", stop_path, body=b"{}")
    assert stop_resp.status_code == 200
    assert stop_resp.json() == {"browser": "stopped"}

    status_resp_2 = _signed_request(client, "GET", f"/desks/{_VALID_BOT_ID}", body=b"")
    assert status_resp_2.json()["browser"] == "stopped"


def test_browser_start_is_idempotent_returns_same_token(client: TestClient):
    start_path = f"/desks/{_VALID_BOT_ID}/browser/start"
    first = _signed_request(client, "POST", start_path, body=b"{}")
    second = _signed_request(client, "POST", start_path, body=b"{}")
    assert first.json()["cdp_token"] == second.json()["cdp_token"]


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_docs_routes_are_disabled_unreachable_even_unsigned(client: TestClient, path: str):
    # FastAPI's auto-docs routes must not be reachable without the shared
    # keeper_secret -- the module docstring promises nothing is. Hitting
    # them completely unsigned (no auth headers at all) must 404, not 200.
    response = client.get(path)
    assert response.status_code == 404


def test_browser_start_failure_is_a_clean_500_not_a_crash(config: RoostConfig):
    def failing_spawner(path, argv, env, *, file_actions):
        raise OSError("brave binary not found")

    app = create_app(config)
    app.state.launcher = BraveLauncher(config, spawner=failing_spawner)
    failing_client = TestClient(app)

    start_path = f"/desks/{_VALID_BOT_ID}/browser/start"
    response = _signed_request(failing_client, "POST", start_path, body=b"{}")
    assert response.status_code == 500
    assert "cdp_token" not in response.text


def test_browser_attach_never_starts_a_browser(client: TestClient):
    attach_path = f"/desks/{_VALID_BOT_ID}/browser/attach"
    assert _signed_request(client, "POST", attach_path, body=b"{}").status_code == 409
    assert _signed_request(client, "GET", f"/desks/{_VALID_BOT_ID}", body=b"").json()["browser"] == "stopped"
    started = _signed_request(client, "POST", f"/desks/{_VALID_BOT_ID}/browser/start", body=b"{}").json()
    attached = _signed_request(client, "POST", attach_path, body=b"{}")
    assert attached.json() == {"browser": "running", "cdp_token": started["cdp_token"]}
    _signed_request(client, "POST", f"/desks/{_VALID_BOT_ID}/browser/stop", body=b"{}")
    assert _signed_request(client, "POST", attach_path, body=b"{}").status_code == 409


def test_browser_attach_is_signed(client: TestClient):
    assert client.post(f"/desks/{_VALID_BOT_ID}/browser/attach", content=b"{}").status_code == 401
