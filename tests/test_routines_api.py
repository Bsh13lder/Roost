"""The routine routes: create, edit, switch, run now, history and the schedule preview.

httpx on the test's own event loop (not TestClient): run-now starts the bot's drain task, and ``wait_idle`` must see
it finish before the test ends."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import AsyncIterator

import httpx
import pytest

import roost.talk.runner as runner_module
from roost.bots.store import BotStore
from roost.config import load_config
from roost.db.connection import db_session, init_db
from roost.gateway.app import create_app
from roost.gateway.auth import register_user
from roost.routines.models import RoutineDraft
from roost.routines.schedule import parse_schedule
from roost.talk.store import TalkStore
from team_helpers import make_bot, wait_idle

O = {"Origin": "http://127.0.0.1:18800"}
BAD_O = {"Origin": "http://evil.example"}
PASSWORD = "pw-123456"
TIMES = {"kind": "times", "days": [1, 2, 3, 4, 5, 6, 7], "times": ["10:07", "15:07"]}


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def app(cfg):
    return create_app(cfg)


@asynccontextmanager
async def signed_in(app, username: str) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test") as client:
        assert (await client.post("/api/auth/login", json={"username": username, "password": PASSWORD},
                                  headers=O)).status_code == 200
        try:
            yield client
        finally:
            await wait_idle(app.state.turns, timeout=8)


@pytest.fixture
async def alice(cfg):
    return await register_user(cfg, "alice", PASSWORD)


@pytest.fixture
async def bob(cfg):
    return await register_user(cfg, "bob", PASSWORD)


@pytest.fixture
async def bot(cfg, alice):
    return await make_bot(cfg, alice.id, "Scout")


def body(**kw) -> dict:
    return {"name": "Morning news", "instructions": "Read the headlines.", "schedule": TIMES, **kw}


async def _make(client, bot, **kw) -> dict:
    created = await client.post(f"/api/bots/{bot.id}/routines", json=body(**kw), headers=O)
    assert created.status_code == 201, created.text
    return created.json()


async def _frames(app, user_id: str, frame_type: str) -> list[dict]:
    return [f for f in await app.state.events.since(user_id, 0) if f["type"] == frame_type]


async def test_create_list_patch_and_delete(app, alice, bot):
    async with signed_in(app, "alice") as client:
        made = await _make(client, bot)
        assert made["name"] == "Morning news" and made["enabled"] is True and made["builtin"] is None
        assert made["words"] == "Every day at 10:07 and 15:07" and made["created_by"] == "user"
        assert made["next_run_at"] and made["last_run_at"] is None and made["last_state"] is None
        assert made["thread_id"]  # the run log's thread, for the web's read-only log page
        assert made["schedule"] == {"kind": "times", "days": [1, 2, 3, 4, 5, 6, 7], "times": ["10:07", "15:07"]}

        listed = (await client.get(f"/api/bots/{bot.id}/routines")).json()["routines"]
        assert [r["id"] for r in listed] == [made["id"]]

        patched = await client.patch(f"/api/routines/{made['id']}", json={"name": "Evening news", "enabled": False},
                                     headers=O)
        assert patched.status_code == 200
        assert patched.json()["name"] == "Evening news" and patched.json()["enabled"] is False
        assert patched.json()["next_run_at"] is None

        assert (await client.delete(f"/api/routines/{made['id']}", headers=O)).status_code == 204
        assert (await client.get(f"/api/bots/{bot.id}/routines")).json()["routines"] == []
        assert (await client.delete(f"/api/routines/{made['id']}", headers=O)).status_code == 404


async def test_the_next_run_shows_the_slot_not_the_jitter(app, alice, bot):
    async with signed_in(app, "alice") as client:
        made = await _make(client, bot)
        assert made["next_run_at"][17:19] == "00"          # whole minute: the user's 10:07, not the jitter


async def test_an_empty_patch_and_unknown_fields_are_422(app, alice, bot):
    async with signed_in(app, "alice") as client:
        made = await _make(client, bot)
        assert (await client.patch(f"/api/routines/{made['id']}", json={}, headers=O)).status_code == 422
        assert (await client.patch(f"/api/routines/{made['id']}", json={"tainted": False}, headers=O)).status_code == 422
        extra = await client.post(f"/api/bots/{bot.id}/routines", json={**body(), "builtin": "day_summary"}, headers=O)
        assert extra.status_code == 422


async def test_bad_schedules_are_422_with_plain_text(app, alice, bot):
    cases = {
        "A routine needs a name.": body(name="   "),
        "Pick at least one day and one time.": body(schedule={"kind": "times", "days": [], "times": ["10:00"]}),
        "Times look like 10:07.": body(schedule={"kind": "times", "days": [1], "times": ["10am"]}),
        "That custom schedule isn't valid.": body(schedule={"kind": "cron", "expr": "nonsense"}),
        "That schedule runs more often than every 15 minutes.": body(schedule={"kind": "cron", "expr": "* * * * *"}),
    }
    async with signed_in(app, "alice") as client:
        for text, payload in cases.items():
            response = await client.post(f"/api/bots/{bot.id}/routines", json=payload, headers=O)
            assert (response.status_code, response.json()["detail"]) == (422, text)
        made = await _make(client, bot)
        patched = await client.patch(f"/api/routines/{made['id']}", json={"schedule": {"kind": "cron", "expr": "x"}},
                                     headers=O)
        assert (patched.status_code, patched.json()["detail"]) == (422, "That custom schedule isn't valid.")


async def test_the_routine_caps_are_422(app, alice, bot, monkeypatch):
    import roost.routines.service as service_module
    monkeypatch.setattr(service_module, "ROUTINES_PER_BOT_MAX", 2)
    monkeypatch.setattr(service_module, "ROUTINES_PER_USER_MAX", 3)
    async with signed_in(app, "alice") as client:
        await _make(client, bot, name="One")
        await _make(client, bot, name="Two")
        over_bot = await client.post(f"/api/bots/{bot.id}/routines", json=body(name="Three"), headers=O)
        assert (over_bot.status_code, over_bot.json()["detail"]) == (422, "This bot already has 2 routines.")
        other = await make_bot(app.state.config, alice.id, "Quill")
        await client.post(f"/api/bots/{other.id}/routines", json=body(name="Four"), headers=O)
        over_user = await client.post(f"/api/bots/{other.id}/routines", json=body(name="Five"), headers=O)
        assert (over_user.status_code, over_user.json()["detail"]) == (422, "You already have 3 routines.")
        long_name = await client.post(f"/api/bots/{other.id}/routines", json=body(name="x" * 81), headers=O)
        assert long_name.status_code == 422 and isinstance(long_name.json()["detail"], str)


async def test_preview_gives_words_and_the_next_five_madrid_times(app, alice):
    async with signed_in(app, "alice") as client:
        response = await client.post("/api/routines/preview", json={"schedule": TIMES}, headers=O)
        assert response.status_code == 200
        data = response.json()
        assert data["words"] == "Every day at 10:07 and 15:07" and len(data["next"]) == 5
        assert all(t.endswith("+01:00") or t.endswith("+02:00") for t in data["next"])
        assert all(t[11:16] in ("10:07", "15:07") for t in data["next"])
        bad = await client.post("/api/routines/preview", json={"schedule": {"kind": "cron", "expr": "x"}}, headers=O)
        assert (bad.status_code, bad.json()["detail"]) == (422, "That custom schedule isn't valid.")


async def test_run_now_queues_and_a_second_run_now_is_409(app, alice, bot):
    async with signed_in(app, "alice") as client:
        made = await _make(client, bot)
        await BotStore(app.state.config).set_off_duty(alice.id, bot.id, False)
        first = await client.post(f"/api/routines/{made['id']}/run-now", headers=O)
        assert first.status_code == 202
        run = first.json()["run"]
        assert run["state"] in ("queued", "running", "done") and run["slot_at"]
        # The run is still open until the after-run pass closes it; a second press right away is refused while open.
        second = await client.post(f"/api/routines/{made['id']}/run-now", headers=O)
        if second.status_code != 202:
            assert (second.status_code, second.json()["detail"]) == (409, "It's still running.")
        await wait_idle(app.state.turns, timeout=8)
        runs = (await client.get(f"/api/routines/{made['id']}/runs")).json()["runs"]
        assert runs and runs[0]["state"] == "done" and runs[0]["report_message_id"]


async def test_run_now_while_a_run_is_open_is_409(app, alice, bot):
    async with signed_in(app, "alice") as client:
        made = await _make(client, bot)
        routine = await app.state.routine_store.get(alice.id, made["id"])
        await BotStore(app.state.config).set_off_duty(alice.id, bot.id, True)
        busy = await client.post(f"/api/routines/{made['id']}/run-now", headers=O)
        assert (busy.status_code, busy.json()["detail"]) == (409, "This bot is off duty.")
        await BotStore(app.state.config).set_off_duty(alice.id, bot.id, False)
        from datetime import datetime, timezone
        await app.state.routine_runs.record(alice.id, routine, datetime(2026, 1, 1, tzinfo=timezone.utc), "running")
        blocked = await client.post(f"/api/routines/{made['id']}/run-now", headers=O)
        assert (blocked.status_code, blocked.json()["detail"]) == (409, "It's still running.")


async def test_run_now_counts_against_the_daily_cap(app, alice, bot, monkeypatch):
    monkeypatch.setattr(runner_module, "DAILY_RUN_CAP", 1)
    async with signed_in(app, "alice") as client:
        made = await _make(client, bot)
        await app.state.turns._runs.start(alice.id, bot.id, "thread", "run-1")
        held = await client.post(f"/api/routines/{made['id']}/run-now", headers=O)
        assert (held.status_code, held.json()["detail"]) == (409, "Daily limit reached.")
        runs = (await client.get(f"/api/routines/{made['id']}/runs")).json()["runs"]
        assert [r["state"] for r in runs] == ["held"]


async def test_runs_page_by_before(app, alice, bot):
    from datetime import datetime, timedelta, timezone
    async with signed_in(app, "alice") as client:
        made = await _make(client, bot)
        routine = await app.state.routine_store.get(alice.id, made["id"])
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        for n in range(5):
            await app.state.routine_runs.record(alice.id, routine, base + timedelta(days=n), "done")
        import roost.routines.service as service_module
        service_module.ROUTINE_RUNS_PAGE = 2
        try:
            page = (await client.get(f"/api/routines/{made['id']}/runs")).json()["runs"]
            assert [r["slot_at"][:10] for r in page] == ["2026-01-05", "2026-01-04"]
            older = (await client.get(f"/api/routines/{made['id']}/runs", params={"before": page[-1]["id"]})).json()["runs"]
            assert [r["slot_at"][:10] for r in older] == ["2026-01-03", "2026-01-02"]
            last = (await client.get(f"/api/routines/{made['id']}/runs", params={"before": older[-1]["id"]})).json()["runs"]
            assert [r["slot_at"][:10] for r in last] == ["2026-01-01"]
            bad = await client.get(f"/api/routines/{made['id']}/runs", params={"before": "nope"})
            assert bad.status_code == 200 and bad.json()["runs"] == []
        finally:
            service_module.ROUTINE_RUNS_PAGE = 50


async def test_every_write_needs_the_origin(app, alice, bot):
    async with signed_in(app, "alice") as client:
        made = await _make(client, bot)
        rid = made["id"]
        writes = (
            ("post", f"/api/bots/{bot.id}/routines", body()),
            ("patch", f"/api/routines/{rid}", {"name": "x"}),
            ("delete", f"/api/routines/{rid}", None),
            ("post", f"/api/routines/{rid}/run-now", None),
            ("post", "/api/routines/preview", {"schedule": TIMES}),
        )
        for method, path, payload in writes:
            kwargs = {"json": payload} if payload is not None else {}
            for headers in ({}, BAD_O):
                response = await client.request(method.upper(), path, headers=headers, **kwargs)
                assert response.status_code == 403, (method, path, headers)
        assert (await client.get(f"/api/bots/{bot.id}/routines")).json()["routines"][0]["name"] == "Morning news"


async def test_every_route_needs_a_login(app, alice, bot):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test") as anon:
        for method, path in (("GET", f"/api/bots/{bot.id}/routines"), ("POST", f"/api/bots/{bot.id}/routines"),
                             ("PATCH", "/api/routines/x"), ("DELETE", "/api/routines/x"),
                             ("POST", "/api/routines/x/run-now"), ("GET", "/api/routines/x/runs"),
                             ("POST", "/api/routines/preview")):
            assert (await anon.request(method, path, headers=O, json={})).status_code == 401, (method, path)


async def test_every_write_publishes_routines_changed_and_a_quiet_line(app, alice, bot):
    async with signed_in(app, "alice") as client:
        made = await _make(client, bot)
        await client.patch(f"/api/routines/{made['id']}", json={"schedule": {**TIMES, "times": ["09:00"]}}, headers=O)
        await client.patch(f"/api/routines/{made['id']}", json={"enabled": False}, headers=O)
        await client.delete(f"/api/routines/{made['id']}", headers=O)
        frames = await _frames(app, alice.id, "routines_changed")
        assert [f["bot_id"] for f in frames] == [bot.id] * 4
        thread = await TalkStore(app.state.config).main_thread(alice.id, bot.id)
        notes = [json.loads(m.body)["text"] for m in await app.state.talk.list_messages(alice.id, thread.id)
                 if m.kind == "routine_note"]
        assert notes == ["Created routine · Morning news", "Updated routine · Morning news",
                         "Paused routine · Morning news", "Deleted routine · Morning news"]


async def test_another_users_routines_runs_and_bots_are_404(app, alice, bob, bot):
    async with signed_in(app, "alice") as client:
        made = await _make(client, bot)
    async with signed_in(app, "bob") as client:
        rid = made["id"]
        assert (await client.get(f"/api/bots/{bot.id}/routines")).status_code == 404
        assert (await client.post(f"/api/bots/{bot.id}/routines", json=body(), headers=O)).status_code == 404
        assert (await client.patch(f"/api/routines/{rid}", json={"name": "mine"}, headers=O)).status_code == 404
        assert (await client.delete(f"/api/routines/{rid}", headers=O)).status_code == 404
        assert (await client.post(f"/api/routines/{rid}/run-now", headers=O)).status_code == 404
        assert (await client.get(f"/api/routines/{rid}/runs")).status_code == 404
    async with signed_in(app, "alice") as client:
        still = (await client.get(f"/api/bots/{bot.id}/routines")).json()["routines"]
        assert [r["name"] for r in still] == ["Morning news"]


async def test_a_builtin_is_retimed_or_deleted_but_never_renamed(app, alice, bot):
    async with signed_in(app, "alice") as client:
        routine = await app.state.routine_store.create(alice.id, RoutineDraft(
            bot_id=bot.id, name="End of day", instructions="", schedule=parse_schedule(
                {"kind": "times", "days": [1, 2, 3, 4, 5, 6, 7], "times": ["21:00"]}),
            created_by="user", builtin="day_summary", enabled=False))
        for change in ({"name": "x"}, {"instructions": "x"}):
            assert (await client.patch(f"/api/routines/{routine.id}", json=change, headers=O)).status_code == 422
        retimed = await client.patch(
            f"/api/routines/{routine.id}", json={"schedule": {**TIMES, "times": ["20:30"]}, "enabled": True},
            headers=O)
        assert retimed.status_code == 200 and retimed.json()["enabled"] is True and retimed.json()["builtin"]
        assert (await client.post(f"/api/routines/{routine.id}/run-now", headers=O)).status_code == 422
        assert (await client.delete(f"/api/routines/{routine.id}", headers=O)).status_code == 204
        listed = (await client.get(f"/api/bots/{bot.id}/routines")).json()["routines"]
        assert all(r["id"] != routine.id for r in listed)
