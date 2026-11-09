"""A routine's own instructions widen its run log's site fence the way they widen its link scope (owner, 2026-11-04:
Gela's "Watch physio chat" opened WhatsApp Web, then a crashed tab reloaded it and the browser refused it with
ERR_BLOCKED_BY_CLIENT, because a run log holds no message of yours and its fence was empty)."""

from __future__ import annotations

import pytest

from roost.computer_use.run_fence import chat_fence
from roost.config import load_config
from roost.db.connection import init_db
from roost.gateway.auth import register_user
from approval_helpers import make_card_rig
from roost.llm.scripted_team import ScriptedTeamModel
from team_helpers import RecordingModel, make_bot

INSTRUCTIONS = "Open WhatsApp Web, open the physio chat and read only the newest messages. Send nothing."


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def user_id(cfg):
    return (await register_user(cfg, "alice", "pw-123456")).id


async def _run_log(cfg, user_id: str, body: str, **extra):
    bot = await make_bot(cfg, user_id, "Gela")
    rig = make_card_rig(cfg, RecordingModel(ScriptedTeamModel({"Gela": []})))
    thread = await rig.talk.create_thread(user_id, bot.id, "Watch physio chat", kind="routine")
    await rig.talk.add_message(user_id, thread.id, "user", body, kind="routine", **extra)
    return thread


async def test_a_well_known_site_the_routine_names_is_in_its_fence(cfg, user_id):
    thread = await _run_log(cfg, user_id, INSTRUCTIONS)
    fence = await chat_fence(cfg, user_id, thread.id)
    assert fence.allows("web.whatsapp.com")


async def test_an_address_typed_in_the_routine_does_not_widen_it(cfg, user_id):
    thread = await _run_log(cfg, user_id, "Read https://evil.example/ every morning.")
    fence = await chat_fence(cfg, user_id, thread.id)
    assert not fence.allows("evil.example")


async def test_the_page_a_routine_watches_is_in_its_fence(cfg, user_id):
    from roost.routines.models import RoutineDraft
    from roost.routines.schedule import parse_schedule
    from roost.routines.store import RoutineStore
    from roost.routines.watch_models import Watch
    from roost.talk.store import TalkStore

    bot = await make_bot(cfg, user_id, "Gela")
    routine = await RoutineStore(cfg, TalkStore(cfg)).create(user_id, RoutineDraft(
        bot_id=bot.id, name="Price", instructions="Tell me the price.", created_by="user",
        schedule=parse_schedule({"kind": "times", "days": [1], "times": ["09:00"]}),
        watch=Watch(url="https://shop.example/item/7", part="the price box", every_min=5)))
    fence = await chat_fence(cfg, user_id, routine.thread_id)
    assert fence.allows("shop.example") and not fence.allows("evil.example")


async def test_a_routine_line_a_bot_wrote_does_not_widen_it(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Chief")
    thread = await _run_log(cfg, user_id, INSTRUCTIONS, author_bot_id=bot.id)
    fence = await chat_fence(cfg, user_id, thread.id)
    assert not fence.allows("web.whatsapp.com")


async def _opened(cfg, user_id: str, bot_id: str, url: str, reason: str = "fresh_open", action: str = "open_page"):
    """An audit row as the gate writes it when a run of your own chat opened ``url``."""
    import json
    from datetime import datetime, timezone

    from roost.crypto.encryption import encrypt, user_aad
    from roost.crypto.key_manager import get_user_dek
    from roost.db.connection import db_session

    dek = await get_user_dek(cfg, user_id)
    detail = encrypt(json.dumps({"url": url}), dek, user_aad(user_id, "audit:detail"))
    async with db_session(cfg) as db:
        await db.execute(
            "INSERT INTO audit (user_id, bot_id, action, decision, detail, created_at, reason, tainted) "
            "VALUES (?,?,?,?,?,?,?,0)",
            (user_id, bot_id, action, "do", detail, datetime.now(timezone.utc).isoformat(), reason))
        await db.commit()


WIZZ = "One-time check: on the official Wizz Air site (wizzair.com, signed in), list the prices for 1-13 Dec."


async def _wizz_log(cfg, user_id: str):
    thread = await _run_log(cfg, user_id, WIZZ)
    from roost.talk.store import TalkStore
    return thread, (await TalkStore(cfg).get_thread(user_id, thread.id)).bot_id


async def test_a_site_your_own_chat_opened_and_the_routine_names_is_in_its_fence(cfg, user_id):
    """Owner, 2026-11-05: Gela opened Wizz Air in your chat, then her 09:00 one-time check asked to open it again."""
    thread, bot_id = await _wizz_log(cfg, user_id)
    await _opened(cfg, user_id, bot_id, "https://www.wizzair.com/en-gb/booking/select-flight/BCN/KUT")
    fence = await chat_fence(cfg, user_id, thread.id)
    assert fence.allows("www.wizzair.com") and fence.allows("wizzair.com")


async def test_a_site_your_chat_opened_after_reading_pages_counts_too(cfg, user_id):
    thread, bot_id = await _wizz_log(cfg, user_id)
    await _opened(cfg, user_id, bot_id, "https://wizzair.com/", reason="owner_site")
    assert (await chat_fence(cfg, user_id, thread.id)).allows("wizzair.com")


async def test_a_named_site_never_opened_from_your_chat_still_asks(cfg, user_id):
    thread, _ = await _wizz_log(cfg, user_id)
    assert not (await chat_fence(cfg, user_id, thread.id)).allows("wizzair.com")


async def test_an_open_that_was_not_from_your_own_chat_does_not_count(cfg, user_id):
    thread, bot_id = await _wizz_log(cfg, user_id)
    await _opened(cfg, user_id, bot_id, "https://wizzair.com/", reason="allowed")
    assert not (await chat_fence(cfg, user_id, thread.id)).allows("wizzair.com")


async def test_a_site_your_chat_opened_that_the_routine_does_not_name_stays_out(cfg, user_id):
    thread, bot_id = await _wizz_log(cfg, user_id)
    await _opened(cfg, user_id, bot_id, "https://evil.example/")
    assert not (await chat_fence(cfg, user_id, thread.id)).allows("evil.example")


async def test_another_bots_open_does_not_count(cfg, user_id):
    thread, _ = await _wizz_log(cfg, user_id)
    other = await make_bot(cfg, user_id, "Scout")
    await _opened(cfg, user_id, other.id, "https://wizzair.com/")
    assert not (await chat_fence(cfg, user_id, thread.id)).allows("wizzair.com")
