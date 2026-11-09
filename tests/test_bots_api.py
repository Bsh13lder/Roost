"""Contract tests for the bots HTTP API — ``roost/gateway/routes/bots.py``.

Per the brief: create -> 201; duplicate -> 409; invalid color/name -> 422;
list shows only own bots; a second user's GET/PATCH/DELETE on the first
user's bot -> 404; DELETE -> 204 then GET -> 404.

Roost's registration endpoint closes itself after the first account ever
exists (single-account contract rule), so there is no HTTP path to create
a second account through the public API. The "second user" tests below
instead create that second account the same way ``tests/test_bot_store.py``
does — calling ``register_user`` directly — then log in as them over
HTTP, same as a real second account would. Those tests run as native
coroutines using ``httpx.AsyncClient`` over an ASGI transport (sharing one
event loop with the direct ``register_user`` call) rather than
``fastapi.testclient.TestClient``, which drives its own background-thread
event loop — mixing the two would hand the DB connection pool a
connection built on one loop and awaited from another.
"""

from __future__ import annotations

import asyncio
import logging

import httpx
from fastapi.testclient import TestClient

from roost.config import load_config
from roost.db.connection import init_db
from roost.gateway.app import create_app
from roost.gateway.auth import register_user

O = {"Origin": "http://127.0.0.1:18800"}
BAD_O = {"Origin": "http://evil.example"}

VALID_AVATAR = {"shape": "round", "color": "#22c55e", "badge": "none"}


def _register(client: TestClient, username: str) -> None:
    r = client.post("/api/auth/register", json={"username": username, "password": "pw-123456"}, headers=O)
    assert r.status_code in (201, 403)
    if r.status_code == 403:
        client.post("/api/auth/login", json={"username": username, "password": "pw-123456"}, headers=O)


def _bot_body(name: str = "Scout", **overrides) -> dict:
    body = {"name": name, "job": "read news", "instructions": "be brief", "avatar": VALID_AVATAR}
    body.update(overrides)
    return body


async def _async_client_as(app, username: str) -> httpx.AsyncClient:
    """Register ``username`` directly (bypassing the closed-registration
    HTTP gate, like a pre-existing second account would), then log them
    in over HTTP on a fresh async client against ``app``."""
    cfg = load_config()
    await init_db(cfg)
    await register_user(cfg, username, "pw-123456")
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test")
    r = await client.post("/api/auth/login", json={"username": username, "password": "pw-123456"}, headers=O)
    assert r.status_code == 200
    return client


def test_create_bot_201_with_expected_shape():
    c = TestClient(create_app())
    _register(c, "alice")
    r = c.post("/api/bots", json=_bot_body(), headers=O)
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "Scout"
    assert body["status"] == "resting"
    assert body["activity"] is None
    assert body["avatar"] == {**VALID_AVATAR, "screen": "glow", "picture": None}
    assert body["off_duty"] is False
    assert set(body) == {
        "id", "name", "job", "instructions", "avatar", "template_id",
        "status", "activity", "model_override", "created_at", "updated_at", "off_duty", "is_primary", "notify",
        "roles", "approval", "group", "pinned", "pinned_at", "model", "model_label", "effort", "computer", "full_limit_until", "workspace_internet", "voice",
    }
    assert body["group"] is None


def test_create_duplicate_name_is_409():
    c = TestClient(create_app())
    _register(c, "alice")
    c.post("/api/bots", json=_bot_body(name="Scout"), headers=O)
    r = c.post("/api/bots", json=_bot_body(name="SCOUT"), headers=O)
    assert r.status_code == 409


def test_create_invalid_color_is_422():
    c = TestClient(create_app())
    _register(c, "alice")
    r = c.post("/api/bots", json=_bot_body(avatar={"shape": "round", "color": "not-a-color", "badge": "none"}), headers=O)
    assert r.status_code == 422


