"""``set_my_voice`` (docs/plans/2026-10-30-roost-voice.md §4): a bot changes ONLY its own voice settings when the
user asks. No card in a run the user's own message started in their 1:1 chat that has read no outside content (a
clean run, or a site-fresh one); anywhere else (tainted, routine, handoff, room) an ordinary Ask card. Saving goes
through the one ``VoiceSettingsService`` the route uses, which publishes ``bot_updated``, and a call in progress
speaks its next part in the new voice."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from roost.approvals import topics
from roost.approvals.models import ApprovalState, PendingCall
from roost.approvals.preview import preview_call
from roost.bots.store import BotStore
from roost.config import load_config
from roost.db.connection import init_db
from roost.events.hub import EventHub
from roost.gateway.auth import register_user
from roost.talk.domain_tools import RecordContext, build_domain_tools
from roost.talk.gate import GateContext, judge
from roost.talk.instructions import VOICE_SETTINGS_TEXT, build_instructions
from roost.talk.plain_steps import plain_step
from roost.talk.tool_catalog import CATALOG
from roost.talk.tools import EVERY_BOT_TOOLS, helper_tool_names
from roost.voice.calls import CallRegistry
from roost.voice.client import FakeVoice
from roost.voice.constants import DEFAULT_VOICE, VoiceSettings
from roost.voice.prompt import voice_section
from roost.voice.service import VoiceSettingsService
from roost.voice.settings import VoicePatch, apply_patch
from roost.voice.speak_ahead import SpeakAhead
from roost.voice.spoken import SpeechCache
from roost.voice.tool_specs import SET_MY_VOICE, VOICE_TOOL_DEFS
from roost.voice.tools import BAD_VOICE_ARGS, VoiceTools, voice_changed_text
from team_helpers import make_bot

PASSWORD = "pw-123456"


class _Events:
    def __init__(self) -> None:
        self.frames: list[tuple[str, dict]] = []

    async def publish(self, user_id: str, frame: dict) -> int:
        self.frames.append((user_id, frame))
        return 0


@pytest.fixture
async def world():
    cfg = load_config()
    await init_db(cfg)
    user = (await register_user(cfg, "alice", PASSWORD)).id
    bots = BotStore(cfg)
    bot = await make_bot(cfg, user, "Scout", "reads the news")
    other = await make_bot(cfg, user, "Pip", "keeps the books")
    events = _Events()
    service = VoiceSettingsService(bots, events)
    return {"cfg": cfg, "user": user, "bot": bot, "other": other, "bots": bots, "events": events,
            "service": service, "tools": VoiceTools(service)}


def _ctx(w, *, tainted=False, from_routine=False, user_started=True):
    return RecordContext(user_id=w["user"], bot_id=w["bot"].id, tainted=tainted, from_routine=from_routine,
                         thread_id="t1", run_id="run-1", user_started=user_started)


def _gate(*, tainted=False, owner_chat=True, site_fresh=False, cards=True, mode="ask", approval=True):
    state = ApprovalState(mode=mode, ask_topics=frozenset(), cards=cards) if approval else None
    return GateContext(allowed=frozenset(CATALOG), tainted=tainted, approval=state, owner_chat=owner_chat,
                       site_fresh=site_fresh)


def _judge(ctx: GateContext, args=None):
    verdict = judge(CATALOG[SET_MY_VOICE], SET_MY_VOICE, args or {"speed": 1.25}, ctx)
    return verdict.decision, verdict.reason


# -- the catalog, the words and the gate -------------------------------------------------------------------------


def test_every_bot_has_the_tool_and_no_helper_does():
    assert SET_MY_VOICE in EVERY_BOT_TOOLS and SET_MY_VOICE in CATALOG
    assert CATALOG[SET_MY_VOICE].kind == "write_change" and CATALOG[SET_MY_VOICE].own_settings is True
    assert VOICE_TOOL_DEFS[0].name == SET_MY_VOICE
    assert SET_MY_VOICE not in helper_tool_names(frozenset(CATALOG))
    assert topics.topic_of(SET_MY_VOICE) is not None
    schema = CATALOG[SET_MY_VOICE].spec.input_schema["properties"]
    assert set(schema) == {"speaker", "tone", "speed", "read_aloud", "correct_speech", "language"}
    assert "ka" not in schema["language"]["enum"] and {"auto", "en", "es"} <= set(schema["language"]["enum"])


def test_the_plain_step_and_the_card_title_are_fixed_words():
    assert plain_step(SET_MY_VOICE, {"speed": 2.0, "speaker": "ryan"}).line == "Changed my voice"
    card = preview_call(SET_MY_VOICE, {"speed": 2.0}, topics.topic_of(SET_MY_VOICE))
    assert card.title == "Change my voice"


async def test_the_prompt_tells_the_bot_it_may_change_its_voice_when_asked(world):
    assert "set_my_voice" in voice_section()
    assert "slower or faster" in VOICE_SETTINGS_TEXT and "set_my_voice" in VOICE_SETTINGS_TEXT
    assert VOICE_SETTINGS_TEXT in build_instructions(world["bot"])                 # the chat's instructions
    assert VOICE_SETTINGS_TEXT in build_instructions(world["bot"], spoken=True)    # and a call's


@pytest.mark.parametrize("ctx", [
    _gate(),                                        # a clean run of your own chat
    _gate(mode="auto_edit"), _gate(mode="plan"),     # whatever the mode
    _gate(tainted=True, site_fresh=True),           # a site-fresh run of your own new message
    _gate(tainted=True),                            # your chat after outside content (owner, 2026-11-03)
    _gate(approval=False),                          # an old rig with no approval state
])
def test_it_runs_with_no_card_in_a_clean_or_fresh_run_of_your_own_chat(ctx):
    assert _judge(ctx) == ("do", "allowed")


@pytest.mark.parametrize("ctx", [
    _gate(owner_chat=False),                        # a routine's run (it may show cards)
    _gate(owner_chat=False, tainted=True),
    _gate(owner_chat=False, site_fresh=True),       # freshness is for your own chat only
])
def test_anywhere_else_it_parks_on_an_ordinary_ask_card(ctx):
    assert _judge(ctx) == ("ask", "hard_floor")


def test_where_no_card_can_open_it_is_refused():
    decision, reason = _judge(_gate(owner_chat=False, cards=False))
    assert (decision, reason) == ("never", "needs_your_ok")
    decision, _ = _judge(_gate(tainted=True, cards=False))
    assert decision == "never"
    # A routine, handoff or room on a rig with no approval state never changes the settings by itself either.
    assert _judge(_gate(owner_chat=False, approval=False)) == ("never", "needs_your_ok")
    assert _judge(_gate(owner_chat=False, tainted=True, approval=False)) == ("never", "needs_your_ok")


# -- the settings patch ------------------------------------------------------------------------------------------


def test_a_patch_changes_only_what_it_names():
    current = VoiceSettings(speaker="serena", tone="calm", speed=1.25, read_aloud=True, correct_speech=False)
    assert apply_patch(current, VoicePatch(speed=2.0)) == VoiceSettings("serena", "calm", 2.0, True, False)
    assert apply_patch(current, VoicePatch(correct_speech=True, read_aloud=False)) == VoiceSettings(
        "serena", "calm", 1.25, False, True)
    assert apply_patch(current, VoicePatch()) == current


async def test_the_service_saves_merges_and_publishes_the_bot(world):
    w = world
    saved = await w["service"].save(w["user"], w["bot"].id, VoicePatch(speaker="ryan", correct_speech=True))
    assert saved is not None and saved.voice == VoiceSettings("ryan", "natural", 1.0, False, True)
    assert (await w["bots"].get(w["user"], w["bot"].id)).voice == saved.voice
    kinds = [f["type"] for _, f in w["events"].frames]
    assert kinds == ["bot_updated"]
    assert w["events"].frames[0][1]["bot"]["voice"] == {"speaker": "ryan", "tone": "natural", "speed": 1.0,
                                                        "read_aloud": False, "correct_speech": True,
                                                        "correct_english": True, "language": "auto"}
    assert await w["service"].save(w["user"], "no-such-bot", VoicePatch(speed=2.0)) is None
    assert await w["service"].save("someone-else", w["bot"].id, VoicePatch(speed=2.0)) is None


# -- the tool ----------------------------------------------------------------------------------------------------


async def test_the_tool_changes_the_calling_bots_own_voice_and_says_so(world):
    w = world
    outcome = await w["tools"].run(SET_MY_VOICE, {"speed": 1.5, "tone": "warm"}, _ctx(w))
    assert not outcome.failed and outcome.text == voice_changed_text(VoicePatch(speed=1.5, tone="warm"))
    assert "1.5" in outcome.text and "Warm" in outcome.text
    assert (await w["bots"].get(w["user"], w["bot"].id)).voice == VoiceSettings("aiden", "warm", 1.5, False, False)
    assert (await w["bots"].get(w["user"], w["other"].id)).voice == DEFAULT_VOICE   # never another bot's
    assert w["tools"].activity(SET_MY_VOICE) == "changing my voice"


async def test_the_tool_turns_switches_on_and_off(world):
    w = world
    await w["tools"].run(SET_MY_VOICE, {"read_aloud": True, "correct_english": True}, _ctx(w))
    assert (await w["bots"].get(w["user"], w["bot"].id)).voice == VoiceSettings("aiden", "natural", 1.0, True, True)
    await w["tools"].run(SET_MY_VOICE, {"correct_english": False}, _ctx(w))
    assert (await w["bots"].get(w["user"], w["bot"].id)).voice == VoiceSettings("aiden", "natural", 1.0, True, False)
    outcome = await w["tools"].run(SET_MY_VOICE, {"correct_speech": True, "language": "es"}, _ctx(w))
    assert "Correct what I say on" in outcome.text and "language Spanish" in outcome.text
    assert (await w["bots"].get(w["user"], w["bot"].id)).voice == VoiceSettings("aiden", "natural", 1.0, True, True, "es")
    assert (await w["tools"].run(SET_MY_VOICE, {"language": "ka"}, _ctx(w))).failed


@pytest.mark.parametrize("args", [
    {}, {"speaker": "nobody"}, {"tone": "angry"}, {"speed": 3.0}, {"speed": "fast"}, {"read_aloud": "yes"},
    {"correct_english": 1}, {"extra": True},
])
async def test_bad_arguments_are_refused_before_anything_changes(world, args):
    w = world
    outcome = await w["tools"].run(SET_MY_VOICE, args, _ctx(w))
    assert outcome.failed and outcome.text == BAD_VOICE_ARGS
    assert (await w["bots"].get(w["user"], w["bot"].id)).voice == DEFAULT_VOICE
    assert w["events"].frames == []


async def test_the_card_step_names_the_change_and_execute_runs_the_stored_call(world):
    w = world
    pending = await w["tools"].prepare(SET_MY_VOICE, {"speed": 0.75, "speaker": "serena"}, _ctx(w, tainted=True))
    assert isinstance(pending, PendingCall)
    assert pending.title == "Change my voice" and pending.tool == SET_MY_VOICE
    assert pending.arguments == {"speed": 0.75, "speaker": "serena"}
    assert "Serena" in pending.detail and "0.75" in pending.detail
    assert await w["tools"].prepare(SET_MY_VOICE, {"speed": 9}, _ctx(w)) == BAD_VOICE_ARGS
    outcome = await w["tools"].execute(SET_MY_VOICE, dict(pending.arguments), _ctx(w, tainted=True))
    assert not outcome.failed
    assert (await w["bots"].get(w["user"], w["bot"].id)).voice == VoiceSettings("serena", "natural", 0.75, False, False)


async def test_the_domain_tools_know_the_tool(world):
    domain = build_domain_tools(world["cfg"], EventHub(world["cfg"]))
    assert domain.handles(SET_MY_VOICE)
    outcome = await domain.run(SET_MY_VOICE, {"speed": 1.15}, _ctx(world))
    assert not outcome.failed
    assert (await world["bots"].get(world["user"], world["bot"].id)).voice.speed == 1.15


# -- a call in progress -------------------------------------------------------------------------------------------


class _Bots:
    def __init__(self, voice: VoiceSettings) -> None:
        self.voice = voice

    async def get(self, user_id: str, bot_id: str):
        return SimpleNamespace(id=bot_id, voice=self.voice)


async def test_a_call_speaks_its_next_part_in_the_new_voice():
    old = VoiceSettings("aiden", "natural", 1.0, False, False)
    new = VoiceSettings("serena", "warm", 1.5, False, True)
    events, voice, cache, bots = _Events(), FakeVoice(), SpeechCache(), _Bots(old)
    calls = CallRegistry(clock=lambda: 0.0)
    locks: dict[str, asyncio.Lock] = {}
    ahead = SpeakAhead(events, bots, voice, cache, calls, speak_lock_for=lambda u: locks.setdefault(u, asyncio.Lock()),
                       clock=lambda: 0.0)
    calls.beat("u1", "t1", "b1")
    ahead.listen("u1", {"type": "message", "thread_id": "t1", "message": {
        "id": "m1", "thread_id": "t1", "role": "bot", "body": "", "seq": 0, "kind": "text", "author_bot_id": "b1"}})
    ahead.listen("u1", {"type": "text_delta", "thread_id": "t1", "message_id": "m1", "delta": "First part. "})
    await ahead.wait_idle()
    assert cache.get(("m1", 0, "aiden", "natural")) is not None
    bot_frame = {"type": "bot_updated", "bot": {"id": "b1", "voice": json.loads(json.dumps({
        "speaker": "serena", "tone": "warm", "speed": 1.5, "read_aloud": False, "correct_english": True}))}}
    ahead.listen("u1", bot_frame)
    assert ahead.track("m1").voice == new
    ahead.listen("u1", {"type": "text_delta", "thread_id": "t1", "message_id": "m1", "delta": "Second part."})
    ahead.listen("u1", {"type": "message_done", "thread_id": "t1", "message_id": "m1"})
    await ahead.wait_idle()
    assert cache.get(("m1", 1, "serena", "warm")) is not None
    # a frame with a strange voice, or for another bot, changes nothing
    ahead.listen("u1", {"type": "bot_updated", "bot": {"id": "b1", "voice": {"speaker": "nobody"}}})
    ahead.listen("u1", {"type": "bot_updated", "bot": {"id": "b2", "voice": {"speaker": "ryan", "tone": "calm",
                                                                             "speed": 1.0, "read_aloud": False}}})
    assert ahead.track("m1").voice == new
