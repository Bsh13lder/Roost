"""Unit tests for ``roost.bots.store.BotStore`` and the activity board /
serializer it ships with (``roost/bots/status.py``, ``roost/bots/service.py``).

The first four tests are verbatim-in-spirit from the Task 3 brief (one
deviation, noted below). The rest cover behavior the contract requires
that the brief's starter tests don't exercise: full create/get/list/
update/delete roundtrips, duplicate-name on update, avatar JSON
roundtripping, and the ``ActivityBoard``/``bot_out`` pieces.

Deviation from the brief: the brief's ``test_sensitive_fields_are_
ciphertext_on_disk`` pseudocode asserts ciphertext starts with
``"enc:v1:"``. The contract's own crypto module
(``roost/crypto/encryption.py``) only ever produces ``enc:v1`` when NO
AAD is passed, and ``enc:v2`` when an AAD is passed — and the design
spec (``docs/specs/2026-10-12-roost-design.md`` §4.7) explicitly says
"New bot tables ... use the existing `enc:v2` format, with AAD". Per the
Global Constraints ("every user-content column is `enc:v1` encrypted
... with an AAD") Roost's bots columns must carry an AAD (to bind
ciphertext to user+field), which this codebase's crypto module can only
do by writing `enc:v2`. Following the contract/spec here: the test below
asserts the literal `"enc:v2:"` prefix (not `"enc:v1:"`) and additionally
uses ``is_encrypted()`` so it stays correct if the version ever changes.
"""

from __future__ import annotations

import json

import pytest

import asyncio

from roost.bots.models import Avatar, Bot, BotDraft, BotPatch, BotStatus, DuplicateBotName
from roost.bots.service import bot_out
from roost.bots.status import ActivityBoard
from roost.bots.store import BotStore
from roost.config import load_config
from roost.crypto.encryption import is_encrypted
from roost.db.connection import db_session, init_db
from roost.events.hub import EventHub
from roost.gateway.auth import register_user

AVATAR = Avatar("round", "#22c55e", "none")


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def store(cfg):
    return BotStore(cfg)


@pytest.fixture
async def user(cfg):
    u = await register_user(cfg, "alice", "pw-123456")
    return u.id


@pytest.fixture
async def other_user(cfg):
    u = await register_user(cfg, "bob", "pw-123456")
    return u.id


# ---------------------------------------------------------------------------
# Brief's starter tests
# ---------------------------------------------------------------------------

async def test_name_unique_ignoring_case(store, user):
    await store.create(user, BotDraft(name="Scout", job="read news", instructions="be brief", avatar=AVATAR))
    with pytest.raises(DuplicateBotName):
        await store.create(user, BotDraft(name=" scout", job="read news", instructions="be brief", avatar=AVATAR))


async def test_sensitive_fields_are_ciphertext_on_disk(store, user, cfg):
    bot = await store.create(
        user,
        BotDraft(name="Scout", job="read news", instructions="be brief", avatar=AVATAR),
    )
    async with db_session(cfg) as db:
        row = await (await db.execute("SELECT name, job, instructions FROM bots WHERE id=?", (bot.id,))).fetchone()
    values = [row["name"], row["job"], row["instructions"]]
    assert all(is_encrypted(v) for v in values)
    assert all(v.startswith("enc:v2:") for v in values)  # AAD-bound, see module docstring
    assert "Scout" not in "".join(values)
    assert "read news" not in "".join(values)
    assert "be brief" not in "".join(values)


async def test_other_user_cannot_see_or_change(store, user, other_user):
    bot = await store.create(user, BotDraft(name="Scout", job="read news", instructions="be brief", avatar=AVATAR))

    assert await store.get(other_user, bot.id) is None
    assert await store.update(other_user, bot.id, BotPatch(name="Hijacked")) is None
    assert await store.delete(other_user, bot.id) is False

    # The owner's bot survived every one of the other user's attempts.
    still_there = await store.get(user, bot.id)
    assert still_there is not None and still_there.name == "Scout"