def test_create_invalid_name_is_422():
    c = TestClient(create_app())
    _register(c, "alice")
    r = c.post("/api/bots", json=_bot_body(name=""), headers=O)
    assert r.status_code == 422


def test_create_without_allowed_origin_is_403():
    c = TestClient(create_app())
    _register(c, "alice")
    r = c.post("/api/bots", json=_bot_body(), headers=BAD_O)
    assert r.status_code == 403


async def test_list_shows_only_own_bots():
    app = create_app()
    alice = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test")
    await alice.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=O)
    await alice.post("/api/bots", json=_bot_body(name="Scout"), headers=O)

    bob = await _async_client_as(app, "bob")
    await bob.post("/api/bots", json=_bot_body(name="Helper"), headers=O)

    bobs_bots = (await bob.get("/api/bots")).json()
    assert [b["name"] for b in bobs_bots if not b["is_primary"]] == ["Helper"]

    alices_bots = (await alice.get("/api/bots")).json()
    assert [b["name"] for b in alices_bots if not b["is_primary"]] == ["Scout"]

    await alice.aclose()
    await bob.aclose()


def test_get_update_delete_round_trip():
    c = TestClient(create_app())
    _register(c, "alice")
    bot_id = c.post("/api/bots", json=_bot_body(), headers=O).json()["id"]

    r = c.get(f"/api/bots/{bot_id}")
    assert r.status_code == 200 and r.json()["name"] == "Scout"

    r = c.patch(f"/api/bots/{bot_id}", json={"job": "read more news"}, headers=O)
    assert r.status_code == 200 and r.json()["job"] == "read more news"
    assert r.json()["name"] == "Scout"  # untouched fields preserved

    r = c.delete(f"/api/bots/{bot_id}", headers=O)
    assert r.status_code == 204

    assert c.get(f"/api/bots/{bot_id}").status_code == 404


async def test_other_users_bot_id_is_404_for_get_patch_delete():
    app = create_app()
    alice = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test")
    await alice.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=O)
    bot_id = (await alice.post("/api/bots", json=_bot_body(), headers=O)).json()["id"]

    bob = await _async_client_as(app, "bob")

    assert (await bob.get(f"/api/bots/{bot_id}")).status_code == 404
    assert (await bob.patch(f"/api/bots/{bot_id}", json={"name": "Hijacked"}, headers=O)).status_code == 404
    assert (await bob.delete(f"/api/bots/{bot_id}", headers=O)).status_code == 404

    await alice.aclose()
    await bob.aclose()


def test_get_unknown_bot_is_404():
    c = TestClient(create_app())
    _register(c, "alice")
    assert c.get("/api/bots/does-not-exist").status_code == 404


def test_update_to_duplicate_name_is_409():
    c = TestClient(create_app())
    _register(c, "alice")
    c.post("/api/bots", json=_bot_body(name="Scout"), headers=O)
    other_id = c.post("/api/bots", json=_bot_body(name="Helper"), headers=O).json()["id"]

    r = c.patch(f"/api/bots/{other_id}", json={"name": "SCOUT"}, headers=O)
    assert r.status_code == 409


def test_update_without_allowed_origin_is_403():
    c = TestClient(create_app())
    _register(c, "alice")
    bot_id = c.post("/api/bots", json=_bot_body(), headers=O).json()["id"]
    r = c.patch(f"/api/bots/{bot_id}", json={"name": "New"}, headers=BAD_O)
    assert r.status_code == 403


def test_delete_without_allowed_origin_is_403():
    c = TestClient(create_app())
    _register(c, "alice")
    bot_id = c.post("/api/bots", json=_bot_body(), headers=O).json()["id"]
    r = c.delete(f"/api/bots/{bot_id}", headers=BAD_O)
    assert r.status_code == 403


def test_bots_routes_require_auth():
    c = TestClient(create_app())
    assert c.get("/api/bots").status_code == 401
    assert c.post("/api/bots", json=_bot_body(), headers=O).status_code == 401


