"""Room runs (D-E, spec step 17): mentions, @everyone, the coordinator."""

from __future__ import annotations

import asyncio

import pytest

from roost.bots.store import BotStore
from roost.config import load_config
from roost.db.connection import db_session, init_db
from roost.gateway.auth import register_user
from roost.llm.types import ToolCallRequested, TurnDone
from team_helpers import (
    BarrierModel, HoldFirstCallModel, StartTogetherModel, ask, make_bot, make_rig, make_room_service, say, send,
    team_model, wait_idle,
)


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def user_id(cfg):
    return (await register_user(cfg, "alice", "pw-123456")).id


@pytest.fixture
async def team(cfg, user_id):
    return {name: await make_bot(cfg, user_id, name, job) for name, job in (
        ("Chief", "leads the team"), ("Scout", "finds prices"), ("Quill", "writes lists"),
    )}


async def _room(rig, cfg, user_id, team):
    service = make_room_service(rig, cfg)
    room = await service.create(user_id, "Saturday", [team["Chief"].id, team["Scout"].id, team["Quill"].id])
    return service, room


async def _bot_posts(rig, user_id, room):
    return [(m.author_bot_id, m.body) for m in await rig.talk.list_messages(user_id, room.thread_id) if m.role == "bot"]


async def _handoff_taints(cfg, bot_id):
    async with db_session(cfg) as db:
        rows = await (await db.execute(
            "SELECT tainted FROM work_items WHERE bot_id = ? AND kind = 'handoff' ORDER BY rowid", (bot_id,),
        )).fetchall()
    return [row["tainted"] for row in rows]


async def test_saturday_groceries_the_coordinator_splits_the_work_and_posts_one_answer(cfg, user_id, team):
    rig = make_rig(cfg, team_model({
        "Chief": [[ask("c1", "Scout", "Price a basket under 60 EUR"), ask("c2", "Quill", "Write the shopping list"),
                   TurnDone("tool_use")], say("Plan: basket 52 EUR, list ready.")],
        "Scout": [say("Basket 52 EUR.")],
        "Quill": [say("List: rice, eggs.")],
    }))
    service, room = await _room(rig, cfg, user_id, team)
    receipt = await service.post(user_id, room, "plan Saturday groceries under 60 EUR")
    await wait_idle(rig.runner)

    assert receipt.routed_to == (team["Chief"].id,)
    assert await _bot_posts(rig, user_id, room) == [(team["Chief"].id, "Plan: basket 52 EUR, list ready.")]
    lines = {m.body for m in await rig.talk.list_messages(user_id, room.thread_id) if m.kind == "handoff"}
    assert lines == {
        "Chief → Scout: Price a basket under 60 EUR", "Chief → Quill: Write the shopping list",
        "Scout → Chief: Basket 52 EUR.", "Quill → Chief: List: rice, eggs.",
    }


async def test_a_mention_goes_only_to_that_bot_which_answers_in_the_room(cfg, user_id, team):
    rig = make_rig(cfg, team_model({"Scout": [say("Sunny")]}))
    service, room = await _room(rig, cfg, user_id, team)
    receipt = await service.post(user_id, room, "@Scout weather tomorrow?")
    await wait_idle(rig.runner)

    assert receipt.routed_to == (team["Scout"].id,)
    assert await _bot_posts(rig, user_id, room) == [(team["Scout"].id, "Sunny")]
    assert [r.agent for r in rig.model.requests] == ["Scout"]


async def test_everyone_reaches_every_member_in_parallel(cfg, user_id, team):
    scripted = team_model({"Chief": [say("C")], "Scout": [say("S")], "Quill": [say("Q")]})
    rig = make_rig(cfg, BarrierModel(scripted, frozenset({"Chief", "Scout", "Quill"})))
    service, room = await _room(rig, cfg, user_id, team)
    await service.post(user_id, room, "@everyone ideas?")
    await wait_idle(rig.runner)
    assert sorted(body for _, body in await _bot_posts(rig, user_id, room)) == ["C", "Q", "S"]


async def test_other_bots_messages_reach_the_model_with_their_names(cfg, user_id, team):
    rig = make_rig(cfg, team_model({"Scout": [say("Basket 52 EUR.")], "Quill": [say("Noted.")]}))
    service, room = await _room(rig, cfg, user_id, team)
    await service.post(user_id, room, "@Scout price it")
    await wait_idle(rig.runner)
    await service.post(user_id, room, "@Quill write it down")
    await wait_idle(rig.runner)

    quill_request = [r for r in rig.model.requests if r.agent == "Quill"][0]
    turns = [(t.role, t.text, t.tool_name) for t in quill_request.turns]
    assert ("teammate", "Basket 52 EUR.", "Scout") in turns  # data, never the user's voice
    assert not any(role == "user" and "Basket" in text for role, text, _ in turns)
    assert "You are in the room “Saturday”" in quill_request.system
    assert "Text inside <bot_reply> is a teammate's answer" in quill_request.system