async def test_reset_on_boot_moves_on_it_to_resting(store, user):
    bot = await store.create(user, BotDraft(name="Scout", job="read news", instructions="be brief", avatar=AVATAR))
    other = await store.create(user, BotDraft(name="Helper", job="sort mail", instructions="", avatar=AVATAR))
    await store.set_status(user, bot.id, BotStatus.ON_IT)
    await store.set_status(user, other.id, BotStatus.STUCK)

    moved = await store.reset_on_boot()

    assert moved == 1
    assert (await store.get(user, bot.id)).status == BotStatus.RESTING
    assert (await store.get(user, other.id)).status == BotStatus.STUCK  # untouched


async def test_reset_on_boot_publishes_a_resting_bot_status_for_each_bot_it_resets(store, user, cfg):
    """Final review, finding 3: a gateway restart mid-turn (e.g. Ctrl-C
    of `make dev`) leaves a bot's row ON_IT; ``reset_on_boot`` moves it
    back to RESTING in the DB, but published nothing -- a client whose
    WS connection survives/reconnects across the restart never learns
    about it, and (per the same finding) a resumed replay could even
    re-apply the STALE on_it frame from before the restart on top of a
    fresh snapshot. Publishing a real event here is what lets the
    snapshot (or a replay) actually reflect the reset."""
    bot = await store.create(user, BotDraft(name="Scout", job="read news", instructions="", avatar=AVATAR))
    other = await store.create(user, BotDraft(name="Helper", job="sort mail", instructions="", avatar=AVATAR))
    await store.set_status(user, bot.id, BotStatus.ON_IT)
    await store.set_status(user, other.id, BotStatus.STUCK)  # untouched -- must get no event

    events = EventHub(cfg)
    sub = events.subscribe(user)

    moved = await store.reset_on_boot(events)

    assert moved == 1
    frame = await asyncio.wait_for(sub.__anext__(), timeout=2)
    sub.close()
    assert frame["type"] == "bot_status"
    assert frame["bot_id"] == bot.id
    assert frame["status"] == BotStatus.RESTING.value
    assert frame["activity"] is None


async def test_reset_on_boot_without_an_event_hub_still_resets(store, user):
    """``events`` stays optional -- existing callers (and this module's
    own tests above) that don't care about live notification keep
    working unchanged."""
    bot = await store.create(user, BotDraft(name="Scout", job="read news", instructions="", avatar=AVATAR))
    await store.set_status(user, bot.id, BotStatus.ON_IT)

    moved = await store.reset_on_boot()

    assert moved == 1
    assert (await store.get(user, bot.id)).status == BotStatus.RESTING


# ---------------------------------------------------------------------------
# Additional coverage
# ---------------------------------------------------------------------------

async def test_create_returns_resting_bot_with_iso_timestamps(store, user):
    bot = await store.create(user, BotDraft(name="Scout", job="read news", instructions="be brief", avatar=AVATAR))
    assert bot.status == BotStatus.RESTING
    assert bot.model_override is None
    assert bot.template_id is None
    assert bot.created_at == bot.updated_at
    assert "T" in bot.created_at  # ISO-8601


async def test_an_avatar_stored_before_the_robots_has_no_screen_and_reads_as_glow(store, user, cfg):
    bot = await store.create(user, BotDraft(name="Scout", job="read news", instructions="", avatar=AVATAR))
    for legacy in ({"shape": "egg", "color": "#14b8a6", "badge": "none"},   # the row as S1.6 wrote it
                   {"shape": "egg", "color": "#14b8a6"}):                    # and one with no badge either
        async with db_session(cfg) as db:
            await db.execute("UPDATE bots SET avatar=? WHERE id=?", (json.dumps(legacy), bot.id))
            await db.commit()
        assert (await store.get(user, bot.id)).avatar == Avatar("egg", "#14b8a6", "none", "glow")


async def test_get_roundtrips_avatar_and_text_fields(store, user):
    created = await store.create(
        user, BotDraft(name="Scout", job="read the news", instructions="be brief", avatar=AVATAR, template_id="tmpl-1"),
    )
    fetched = await store.get(user, created.id)
    assert fetched == created
    assert fetched.avatar == AVATAR
    assert fetched.template_id == "tmpl-1"