def test_delete_bot_retires_its_desk():
    """Contract: "Retire this bot" (spec vocabulary) — deleting a bot
    must also retire its desk (stop the browser, remove the workspace
    container, delete the desk directory), not just the DB row. Task 13's
    real-desk smoke proves this against a real keeper; this is the
    FakeDesk-level contract test."""
    app = create_app()
    c = TestClient(app)
    _register(c, "alice")
    bot_id = c.post("/api/bots", json=_bot_body(), headers=O).json()["id"]

    # Touch the desk once before deleting, same as a real run would (the
    # bot's browser was started at some point) -- proves retire() really
    # runs against the SAME desk instance a live bot would have used,
    # not a freshly-constructed one that happens to start out "retired".
    # Captured BEFORE delete: final review, finding 5 makes delete_bot
    # forget the cache entry right after retiring, so re-fetching
    # app.state.desks.for_bot(bot_id) AFTER delete now legitimately
    # builds a brand new (never-retired) instance instead.
    c.post(f"/api/bots/{bot_id}/desk/browser/start", headers=O)
    desk = app.state.desks.for_bot(bot_id)

    r = c.delete(f"/api/bots/{bot_id}", headers=O)
    assert r.status_code == 204

    assert desk.retired is True


def test_delete_bot_succeeds_even_when_desk_retire_is_unavailable():
    """A keeper that's down must not block deleting the bot's own
    record -- the DB row is the source of truth for "does this bot
    exist", desk cleanup is best-effort."""
    from roost.desk.fake import FakeDesk

    class _StubDeskFactory:
        def __init__(self, desk) -> None:
            self._desk = desk

        def for_bot(self, bot_id: str, computer: str = "mac_brave"):
            return self._desk

        def forget(self, bot_id: str) -> None:
            pass

    app = create_app()
    c = TestClient(app)
    _register(c, "alice")
    bot_id = c.post("/api/bots", json=_bot_body(), headers=O).json()["id"]
    app.state.desks = _StubDeskFactory(FakeDesk(bot_id, force_unavailable=True))

    r = c.delete(f"/api/bots/{bot_id}", headers=O)
    assert r.status_code == 204
    assert c.get(f"/api/bots/{bot_id}").status_code == 404


def test_delete_bot_logs_when_desk_retire_is_unavailable(caplog):
    """Fix round 1, finding 2: the DeskUnavailable fallback above is
    best-effort for the HTTP response, but it must not be silent -- a
    keeper that's unreachable here leaves a Brave profile and a
    workspace container running with nothing anywhere to say so, unless
    a warning is logged for an operator to find."""
    from roost.desk.fake import FakeDesk

    class _StubDeskFactory:
        def __init__(self, desk) -> None:
            self._desk = desk

        def for_bot(self, bot_id: str, computer: str = "mac_brave"):
            return self._desk

        def forget(self, bot_id: str) -> None:
            pass

    app = create_app()
    c = TestClient(app)
    _register(c, "alice")
    bot_id = c.post("/api/bots", json=_bot_body(), headers=O).json()["id"]
    app.state.desks = _StubDeskFactory(FakeDesk(bot_id, force_unavailable=True))

    with caplog.at_level(logging.WARNING, logger="roost.gateway.routes.bots"):
        r = c.delete(f"/api/bots/{bot_id}", headers=O)
    assert r.status_code == 204

    warnings = [rec for rec in caplog.records if rec.levelno == logging.WARNING]
    assert any(bot_id in rec.getMessage() for rec in warnings), (
        f"expected a WARNING log mentioning {bot_id!r}, got: {[r.getMessage() for r in caplog.records]}"
    )


# ---------------------------------------------------------------------------
# Final review, finding 5: retiring a bot stops its running turn and
# never lets this process reuse its desk afterward.
# ---------------------------------------------------------------------------

