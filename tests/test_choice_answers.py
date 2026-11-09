"""Answering an options card: pick, your own words, or a dismiss, and the decision each leaves (chat feel Task 5)."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import httpx
import pytest

from approval_helpers import ORIGIN, make_card_rig
from roost.approvals.executor import ApprovedCalls
from roost.approvals.models import ApprovalDraft, BadAnswer, CardClosed, CardState
from roost.approvals.store import ApprovalStore
from roost.choices.models import CHOICE_TOOL, ChoiceArgs, choice_step
from roost.choices.texts import (
    CHOICE_OUT_OF_RANGE_TEXT, DISMISS_LINE, DISMISSED_ANSWER, OWN_NEEDS_TEXT, OWN_NOT_OFFERED_TEXT,
)
from roost.config import load_config
from roost.constants import CHOICE_OWN_ANSWER_MAX_CHARS
from roost.db.connection import db_session, init_db
from roost.gateway.app import create_app
from roost.gateway.auth import register_user
from roost.llm.types import ToolCallRequested, TurnDone
from roost.talk.gate import Gate
from team_helpers import make_bot, say, send, team_model, wait_idle

PASSWORD = "pw-123456"
OPTIONS = ["Keep it", "Change it", "Ask later"]
ARGS = {"question": "Keep it as is?", "options": OPTIONS, "safe": 0, "own": True, "why": "Shared file."}


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def user_id(cfg):
    return (await register_user(cfg, "alice", "pw-123456")).id


async def _open(cfg, user_id, bot, thread_id, *, tainted=False, **overrides):
    step = choice_step(ChoiceArgs.model_validate({**ARGS, **overrides}))
    return await ApprovalStore(cfg).open(user_id, ApprovalDraft(
        bot_id=bot.id, thread_id=thread_id, work_item_id=None, kind="ask", steps=(step,),
        request="do it", tainted=tainted))


async def _rig(cfg, user_id, *, tainted=False, script=None, **overrides):
    bot = await make_bot(cfg, user_id, "Scout")
    rig = make_card_rig(cfg, team_model({"Scout": script or [say("Carrying on.")]}))
    thread = await rig.talk.create_thread(user_id, bot.id)
    card = await _open(cfg, user_id, bot, thread.id, tainted=tainted, **overrides)
    return rig, bot, thread, card


async def _lines(rig, user_id, thread_id, kind="card_answer"):
    return [m for m in await rig.talk.list_messages(user_id, thread_id) if m.kind == kind]


async def _items(cfg, user_id):
    async with db_session(cfg) as db:
        rows = await (await db.execute("SELECT kind, tainted FROM work_items WHERE user_id = ?",
                                       (user_id,))).fetchall()
    return [(r["kind"], r["tainted"]) for r in rows]


async def test_pick_uses_the_stored_option_text(cfg, user_id):
    rig, bot, thread, card = await _rig(cfg, user_id)
    done = await rig.service.answer(user_id, card.id, "pick", text="EVIL client text", choice=1)
    assert done.state is CardState.APPROVED
    [line] = await _lines(rig, user_id, thread.id)
    assert line.body == "Change it" and line.role == "user"
    found = await rig.decisions.find(user_id, bot.id, "keep it as is")
    assert found.answer == "Change it"
    await wait_idle(rig.runner)


@pytest.mark.parametrize("choice", [3, 7, -1])
async def test_a_pick_out_of_range_is_422(cfg, user_id, choice):
    rig, bot, thread, card = await _rig(cfg, user_id)
    with pytest.raises(BadAnswer, match=CHOICE_OUT_OF_RANGE_TEXT):
        await rig.service.answer(user_id, card.id, "pick", choice=choice)
    assert (await rig.store.get(user_id, card.id)).state is CardState.OPEN


async def test_a_pick_without_a_choice_is_422(cfg, user_id):
    rig, bot, thread, card = await _rig(cfg, user_id)
    with pytest.raises(BadAnswer, match=CHOICE_OUT_OF_RANGE_TEXT):
        await rig.service.answer(user_id, card.id, "pick")


async def test_own_text_only_when_allowed(cfg, user_id):
    rig, bot, thread, card = await _rig(cfg, user_id, own=False)
    with pytest.raises(BadAnswer, match=OWN_NOT_OFFERED_TEXT):
        await rig.service.answer(user_id, card.id, "own", text="my way")
    assert (await rig.store.get(user_id, card.id)).state is CardState.OPEN


async def test_own_text_bounds(cfg, user_id):
    rig, bot, thread, card = await _rig(cfg, user_id)
    for bad in ("", "   ", None, "x" * (CHOICE_OWN_ANSWER_MAX_CHARS + 1)):
        with pytest.raises(BadAnswer, match=OWN_NEEDS_TEXT):
            await rig.service.answer(user_id, card.id, "own", text=bad)
    done = await rig.service.answer(user_id, card.id, "own", text="  <b>Do it later</b> ")
    assert done.state is CardState.APPROVED
    [line] = await _lines(rig, user_id, thread.id)
    assert line.body == "<b>Do it later</b>"           # stored as text; the model and the web escape it
    assert (await rig.decisions.list(user_id, bot.id))[0].answer == "<b>Do it later</b>"
    await wait_idle(rig.runner)


@pytest.mark.parametrize("answer", ["yes", "yes_session", "accept", "decline", "edit"])
async def test_yes_on_an_options_card_is_422(cfg, user_id, answer):
    rig, bot, thread, card = await _rig(cfg, user_id)
    with pytest.raises(BadAnswer):
        await rig.service.answer(user_id, card.id, answer, text="hello")
    assert (await rig.store.get(user_id, card.id)).state is CardState.OPEN


async def test_pick_and_own_do_not_fit_other_cards(cfg, user_id):
    from roost.approvals.models import PendingCall
    bot = await make_bot(cfg, user_id, "Scout")
    rig = make_card_rig(cfg, team_model({"Scout": [say("ok")]}))
    thread = await rig.talk.create_thread(user_id, bot.id)
    step = PendingCall(tool="add_task", arguments={"title": "x"}, topic="tasks", title="Add a task")
    card = await rig.store.open(user_id, ApprovalDraft(bot_id=bot.id, thread_id=thread.id, work_item_id=None,
                                                       kind="ask", steps=(step,), request="r", tainted=False))
    for answer in ("pick", "own"):
        with pytest.raises(BadAnswer):
            await rig.service.answer(user_id, card.id, answer, text="x", choice=0)


async def test_dismiss_is_no_and_records_the_decision(cfg, user_id):
    rig, bot, thread, card = await _rig(cfg, user_id)
    done = await rig.service.answer(user_id, card.id, "no")
    assert done.state is CardState.DECLINED
    [line] = await _lines(rig, user_id, thread.id)
    assert line.body == DISMISS_LINE.format(question="Keep it as is?")
    found = await rig.decisions.find(user_id, bot.id, "KEEP IT AS IS??")
    assert found.answer == DISMISSED_ANSWER
    from roost.choices.tool import park_choice
    again = await park_choice(ARGS, cards=True, tainted=False, decisions=rig.decisions, user_id=user_id,
                              bot_id=bot.id, has_question_book=False)
    assert isinstance(again, str) and DISMISSED_ANSWER in again
    await wait_idle(rig.runner)


async def test_only_one_press_wins_on_an_options_card(cfg, user_id):
    rig, bot, thread, card = await _rig(cfg, user_id)
    results = await asyncio.gather(
        rig.service.answer(user_id, card.id, "pick", choice=0), rig.service.answer(user_id, card.id, "no"),
        rig.service.answer(user_id, card.id, "pick", choice=2), return_exceptions=True)
    assert sum(isinstance(r, CardClosed) for r in results) == 2
    assert len(await _lines(rig, user_id, thread.id)) == 1
    assert len(await rig.decisions.list(user_id, bot.id)) == 1
    await wait_idle(rig.runner)


async def test_the_executor_never_runs_ask_choice(cfg, user_id):
    rig, bot, thread, card = await _rig(cfg, user_id)
    executor = ApprovedCalls(rig.runner.domain, Gate(cfg), rig.talk, rig.events)
    outcome = await executor.run(user_id, card, card.steps[0])
    assert outcome.ok is False and card.steps[0].tool == CHOICE_TOOL


async def test_a_tainted_choice_taints_the_item_and_the_decision(cfg, user_id):
    rig, bot, thread, card = await _rig(cfg, user_id, tainted=True)
    await rig.service.answer(user_id, card.id, "pick", choice=0)
    [line] = await _lines(rig, user_id, thread.id)
    assert line.tainted is True
    assert (await rig.decisions.list(user_id, bot.id))[0].tainted is True
    assert ("card_answer", 1) in await _items(cfg, user_id)
    await wait_idle(rig.runner)


async def test_a_clean_choice_taints_nothing(cfg, user_id):
    rig, bot, thread, card = await _rig(cfg, user_id)
    await rig.service.answer(user_id, card.id, "pick", choice=0)
    assert (await rig.decisions.list(user_id, bot.id))[0].tainted is False
    assert ("card_answer", 0) in await _items(cfg, user_id)
    await wait_idle(rig.runner)


async def test_a_secret_looking_answer_still_answers_the_card(cfg, user_id):
    rig, bot, thread, card = await _rig(cfg, user_id)
    done = await rig.service.answer(user_id, card.id, "own", text="my password is hunter2hunter2")
    assert done.state is CardState.APPROVED
    assert await rig.decisions.list(user_id, bot.id) == ()
    await wait_idle(rig.runner)


async def test_the_bot_carries_on_after_a_pick(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Scout")
    ask = [ToolCallRequested(id="c1", name="ask_choice", arguments=ARGS), TurnDone("tool_use")]
    rig = make_card_rig(cfg, team_model({"Scout": [ask, say("I asked you."), say("Kept it.")]}))
    thread = await rig.talk.create_thread(user_id, bot.id)
    await send(rig, user_id, bot.id, thread.id, "Do the thing")
    await wait_idle(rig.runner)
    [card] = await rig.store.list_open(user_id)
    await rig.service.answer(user_id, card.id, "pick", choice=2)
    await wait_idle(rig.runner)
    turns = rig.model.requests[-1].turns
    assert any(t.role == "user" and t.text == "Ask later" for t in turns)
    assert len(rig.model.requests) == 2


@asynccontextmanager
async def _signed_in(app, username):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test") as client:
        assert (await client.post("/api/auth/login", json={"username": username, "password": PASSWORD},
                                  headers=ORIGIN)).status_code == 200
        try:
            yield client
        finally:
            await wait_idle(app.state.turns, timeout=8)


async def _http_card(cfg, app, username="alice"):
    user = await register_user(cfg, username, PASSWORD)
    bot = await make_bot(cfg, user.id, "Scout")
    thread = await app.state.talk.create_thread(user.id, bot.id)
    return user, await _open(cfg, user.id, bot, thread.id)


async def test_the_wire_card_carries_the_choice_and_no_secrets(cfg):
    app = create_app()
    user, card = await _http_card(cfg, app)
    async with _signed_in(app, "alice") as client:
        body = (await client.get(f"/api/approvals/{card.id}")).json()
    assert body["choice"] == {"question": "Keep it as is?", "options": OPTIONS, "safe": 0, "own": True,
                              "why": "Shared file."}
    assert "request" not in body and "user_id" not in body


async def test_http_answers(cfg):
    app = create_app()
    user, card = await _http_card(cfg, app)
    async with _signed_in(app, "alice") as client:
        url = f"/api/approvals/{card.id}/answer"
        assert (await client.post(url, json={"answer": "pick", "choice": 9}, headers=ORIGIN)).status_code == 422
        assert (await client.post(url, json={"answer": "yes"}, headers=ORIGIN)).status_code == 422
        assert (await client.post(url, json={"answer": "pick", "choice": 0, "extra": 1},
                                  headers=ORIGIN)).status_code == 422
        ok = await client.post(url, json={"answer": "pick", "choice": 1}, headers=ORIGIN)
        assert ok.status_code == 200 and ok.json()["state"] == "approved"
        again = await client.post(url, json={"answer": "no"}, headers=ORIGIN)
        assert again.status_code == 409 and again.json()["detail"] == "Already answered."


async def test_every_answer_needs_the_origin(cfg):
    app = create_app()
    user, card = await _http_card(cfg, app)
    async with _signed_in(app, "alice") as client:
        r = await client.post(f"/api/approvals/{card.id}/answer", json={"answer": "pick", "choice": 0})
        assert r.status_code == 403
        assert (await client.get(f"/api/approvals/{card.id}")).json()["state"] == "open"


async def test_another_users_options_card_is_404(cfg):
    app = create_app()
    user, card = await _http_card(cfg, app)
    await register_user(cfg, "bob", PASSWORD)
    async with _signed_in(app, "bob") as client:
        r = await client.post(f"/api/approvals/{card.id}/answer", json={"answer": "pick", "choice": 0},
                              headers=ORIGIN)
        assert r.status_code == 404
        assert (await client.get(f"/api/approvals/{card.id}")).status_code == 404
    assert (await ApprovalStore(cfg).get(user.id, card.id)).state is CardState.OPEN
