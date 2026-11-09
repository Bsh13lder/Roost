"""The Computer tab's routes (S1.8): screenshots and Take control / Give it back."""

from __future__ import annotations

from fastapi.testclient import TestClient

from roost.gateway.app import create_app

O = {"Origin": "http://127.0.0.1:18800"}
AVATAR = {"shape": "round", "color": "#22c55e", "badge": "none"}


def _client_and_bot() -> tuple[TestClient, str]:
    c = TestClient(create_app())
    c.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=O)
    bot = c.post("/api/bots", json={"name": "Helper", "job": "helps", "instructions": "", "avatar": AVATAR},
                 headers=O).json()
    # the Mac Brave desk's screenshots; new bots default to the Linux computer
    assert c.patch(f"/api/bots/{bot['id']}", json={"computer": "mac_brave"}, headers=O).status_code == 200
    return c, bot["id"]


def test_viewing_a_sleeping_computer_says_so_and_never_starts_its_browser():
    c, bot_id = _client_and_bot()
    r = c.get(f"/api/bots/{bot_id}/desk/screenshot")
    assert (r.status_code, r.json()) == (409, {"detail": "asleep"})
    assert c.get(f"/api/bots/{bot_id}/desk").json()["browser"] == "stopped"


def test_a_running_computer_gives_a_jpeg_that_is_never_cached():
    c, bot_id = _client_and_bot()
    c.post(f"/api/bots/{bot_id}/desk/browser/start", headers=O)
    r = c.get(f"/api/bots/{bot_id}/desk/screenshot")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jpeg"
    assert r.headers["cache-control"] == "no-store"
    assert r.content.startswith(b"\xff\xd8")


def test_an_unreachable_computer_is_503():
    c, bot_id = _client_and_bot()
    c.app.state.desks.for_bot(bot_id).force_unavailable = True
    assert c.get(f"/api/bots/{bot_id}/desk/screenshot").status_code == 503


def test_take_control_and_give_it_back():
    c, bot_id = _client_and_bot()
    assert c.get(f"/api/bots/{bot_id}/control").json() == {"held": False, "since": None}
    taken = c.post(f"/api/bots/{bot_id}/control", headers=O).json()
    assert taken["held"] is True and taken["since"]
    assert c.get(f"/api/bots/{bot_id}/control").json()["held"] is True
    assert c.delete(f"/api/bots/{bot_id}/control", headers=O).json() == {"held": False, "since": None}


def test_control_needs_an_origin_and_an_owned_bot():
    c, bot_id = _client_and_bot()
    assert c.post(f"/api/bots/{bot_id}/control").status_code == 403
    assert c.post("/api/bots/not-a-bot/control", headers=O).status_code == 404
    assert c.get("/api/bots/not-a-bot/desk/screenshot").status_code == 404