async def test_get_unknown_bot_returns_none(store, user):
    assert await store.get(user, "nonexistent-id") is None


async def test_list_returns_empty_when_no_bots(store, user):
    assert await store.list(user) == []


async def test_list_returns_only_own_bots(store, user, other_user):
    mine = await store.create(user, BotDraft(name="Scout", job="read news", instructions="", avatar=AVATAR))
    await store.create(other_user, BotDraft(name="Other", job="sort mail", instructions="", avatar=AVATAR))

    mine_list = await store.list(user)
    assert [b.id for b in mine_list] == [mine.id]

    theirs_list = await store.list(other_user)
    assert mine.id not in [b.id for b in theirs_list]


async def test_update_changes_fields_and_bumps_updated_at(store, user):
    bot = await store.create(user, BotDraft(name="Scout", job="read news", instructions="be brief", avatar=AVATAR))
    new_avatar = Avatar("tall", "#000000", "tasks")

    updated = await store.update(user, bot.id, BotPatch(name="Scout2", job="read more news", avatar=new_avatar))

    assert updated.name == "Scout2"
    assert updated.job == "read more news"
    assert updated.instructions == "be brief"  # untouched field is preserved
    assert updated.avatar == new_avatar
    assert updated.updated_at >= bot.updated_at
    assert updated.created_at == bot.created_at


async def test_update_nonexistent_bot_returns_none(store, user):
    assert await store.update(user, "nonexistent-id", BotPatch(name="X")) is None


async def test_update_to_own_existing_name_raises_duplicate(store, user):
    await store.create(user, BotDraft(name="Scout", job="read news", instructions="", avatar=AVATAR))
    second = await store.create(user, BotDraft(name="Helper", job="sort mail", instructions="", avatar=AVATAR))

    with pytest.raises(DuplicateBotName):
        await store.update(user, second.id, BotPatch(name="SCOUT"))


async def test_delete_then_get_returns_none(store, user):
    bot = await store.create(user, BotDraft(name="Scout", job="read news", instructions="", avatar=AVATAR))

    assert await store.delete(user, bot.id) is True
    assert await store.delete(user, bot.id) is False  # already gone
    assert await store.get(user, bot.id) is None


async def test_set_status_persists(store, user):
    bot = await store.create(user, BotDraft(name="Scout", job="read news", instructions="", avatar=AVATAR))
    await store.set_status(user, bot.id, BotStatus.ASKING_YOU)
    assert (await store.get(user, bot.id)).status == BotStatus.ASKING_YOU


# ---------------------------------------------------------------------------
# ActivityBoard (roost/bots/status.py)
# ---------------------------------------------------------------------------

def test_activity_board_set_get_and_clear():
    board = ActivityBoard()
    assert board.get("bot-1") is None

    board.set("bot-1", "reading your inbox...")
    assert board.get("bot-1") == "reading your inbox..."

    board.set("bot-1", None)
    assert board.get("bot-1") is None


def test_activity_board_tracks_bots_independently():
    board = ActivityBoard()
    board.set("bot-1", "doing a thing")
    board.set("bot-2", "doing another thing")
    assert board.get("bot-1") == "doing a thing"
    assert board.get("bot-2") == "doing another thing"


# ---------------------------------------------------------------------------
# bot_out serializer (roost/bots/service.py)
# ---------------------------------------------------------------------------