def test_delete_bot_cancels_any_running_turn_before_retiring_the_desk():
    """A turn that's still ``on_it`` when the user retires the bot must
    be stopped BEFORE the desk is retired -- otherwise that turn's next
    CDP call can race the retire, and (per KeeperDesk's own `retired`
    flag, tested directly in ``test_keeper_client.py``) relaunch a
    browser for a bot that's already gone."""
    app = create_app()
    c = TestClient(app)
    _register(c, "alice")
    bot_id = c.post("/api/bots", json=_bot_body(), headers=O).json()["id"]

    call_order: list[str] = []

    class _RecordingTurns:
        async def cancel(self, cancelled_bot_id: str) -> None:
            assert cancelled_bot_id == bot_id
            call_order.append("cancel")

    desk = app.state.desks.for_bot(bot_id)
    original_retire = desk.retire

    async def _recording_retire() -> None:
        call_order.append("retire")
        await original_retire()

    desk.retire = _recording_retire
    app.state.turns = _RecordingTurns()

    r = c.delete(f"/api/bots/{bot_id}", headers=O)
    assert r.status_code == 204
    assert call_order == ["cancel", "retire"]


def test_delete_bot_forgets_the_desk_so_a_new_one_is_built():
    """Nothing in this process may go on reusing a ``Desk`` instance for
    a bot id that's already gone -- ``DeskFactory.forget`` (tested
    directly in ``test_desk_api.py``) is called right after retire."""
    app = create_app()
    c = TestClient(app)
    _register(c, "alice")
    bot_id = c.post("/api/bots", json=_bot_body(), headers=O).json()["id"]
    first_desk = app.state.desks.for_bot(bot_id)

    r = c.delete(f"/api/bots/{bot_id}", headers=O)
    assert r.status_code == 204

    second_desk = app.state.desks.for_bot(bot_id)
    assert second_desk is not first_desk


# ---------------------------------------------------------------------------
# Final review, finding 6: the contract's `bot_removed` frame is never
# published -- a live client's sidebar never drops a retired bot.
# ---------------------------------------------------------------------------

async def test_delete_bot_publishes_bot_removed():
    app = create_app()
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test")
    await client.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=O)
    bot_id = (await client.post("/api/bots", json=_bot_body(), headers=O)).json()["id"]
    user_id = (await client.get("/api/auth/me", headers=O)).json()["id"]

    sub = app.state.events.subscribe(user_id)
    try:
        r = await client.delete(f"/api/bots/{bot_id}", headers=O)
        assert r.status_code == 204

        frame = await asyncio.wait_for(sub.__anext__(), timeout=2)
        assert frame["type"] == "bot_removed"
        assert frame["bot_id"] == bot_id
    finally:
        sub.close()
        await client.aclose()


async def test_create_bot_publishes_bot_updated_for_the_new_bot():
    # The live store only knows bots from its connect-time snapshot; without
    # a frame, a bot made later never gets its live status in the web face.
    app = create_app()
    client = await _async_client_as(app, "alice")
    try:
        me = (await client.get("/api/auth/me")).json()
        sub = app.state.events.subscribe(me["id"])
        created = (await client.post("/api/bots", json=_bot_body("Ledger"), headers=O)).json()
        frame = await asyncio.wait_for(sub.__anext__(), timeout=1)
        sub.close()
    finally:
        await client.aclose()
    assert frame["type"] == "bot_updated"
    assert frame["bot"] == created


def test_a_job_on_two_lines_is_422():
    c = TestClient(create_app())
    _register(c, "alice")
    assert c.post("/api/bots", json=_bot_body("Mole", job="a\nb"), headers=O).status_code == 422


