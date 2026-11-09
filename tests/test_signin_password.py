"""The Sign-in card's promise, checked through C3: the bot never types into a password or one-time-code box.

Whatever the approval mode, the taint or the text's source, ``type`` and ``press_key`` on a focused secret field
(and a click on one) are refused with the plain sentence, and nothing reaches the computer's screen. Under Take
control you type; nothing in Roost records a keystroke's text."""

from __future__ import annotations

import pytest

from roost.computer_use.gate_rules import ACT_TEXTS
from roost.config import load_config
from roost.db.connection import init_db
from roost.desk import ScreenInput
from roost.desk.fake_cu import fake_target

from cu_run_helpers import ctx, make_cu_rig, step

SECRET_BOXES = (
    fake_target("field", "Password", 100, 100, tag="input", input_type="password", secret_field=True),
    fake_target("field", "One-time code", 100, 100, tag="input", input_type="text", secret_field=True),
)


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


async def _focused_on(rig, monkeypatch, target) -> None:
    async def focused():
        return target

    monkeypatch.setattr(rig.page, "focused", focused)


@pytest.mark.parametrize("box", SECRET_BOXES, ids=["password", "one-time-code"])
@pytest.mark.parametrize("mode, tainted", [("ask", True), ("auto_edit", False), ("plan", False)])
async def test_the_bot_never_types_into_a_secret_box(cfg, monkeypatch, box, mode, tainted):
    rig = await make_cu_rig(cfg)
    cu = rig.computer()
    await step(cu, "look")
    await _focused_on(rig, monkeypatch, box)
    typed = await step(cu, "type", ctx(mode=mode, tainted=tainted), text="hunter2", source={"from": "message"},
                       expect="signed in")
    assert typed.text == ACT_TEXTS.password and typed.parked is None
    pressed = await step(cu, "press_key", ctx(mode=mode, tainted=tainted), key="Enter", expect="signed in")
    assert pressed.text == ACT_TEXTS.password and pressed.parked is None
    assert rig.desk.inputs == () and rig.desk.typed_lengths == () and rig.desk._screen_page.pasted_lengths == ()


async def test_a_click_on_a_password_box_is_refused_and_says_to_take_over(cfg):
    rig = await make_cu_rig(cfg)
    cu = rig.computer()
    await step(cu, "look")
    refused = await step(cu, "click", target={"text": "Password"}, expect="focused")
    assert refused.text == ACT_TEXTS.password and "take over" in refused.text
    assert rig.desk.inputs == ()


def test_a_typed_texts_repr_never_shows_the_text():
    action = ScreenInput("type", text="hunter2", window=(0, 0, 10, 10))
    assert "hunter2" not in repr(action)