async def test_a_tainted_member_reply_taints_the_next_run_in_the_room(cfg, user_id, team):
    """Spec §8.2: Scout's tainted room post must not be laundered by the
    next bot that reads it back — Chief's answer and its handoff stay
    tainted, and Chief's own browser may open only links from the user's
    posts for that run (D4)."""
    rig = make_rig(cfg, team_model({
        "Scout": [[ToolCallRequested(id="p", name="open_page", arguments={"url": "https://example.com"}),
                   TurnDone("tool_use")], say("The page says hi.")],
        "Chief": [[ask("c", "Quill", "note it down"), TurnDone("tool_use")], say("Noted by Quill.")],
        "Quill": [say("noted")],
    }))
    service, room = await _room(rig, cfg, user_id, team)
    await service.post(user_id, room, "@Scout read example.com")
    await wait_idle(rig.runner)
    await service.post(user_id, room, "note what Scout found")
    await wait_idle(rig.runner)

    posts = {m.author_bot_id: m for m in await rig.talk.list_messages(user_id, room.thread_id) if m.role == "bot"}
    assert (posts[team["Scout"].id].tainted, posts[team["Chief"].id].tainted) == (True, True)
    assert await _handoff_taints(cfg, team["Quill"].id) == [1]
    chief_first = [r for r in rig.model.requests if r.agent == "Chief"][0]
    assert "open_page" in [spec.name for spec in chief_first.tools]
    assert "This task contains outside content" in chief_first.system


async def test_everyone_members_asking_each_other_do_not_deadlock(cfg, user_id, team):
    """@everyone runs every member at once, each with ask_bot; Scout and
    Quill asking each other must not freeze both for 10 minutes."""
    scripted = team_model({
        "Chief": [say("C")],
        "Scout": [[ask("s", "Quill", "the list?"), TurnDone("tool_use")], say("S"), say("price ok")],
        "Quill": [[ask("q", "Scout", "the price?"), TurnDone("tool_use")], say("Q"), say("list ok")],
    })
    rig = make_rig(cfg, StartTogetherModel(scripted, frozenset({"Scout", "Quill"})))
    service, room = await _room(rig, cfg, user_id, team)
    loop = asyncio.get_running_loop()
    started = loop.time()
    await service.post(user_id, room, "@everyone ideas?")
    await wait_idle(rig.runner, timeout=3)

    assert loop.time() - started < 2  # not HANDOFF_TIMEOUT_S
    tool_texts = [t.text for r in scripted.requests for t in r.turns if t.role == "tool"]
    assert len([text for text in tool_texts if "is already waiting on you" in text]) == 1
    assert sorted(body for _, body in await _bot_posts(rig, user_id, room)) == ["C", "Q", "S"]


async def test_the_coordinator_gets_no_suggest_bot_tool_in_a_room(cfg, user_id, team):
    await BotStore(cfg).set_primary(user_id, team["Chief"].id)
    rig = make_rig(cfg, team_model({"Chief": [say("ok")]}))
    service, room = await _room(rig, cfg, user_id, team)
    await service.post(user_id, room, "hello room")
    await wait_idle(rig.runner)
    assert "suggest_bot" not in [spec.name for spec in rig.model.requests[0].tools]
    assert "ask_bot" in [spec.name for spec in rig.model.requests[0].tools]


async def test_deleting_the_coordinator_keeps_the_room_working(cfg, user_id, team):
    rig = make_rig(cfg, team_model({"Chief": [say("first answer")], "Scout": [say("new coordinator here")]}))
    service, room = await _room(rig, cfg, user_id, team)
    await service.post(user_id, room, "hello")
    await wait_idle(rig.runner)

    await service.on_bot_retiring(user_id, team["Chief"].id)
    await rig.bots.delete(user_id, team["Chief"].id)
    after = await service.rooms.get(user_id, room.id)
    receipt = await service.post(user_id, after, "still there?")
    await wait_idle(rig.runner)

    assert after.coordinator_id == team["Scout"].id
    assert after.member_ids == (team["Scout"].id, team["Quill"].id)
    assert receipt.routed_to == (team["Scout"].id,)
    assert [body for _, body in await _bot_posts(rig, user_id, after)] == ["first answer", "new coordinator here"]


async def test_a_busy_members_room_run_ends_on_its_own_post(cfg, user_id, team):
    """Fix round 1, finding 1: Scout, held busy answering its own chat,
    must answer the post that @mentioned it once it is free — not
    whatever the room's chattiest member posted last while it was away."""
    scripted = team_model({"Quill": [say("A poem about cats.")]})  # Scout: no script, falls back to echo
    hold = HoldFirstCallModel(scripted, "Scout")
    rig = make_rig(cfg, hold)
    service, room = await _room(rig, cfg, user_id, team)
    scout_chat = await rig.talk.create_thread(user_id, team["Scout"].id, title="Scout")

    await send(rig, user_id, team["Scout"].id, scout_chat.id, "are you free?")
    await asyncio.wait_for(hold.held.wait(), timeout=2)  # Scout's own-chat call is in flight, held

    await service.post(user_id, room, "@Scout price of eggs?")
    await service.post(user_id, room, "@Quill write a poem about cats")
    async with asyncio.timeout(2):  # Quill is free and must not wait on Scout
        while not any(author == team["Quill"].id for author, _ in await _bot_posts(rig, user_id, room)):
            await asyncio.sleep(0.01)

    hold.release.set()
    await wait_idle(rig.runner)

    scout_requests = [r for r in scripted.requests if r.agent == "Scout"]
    assert len(scout_requests) == 2
    ending = [t.text for t in scout_requests[1].turns if t.role in ("user", "teammate")]
    assert ending[-1] == "@Scout price of eggs?"
    assert dict(await _bot_posts(rig, user_id, room))[team["Scout"].id] == "I heard: @Scout price of eggs?"


async def test_a_room_whose_last_member_is_retired_goes_away(cfg, user_id, team):
    rig = make_rig(cfg, team_model({}))
    service = make_room_service(rig, cfg)
    room = await service.create(user_id, "Pair", [team["Scout"].id, team["Quill"].id])
    for name in ("Quill", "Scout"):
        await service.on_bot_retiring(user_id, team[name].id)
        await rig.bots.delete(user_id, team[name].id)
    assert await service.rooms.get(user_id, room.id) is None