async def test_patching_a_bot_publishes_bot_updated():
    app = create_app()
    client = await _async_client_as(app, "alice")
    created = (await client.post("/api/bots", json=_bot_body("Scout"), headers=O)).json()
    me = (await client.get("/api/auth/me")).json()["id"]
    subscription = app.state.events.subscribe(me)
    await client.patch(f"/api/bots/{created['id']}", json={"name": "Scout Two"}, headers=O)
    from team_helpers import frames_so_far
    assert any(f["type"] == "bot_updated" and f["bot"]["name"] == "Scout Two" for f in await frames_so_far(subscription))
    subscription.close()
    await client.aclose()


def test_patch_sets_keeps_and_clears_a_group():
    c = TestClient(create_app())
    _register(c, "alice")
    bot_id = c.post("/api/bots", json=_bot_body(), headers=O).json()["id"]
    url = f"/api/bots/{bot_id}"
    assert c.patch(url, json={"group": "Home"}, headers=O).json()["group"] == "Home"
    assert c.patch(url, json={"name": "Scout2"}, headers=O).json()["group"] == "Home"
    assert c.patch(url, json={"group": ""}, headers=O).json()["group"] is None
    assert c.patch(url, json={"group": " Work "}, headers=O).json()["group"] == "Work"
    assert c.patch(url, json={"group": None}, headers=O).json()["group"] is None


def test_a_group_must_fit_on_one_line_and_be_short():
    c = TestClient(create_app())
    _register(c, "alice")
    bot_id = c.post("/api/bots", json=_bot_body(), headers=O).json()["id"]
    url = f"/api/bots/{bot_id}"
    assert c.patch(url, json={"group": "a\nb"}, headers=O).status_code == 422
    assert c.patch(url, json={"group": "x" * 31}, headers=O).status_code == 422
    assert c.patch(url, json={"group": "x" * 30}, headers=O).status_code == 200


async def test_another_users_bot_cannot_be_labelled():
    app = create_app()
    alice = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test")
    await alice.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=O)
    bot_id = (await alice.post("/api/bots", json=_bot_body(), headers=O)).json()["id"]
    bob = await _async_client_as(app, "bob")

    assert (await bob.patch(f"/api/bots/{bot_id}", json={"group": "Mine now"}, headers=O)).status_code == 404
    assert (await alice.get(f"/api/bots/{bot_id}")).json()["group"] is None

    await alice.aclose()
    await bob.aclose()


async def test_patching_a_group_publishes_bot_updated_with_it():
    app = create_app()
    client = await _async_client_as(app, "alice")
    created = (await client.post("/api/bots", json=_bot_body("Scout"), headers=O)).json()
    me = (await client.get("/api/auth/me")).json()["id"]
    subscription = app.state.events.subscribe(me)
    await client.patch(f"/api/bots/{created['id']}", json={"group": "Home"}, headers=O)
    from team_helpers import frames_so_far
    assert any(f["type"] == "bot_updated" and f["bot"]["group"] == "Home" for f in await frames_so_far(subscription))
    await client.aclose()


def test_a_new_bot_is_unpinned_and_the_main_bot_counts_as_pinned():
    c = TestClient(create_app())
    _register(c, "alice")
    bot = c.post("/api/bots", json=_bot_body(), headers=O).json()
    assert bot["pinned"] is False and bot["pinned_at"] is None
    main = next(b for b in c.get("/api/bots").json() if b["is_primary"])
    assert main["pinned"] is True


def test_pin_and_unpin_a_bot_in_pin_order():
    c = TestClient(create_app())
    _register(c, "alice")
    first = c.post("/api/bots", json=_bot_body(name="First"), headers=O).json()["id"]
    second = c.post("/api/bots", json=_bot_body(name="Second"), headers=O).json()["id"]

    one = c.put(f"/api/bots/{second}/pin", json={"pinned": True}, headers=O)
    assert one.status_code == 200 and one.json()["pinned"] is True and one.json()["pinned_at"]
    c.put(f"/api/bots/{first}/pin", json={"pinned": True}, headers=O)
    again = c.put(f"/api/bots/{second}/pin", json={"pinned": True}, headers=O).json()
    assert again["pinned_at"] == one.json()["pinned_at"]   # pinning twice keeps its place
    pinned = sorted((b for b in c.get("/api/bots").json() if b["pinned_at"]), key=lambda b: b["pinned_at"])
    assert [b["id"] for b in pinned] == [second, first]

    off = c.put(f"/api/bots/{second}/pin", json={"pinned": False}, headers=O).json()
    assert off["pinned"] is False and off["pinned_at"] is None