def test_bot_out_shape_matches_contract():
    bot = Bot(
        id="b1", user_id="u1", name="Scout", job="read news", instructions="be brief",
        avatar=AVATAR, template_id="tmpl-1", status=BotStatus.ON_IT, model_override="haiku",
        created_at="2026-10-13T00:00:00+00:00", updated_at="2026-10-13T00:00:01+00:00",
    )
    out = bot_out(bot, "reading your inbox...")
    assert out == {
        "id": "b1",
        "name": "Scout",
        "job": "read news",
        "instructions": "be brief",
        "avatar": {"shape": "round", "color": "#22c55e", "badge": "none", "screen": "glow", "picture": None},
        "template_id": "tmpl-1",
        "status": "on_it",
        "activity": "reading your inbox...",
        "model_override": "haiku",
        "model": "haiku",   # the stored choice is shown as it is (the routes only store pickable ones)
        "model_label": "haiku",
        "effort": None,
        "created_at": "2026-10-13T00:00:00+00:00",
        "updated_at": "2026-10-13T00:00:01+00:00",
        "off_duty": False,
        "is_primary": False,
        "notify": True,
        "pinned": False,
        "pinned_at": None,
        "roles": [],
        "group": None,
        "computer": "linux",
        "full_limit_until": None,
        "workspace_internet": False,
        "voice": {"speaker": "aiden", "tone": "natural", "speed": 1.0, "read_aloud": False, "correct_speech": False,
                  "correct_english": False, "language": "auto"},
        "approval": {"mode": "auto_edit", "ask_topics": [], "locked_topics": ["posting"], "auto_review": True},
    }


async def test_set_off_duty_moves_an_idle_bot_and_back(store, user):
    bot = await store.create(user, BotDraft(name="Scout", job="j", instructions="", avatar=AVATAR))
    paused = await store.set_off_duty(user, bot.id, True)
    assert (paused.off_duty, paused.status) == (True, BotStatus.OFF_DUTY)
    back = await store.set_off_duty(user, bot.id, False)
    assert (back.off_duty, back.status) == (False, BotStatus.RESTING)


async def test_starring_moves_the_main_bot(store, user):
    a = await store.create(user, BotDraft(name="Chief", job="j", instructions="", avatar=AVATAR))
    b = await store.create(user, BotDraft(name="Scout", job="j", instructions="", avatar=AVATAR))

    first = await store.set_primary(user, a.id)
    moved = await store.set_primary(user, b.id)

    assert [(x.id, x.is_primary) for x in first] == [(a.id, True)]
    assert [(x.id, x.is_primary) for x in moved] == [(b.id, True), (a.id, False)]
    assert (await store.get_primary(user)).id == b.id


async def test_starring_another_users_bot_changes_nothing(store, user, other_user):
    mine = await store.create(user, BotDraft(name="Chief", job="j", instructions="", avatar=AVATAR))
    await store.set_primary(user, mine.id)
    theirs = await store.create(other_user, BotDraft(name="Chief", job="j", instructions="", avatar=AVATAR))
    assert await store.set_primary(user, theirs.id) is None
    assert (await store.get_primary(user)).id == mine.id
    assert await store.get_primary(other_user) is None


async def test_editing_a_bot_keeps_its_star(store, user):
    a = await store.create(user, BotDraft(name="Chief", job="j", instructions="", avatar=AVATAR))
    await store.set_primary(user, a.id)
    edited = await store.update(user, a.id, BotPatch(job="leads"))
    assert edited.is_primary is True


async def test_set_off_duty_keeps_on_it_until_the_run_ends(store, user):
    bot = await store.create(user, BotDraft(name="Scout", job="j", instructions="", avatar=AVATAR))
    await store.set_status(user, bot.id, BotStatus.ON_IT)
    paused = await store.set_off_duty(user, bot.id, True)
    assert (paused.off_duty, paused.status) == (True, BotStatus.ON_IT)


async def test_set_off_duty_on_another_users_bot_is_none(store, user, other_user):
    bot = await store.create(user, BotDraft(name="Scout", job="j", instructions="", avatar=AVATAR))
    assert await store.set_off_duty(other_user, bot.id, True) is None


def test_bot_out_activity_none_when_resting():
    bot = Bot(
        id="b1", user_id="u1", name="Scout", job="read news", instructions="",
        avatar=AVATAR, template_id=None, status=BotStatus.RESTING, model_override=None,
        created_at="2026-10-13T00:00:00+00:00", updated_at="2026-10-13T00:00:00+00:00",
    )
    assert bot_out(bot, None)["activity"] is None


# ---------------------------------------------------------------------------
# Polish R1: the optional group label
# ---------------------------------------------------------------------------

