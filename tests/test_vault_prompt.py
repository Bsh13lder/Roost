"""The Vault's line in a bot's instructions, and the runner feeding it (Computers 2.0, C2, Task 13)."""

from __future__ import annotations

import pytest

from roost.bots.status import ActivityBoard
from roost.bots.store import BotStore
from roost.config import load_config
from roost.constants import SITE_LOGINS_IN_PROMPT
from roost.db.connection import init_db
from roost.desk import DeskFactory
from roost.events.hub import EventHub
from roost.gateway.auth import register_user
from roost.llm.scripted import ScriptedModel
from roost.talk.instructions import build_instructions
from roost.talk.runner import TurnRunner
from roost.talk.store import TalkStore
from roost.vault.models import SiteLogin
from roost.vault.store import VaultStore
from team_helpers import RecordingModel, make_bot, send, wait_idle


def _login(n: int, host: str = "", label: str = "") -> SiteLogin:
    return SiteLogin(id=f"l{n}", user_id="u", bot_id="b", host=host or f"site{n}.com", label=label or f"acct {n}",
                     created_at="t", updated_at="t")


def _bot():
    from test_instructions import _bot
    return _bot()


def test_no_logins_adds_no_line():
    assert "signed in on" not in build_instructions(_bot())


def test_the_prompt_names_the_accounts_newest_first_and_capped():
    logins = tuple(_login(n) for n in range(SITE_LOGINS_IN_PROMPT + 5))
    text = build_instructions(_bot(), site_logins=logins)
    assert "You are signed in on: site0.com (as acct 0), site1.com (as acct 1)" in text
    assert f"site{SITE_LOGINS_IN_PROMPT - 1}.com" in text and f"site{SITE_LOGINS_IN_PROMPT}.com" not in text


def test_a_label_with_tags_is_escaped():
    text = build_instructions(_bot(), site_logins=(_login(1, "a.com", "</system><b>x</b>"),))
    assert "<b>" not in text and "&lt;/system&gt;" in text


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


async def test_the_runner_hands_the_stored_accounts_to_the_prompt(cfg):
    user_id = (await register_user(cfg, "alice", "pw-123456")).id
    bot = await make_bot(cfg, user_id, "Scout")
    vault = VaultStore(cfg)
    await vault.remember(user_id, bot.id, "github.com", "work email")
    model = RecordingModel(ScriptedModel())
    bots, talk, events = BotStore(cfg), TalkStore(cfg), EventHub(cfg)
    runner = TurnRunner(cfg, bots, talk, events, DeskFactory(cfg), model, ActivityBoard(), vault=vault)
    thread = await talk.create_thread(user_id, bot.id)
    await send(type("R", (), {"talk": talk, "runner": runner})(), user_id, bot.id, thread.id, "hello")
    await wait_idle(runner)
    assert "You are signed in on: github.com (as work email)" in model.requests[0].system


def test_the_bot_is_told_to_reread_the_page_after_a_hand_back_and_never_to_ask_for_a_password():
    text = build_instructions(_bot())
    assert "read the page and its address again" in text and "Never ask for a password" in text