def test_pin_needs_the_origin_and_a_boolean():
    c = TestClient(create_app())
    _register(c, "alice")
    bot_id = c.post("/api/bots", json=_bot_body(), headers=O).json()["id"]
    url = f"/api/bots/{bot_id}/pin"
    assert c.put(url, json={"pinned": True}, headers=BAD_O).status_code == 403
    assert c.put(url, json={"pinned": "yes please"}, headers=O).status_code == 422
    assert c.put(url, json={"pinned": True, "x": 1}, headers=O).status_code == 422
    assert c.put("/api/bots/nope/pin", json={"pinned": True}, headers=O).status_code == 404


async def test_another_users_bot_cannot_be_pinned():
    app = create_app()
    alice = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test")
    await alice.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=O)
    bot_id = (await alice.post("/api/bots", json=_bot_body(), headers=O)).json()["id"]
    bob = await _async_client_as(app, "bob")

    assert (await bob.put(f"/api/bots/{bot_id}/pin", json={"pinned": True}, headers=O)).status_code == 404
    assert (await alice.get(f"/api/bots/{bot_id}")).json()["pinned"] is False

    await alice.aclose()
    await bob.aclose()


def test_a_new_bot_reports_linux_and_patch_switches_it():
    c = TestClient(create_app())
    _register(c, "alice")
    bot = c.post("/api/bots", json=_bot_body(), headers=O).json()
    assert bot["computer"] == "linux"
    r = c.patch(f"/api/bots/{bot['id']}", json={"computer": "mac_brave"}, headers=O)
    assert (r.status_code, r.json()["computer"]) == (200, "mac_brave")
    kept = c.patch(f"/api/bots/{bot['id']}", json={"job": "other"}, headers=O).json()
    assert kept["computer"] == "mac_brave"
    assert c.get(f"/api/bots/{bot['id']}").json()["computer"] == "mac_brave"


def test_an_unknown_computer_kind_is_a_422():
    c = TestClient(create_app())
    _register(c, "alice")
    bot = c.post("/api/bots", json=_bot_body(), headers=O).json()
    for kind in ("windows", ""):
        assert c.patch(f"/api/bots/{bot['id']}", json={"computer": kind}, headers=O).status_code == 422
    assert c.get(f"/api/bots/{bot['id']}").json()["computer"] == "linux"


async def test_another_users_bot_cannot_switch_its_computer():
    app = create_app()
    alice = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test")
    await alice.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=O)
    bot_id = (await alice.post("/api/bots", json=_bot_body(), headers=O)).json()["id"]
    bob = await _async_client_as(app, "bob")
    assert (await bob.patch(f"/api/bots/{bot_id}", json={"computer": "mac_brave"}, headers=O)).status_code == 404
    assert (await alice.get(f"/api/bots/{bot_id}")).json()["computer"] == "linux"
    await alice.aclose()
    await bob.aclose()


def test_the_bot_updated_frame_carries_the_computer_kind():
    app = create_app()
    c = TestClient(app)
    _register(c, "alice")
    bot = c.post("/api/bots", json=_bot_body(), headers=O).json()
    seen: list[dict] = []
    publish = app.state.events.publish

    async def spy(user_id, frame):
        seen.append(frame)
        return await publish(user_id, frame)

    app.state.events.publish = spy
    c.patch(f"/api/bots/{bot['id']}", json={"computer": "linux"}, headers=O)
    assert [f["bot"]["computer"] for f in seen if f["type"] == "bot_updated"] == ["linux"]