async def _raw_group(cfg, bot_id: str) -> str | None:
    async with db_session(cfg) as db:
        row = await (await db.execute("SELECT group_label FROM bots WHERE id=?", (bot_id,))).fetchone()
    return row["group_label"]


async def _new_bot(store, user) -> Bot:
    return await store.create(user, BotDraft(name="Scout", job="read news", instructions="be brief", avatar=AVATAR))


async def test_a_new_bot_has_no_group(store, user):
    assert (await _new_bot(store, user)).group is None


async def test_a_group_label_is_stored_sealed_and_read_back(store, user, cfg):
    bot = await _new_bot(store, user)
    updated = await store.update(user, bot.id, BotPatch(group="Home"))
    assert updated.group == "Home"
    assert (await store.get(user, bot.id)).group == "Home"
    raw = await _raw_group(cfg, bot.id)
    assert raw.startswith("enc:") and "Home" not in raw


async def test_update_leaves_the_group_alone_when_not_given(store, user):
    bot = await _new_bot(store, user)
    await store.update(user, bot.id, BotPatch(group="Home"))
    kept = await store.update(user, bot.id, BotPatch(name="Other"))
    assert kept.group == "Home"
    assert (await store.get(user, bot.id)).group == "Home"


@pytest.mark.parametrize("blank", ["", "   "])
async def test_an_empty_group_clears_it(store, user, cfg, blank):
    bot = await _new_bot(store, user)
    await store.update(user, bot.id, BotPatch(group="Home"))
    cleared = await store.update(user, bot.id, BotPatch(group=blank))
    assert cleared.group is None
    assert (await store.get(user, bot.id)).group is None
    assert await _raw_group(cfg, bot.id) is None


async def test_another_user_cannot_set_a_group(store, user, other_user):
    bot = await _new_bot(store, user)
    assert await store.update(other_user, bot.id, BotPatch(group="X")) is None
    assert (await store.get(user, bot.id)).group is None


async def test_set_model_stores_and_clears_the_choice(store, user):
    bot = await store.create(user, BotDraft(name="Scout", job="j", instructions="", avatar=AVATAR))
    assert bot.effort is None
    chosen = await store.set_model(user, bot.id, "claude-opus-5-5", "max")
    assert (chosen.model_override, chosen.effort) == ("claude-opus-5-5", "max")
    assert (await store.get(user, bot.id)).effort == "max"
    cleared = await store.set_model(user, bot.id, None, None)
    assert (cleared.model_override, cleared.effort) == (None, None)


async def test_set_model_on_another_users_bot_changes_nothing(store, user, other_user):
    bot = await store.create(user, BotDraft(name="Scout", job="j", instructions="", avatar=AVATAR))
    assert await store.set_model(other_user, bot.id, "claude-opus-5-5", "low") is None
    mine = await store.get(user, bot.id)
    assert (mine.model_override, mine.effort) == (None, None)


# --- Computers: the bot's computer kind (schema v24) ---

async def test_a_new_bot_gets_its_linux_computer(store, user):
    bot = await store.create(user, BotDraft(name="Scout", job="j", instructions="", avatar=AVATAR))
    assert bot.computer == "linux"
    assert (await store.get(user, bot.id)).computer == "linux"


async def test_patch_sets_the_computer_kind_and_keeps_it_when_absent(store, user):
    bot = await store.create(user, BotDraft(name="Scout", job="j", instructions="", avatar=AVATAR))
    switched = await store.update(user, bot.id, BotPatch(computer="mac_brave"))
    assert switched.computer == "mac_brave"
    assert (await store.get(user, bot.id)).computer == "mac_brave"
    renamed = await store.update(user, bot.id, BotPatch(name="Scout 2"))
    assert renamed.computer == "mac_brave"
    assert (await store.get(user, bot.id)).computer == "mac_brave"


async def test_another_users_bot_cannot_switch_its_computer_in_the_store(store, user, other_user):
    bot = await store.create(user, BotDraft(name="Scout", job="j", instructions="", avatar=AVATAR))
    assert await store.update(other_user, bot.id, BotPatch(computer="mac_brave")) is None
    assert (await store.get(user, bot.id)).computer == "linux"
