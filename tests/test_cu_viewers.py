"""Owner, 2026-10-25: Gela asked again and again to close a photo, open a picture or press Escape, and scrolled a
PDF forty times blind. Keys that commit nothing never ask, a short Open/View label is browsing, and a third scroll
in a row without a look is refused until the bot looks."""

from __future__ import annotations

import pytest

from cu_run_helpers import make_cu_rig, step
from roost.computer_use.commit_words import commit_class
from roost.computer_use.runner import BLIND_SCROLL_TEXT
from roost.config import load_config
from roost.constants import CU_BLIND_SCROLLS_MAX
from roost.db.connection import init_db
from test_commit_words import _t


@pytest.mark.parametrize("key", ["Escape", "Tab", "Shift+Tab", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight",
                                 "PageUp", "PageDown", "Home", "End"])
def test_a_key_that_commits_nothing_never_asks_even_with_nothing_focused(key):
    assert commit_class(None, key=key) == "browsing"


@pytest.mark.parametrize("key", ["Space", "Delete", "Backspace"])
def test_keys_that_may_commit_still_need_a_known_target(key):
    assert commit_class(None, key=key) == "unknown"


@pytest.mark.parametrize("label", ["Open picture", "Open photo", "View image", "Show more", "Preview", "Play video",
                                   "Ver foto", "Abrir imagen", "Expand"])
def test_a_short_open_or_view_label_is_browsing(label):
    assert commit_class(_t(label)) == "browsing", label


@pytest.mark.parametrize("label", ["Open account", "Open a new account", "View and pay", "Abrir cuenta",
                                   "Open and send"])
def test_an_open_that_names_an_account_or_an_action_still_asks(label):
    assert commit_class(_t(label)) not in ("browsing", "consent"), label


@pytest.fixture
async def rig():
    config = load_config()
    await init_db(config)
    return await make_cu_rig(config)


async def test_scrolling_blind_is_capped_until_the_bot_looks(rig):
    cu = rig.computer()
    await step(cu, "look")
    for _ in range(CU_BLIND_SCROLLS_MAX):
        assert "Scrolled down" in (await step(cu, "scroll", direction="down", amount=2)).text
    scrolls = len([p for p in rig.events.pointers() if p["kind"] == "scroll"])
    assert (await step(cu, "scroll", direction="down", amount=2)).text == BLIND_SCROLL_TEXT
    assert len([p for p in rig.events.pointers() if p["kind"] == "scroll"]) == scrolls
    await step(cu, "look")
    assert "Scrolled up" in (await step(cu, "scroll", direction="up", amount=2)).text


def test_enter_with_nothing_focused_still_asks():
    """A page may listen for Enter on a whole dialog ("Delete chat?"), so Enter on no control stays unknown."""
    assert commit_class(None, key="Enter") == "unknown"


def test_enter_in_a_chat_box_still_asks():
    box = _t("Type a message", kind="field", tag="div", editable=True)
    assert commit_class(box, key="Enter") not in ("browsing", "consent")


def test_going_back_is_a_key_that_commits_nothing():
    from roost.constants import CU_KEYS
    assert CU_KEYS["Back"] == "XF86Back"
    assert commit_class(None, key="Back") == "browsing"
