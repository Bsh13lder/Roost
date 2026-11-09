"""Remind me (phone notifications, 2026-10-23): a reminder set with its own advance reminders, from the drawer
(PATCH) and by a bot (update_task); ``[]`` means only the reminder itself."""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from roost.config import load_config
from roost.db.connection import init_db
from roost.gateway.app import create_app
from roost.gateway.auth import register_user
from roost.llm.types import ToolCallRequested, TurnDone
from tz_helpers import MADRID_TZ
from roost.tasks.due import patch_from_fields
from roost.tasks.models import TaskDraft
from roost.tasks.store import TaskStore
from team_helpers import make_bot, make_rig, say, send, team_model, wait_idle

O = {"Origin": "http://127.0.0.1:18800"}


def test_a_reminder_with_no_advance_reminder():
    patch = patch_from_fields({"reminder_at": "2026-12-01T08:50", "pre_reminders": []})
    assert patch.changes["reminder_at"] == "2026-12-01T07:50:00+00:00"
    assert patch.changes["pre_reminders"] == ()


def test_a_reminder_with_its_own_advance_reminder():
    patch = patch_from_fields({"reminder_at": "2026-12-01T09:00", "pre_reminders": ["-1h"]})
    assert patch.changes["pre_reminders"] == ("2026-12-01T07:00:00+00:00",)


def test_without_advance_reminders_the_default_stays():
    patch = patch_from_fields({"reminder_at": "2026-12-01T09:00"})
    assert patch.changes["pre_reminders"] == ("2026-12-01T07:30:00+00:00",)


def test_advance_reminders_need_a_reminder_time_in_the_same_change():
    with pytest.raises(ValueError, match="reminder time"):
        patch_from_fields({"pre_reminders": ["-1h"]})


def test_the_drawer_sets_ten_minutes_before_with_no_extra_reminder():
    c = TestClient(create_app())
    assert c.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"}, headers=O).status_code == 201
    task = c.post("/api/tasks", json={"title": "Call Iurie", "due_date": "2026-12-01T09:00"}, headers=O).json()
    patched = c.patch(f"/api/tasks/{task['id']}", json={"reminder_at": "2026-12-01T08:50", "pre_reminders": []},
                      headers=O)
    assert patched.status_code == 200, patched.text
    assert (patched.json()["reminder_at"], patched.json()["pre_reminders"]) == ("2026-12-01T07:50:00+00:00", [])
    alone = c.patch(f"/api/tasks/{task['id']}", json={"pre_reminders": ["-1h"]}, headers=O)
    assert alone.status_code == 422 and "reminder time" in alone.json()["detail"]


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


async def test_a_bot_sets_a_reminder_on_a_task(cfg):
    user_id = (await register_user(cfg, "alice", "pw-123456")).id
    await TaskStore(cfg).create(user_id, TaskDraft(title="Call Iurie"), created_by_bot=None, tainted=False)
    bot = await make_bot(cfg, user_id, "Chief")
    rig = make_rig(cfg, team_model({"Chief": [
        [ToolCallRequested(id="t", name="update_task", arguments={
            "task": "Call Iurie", "reminder_at": "tomorrow at 9", "pre_reminders": []}), TurnDone("tool_use")],
        say("Done."),
    ]}))
    thread = await rig.talk.create_thread(user_id, bot.id)
    await send(rig, user_id, bot.id, thread.id, "remind me tomorrow at 9 to call Iurie")
    await wait_idle(rig.runner)

    [task] = await TaskStore(cfg).list(user_id)
    nine = datetime.combine(datetime.now(MADRID_TZ).date() + timedelta(days=1), time(9, 0), tzinfo=MADRID_TZ)
    assert task.reminder_at == nine.astimezone(timezone.utc).isoformat()
    assert task.pre_reminders == ()
