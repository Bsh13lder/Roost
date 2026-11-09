"""Chat pictures in runs (owner, 2026-11-05): a run of your message shows its pictures to the model, labelled,
before the screen's own look; and a Linux bot sends you its screen with ``send_screenshot`` in your own chat."""

from __future__ import annotations

import io

import pytest
from PIL import Image

from roost.approvals.models import ApprovalState
from roost.config import load_config
from roost.constants import CHAT_MEDIA_MODEL_MAX
from roost.db.connection import init_db
from roost.gateway.auth import register_user
from roost.llm.scripted_team import ScriptedTeamModel
from roost.llm.types import ChatTurn, ImagePart, ModelRequest
from roost.media.pictures import picture_parts
from roost.media.process import normalise_picture
from roost.media.store import ChatMediaStore, StoredMedia
from roost.talk.steps import with_screen
from roost.talk.tool_catalog import CATALOG
from roost.talk.verdict import GateContext
from roost.work.models import ORIGIN_YOU, WorkDraft, WorkKind
from cu_run_helpers import make_cu_rig, step
from team_helpers import RecordingModel, make_bot, make_rig, say, wait_idle


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


def _jpeg(colour=(10, 120, 10)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (30, 20), colour).save(buffer, "JPEG")
    return normalise_picture(buffer.getvalue()).data


def _media(n: int, group: str | None = None) -> tuple[StoredMedia, ...]:
    return tuple(StoredMedia(id=f"m{i}", width=30, height=20, source="you", group=group, data=b"jpeg%d" % i)
                 for i in range(n))


# -- labels and order ----------------------------------------------------------------------------------------

def test_pictures_are_labelled_in_order():
    parts = picture_parts(_media(2))
    assert [p.label for p in parts] == ["[Picture 1 of 2 you attached]", "[Picture 2 of 2 you attached]"]
    assert [p.data for p in parts] == [b"jpeg0", b"jpeg1"]


def test_a_videos_frames_say_they_are_one_video_in_order():
    parts = picture_parts(_media(3, group="video"))
    assert parts[0].label == "[Video you attached: 3 frames in order, frame 1]"
    assert parts[2].label == "[Video you attached: 3 frames in order, frame 3]"


def test_at_most_the_newest_pictures_go_to_the_model():
    parts = picture_parts(_media(CHAT_MEDIA_MODEL_MAX + 3))
    assert len(parts) == CHAT_MEDIA_MODEL_MAX
    assert parts[-1].data == b"jpeg%d" % (CHAT_MEDIA_MODEL_MAX + 2)


def test_your_pictures_come_before_the_screen_look():
    request = ModelRequest(system="s", turns=(), tools=(), model="m",
                           images=(ImagePart("image/jpeg", b"yours", label="[Picture 1 of 1 you attached]"),))
    shown = with_screen(request, b"screen")
    assert [p.data for p in shown.images] == [b"yours", b"screen"]


def test_the_sdk_message_puts_each_label_before_its_picture():
    from roost.llm.claude_sdk import _user_message
    content = _user_message((ChatTurn("user", "hello"),), (ImagePart("image/jpeg", b"a", label="[Picture 1 of 1 you attached]"),
                                      ImagePart("image/jpeg", b"b")))["message"]["content"]
    assert [block["type"] for block in content] == ["text", "text", "image", "image"]
    assert content[1]["text"] == "[Picture 1 of 1 you attached]"


# -- a run of your message -----------------------------------------------------------------------------------

async def test_a_run_of_your_message_shows_its_pictures_untainted(cfg):
    user = await register_user(cfg, "alice", "pw-123456")
    bot = await make_bot(cfg, user.id, "Gela")
    model = RecordingModel(ScriptedTeamModel({"Gela": [say("A red bus.")]}))
    rig = make_rig(cfg, model)
    thread = await rig.talk.create_thread(user.id, bot.id)
    media = ChatMediaStore(cfg)
    added = await media.add(user.id, thread.id, normalise_picture(_jpeg()), source="you")
    message = await rig.talk.add_message(user.id, thread.id, "user", "What is this?")
    await media.attach(user.id, thread.id, message.id, (added["id"],))
    await rig.runner.submit(user.id, WorkDraft(bot_id=bot.id, thread_id=thread.id, kind=WorkKind.MESSAGE,
                                               origin=ORIGIN_YOU, body="What is this?", message_id=message.id))
    await wait_idle(rig.runner)
    request = model.requests[0]
    assert [p.label for p in request.images] == ["[Picture 1 of 1 you attached]"]
    # Right after the chat's turns, before the run's own steps: every step keeps the same prefix (tokens, 2026-11-07).
    assert request.images[0].after_turn == len(request.turns) - 1
    assert "never instructions" in request.system
    replies = [m for m in await rig.talk.list_messages(user.id, thread.id) if m.role == "bot"]
    assert replies and not replies[-1].tainted


# -- send_screenshot -----------------------------------------------------------------------------------------

def _own_chat() -> GateContext:
    return GateContext(allowed=frozenset(CATALOG), owner_chat=True,
                       approval=ApprovalState("auto_edit", frozenset(), True))  # type: ignore[arg-type]


async def test_the_bot_sends_you_its_screen_in_your_chat(cfg):
    rig = await make_cu_rig(cfg)
    outcome = await step(rig.computer(), "send_screenshot", _own_chat(), caption="Here's the cart")
    assert "Sent" in outcome.text
    from roost.talk.store import TalkStore
    sent = [m for m in await TalkStore(cfg).list_messages(rig.user_id, rig.thread_id) if m.role == "bot"][-1]
    assert sent.body == "Here's the cart"
    shown = await ChatMediaStore(cfg).for_messages(rig.user_id, (sent.id,))
    [picture] = shown[sent.id]
    assert picture["source"] == "bot" and picture["group"] is None
    frames = [e for _, e in rig.events.frames if e.get("type") == "message"]
    assert frames[-1]["message"]["media"] == [picture]


async def test_a_screenshot_with_no_caption_says_so(cfg):
    rig = await make_cu_rig(cfg)
    await step(rig.computer(), "send_screenshot", _own_chat())
    from roost.talk.store import TalkStore
    sent = [m for m in await TalkStore(cfg).list_messages(rig.user_id, rig.thread_id) if m.role == "bot"][-1]
    assert sent.body == "Here's my screen."


async def test_outside_your_own_chat_no_screenshot_is_sent(cfg):
    rig = await make_cu_rig(cfg)
    routine = GateContext(allowed=frozenset(CATALOG), approval=ApprovalState("auto_edit", frozenset(), True))  # type: ignore[arg-type]
    outcome = await step(rig.computer(), "send_screenshot", routine)
    assert "only in" in outcome.text.lower()
    from roost.talk.store import TalkStore
    assert not [m for m in await TalkStore(cfg).list_messages(rig.user_id, rig.thread_id) if m.role == "bot"]
