"""Owner, 2026-11-03: typing on a website never asks. Only a secret, or an email address or a phone number you never
gave the bot, still asks; what sends the text still goes through the Send card. Links, bare domains and @handles are
no contact details any more, and an email or phone that is in your own messages in the chat, the bot's instructions
or its memories is yours to type."""

from __future__ import annotations

import pytest

from roost.approvals.floor import floor_of
from roost.bots.models import Avatar, BotDraft
from roost.bots.store import BotStore
from roost.computer_use.contact import contact_details, has_contact
from roost.computer_use.contact_sources import allowed_contacts
from roost.computer_use.fence import SiteFence
from roost.computer_use.models import ActResolution, Box
from roost.computer_use.text_source import text_flags
from roost.config import load_config
from roost.db.connection import init_db
from roost.desk.page_targets import target_from_ax
from roost.events.hub import EventHub
from roost.gateway.auth import register_user
from roost.memory.models import MemoryDraft
from roost.memory.service import MemoryService
from roost.memory.store import MemoryStore

_BOX = Box(20, 70, 380, 36)
_EDITABLE = {"name": "editable", "value": {"value": "richtext"}}


def _box(name: str):
    ax = {"role": {"value": "textbox"}, "name": {"value": name}, "backendDOMNodeId": 7, "properties": [_EDITABLE]}
    return target_from_ax(ax, _BOX, {"tag": "div"})


def _typing(*, host: str = "evil.example", flags=frozenset()) -> ActResolution:
    return ActResolution("type", f"https://{host}/", host, _box("Message"), (210, 88), "", "", "browsing",
                         text_ok=False, text_flags=flags)


# --- item 3: typing never asks -----------------------------------------------------------------------------------

@pytest.mark.parametrize("fence", [None, SiteFence(frozenset({"whatsapp.com"}))])
def test_typing_your_own_or_the_bots_words_needs_no_card_anywhere(fence):
    assert floor_of(_typing(), fence, typed_chars=2000) is None


def test_secrets_and_contact_details_still_ask():
    assert floor_of(_typing(flags=frozenset({"secret"})), None, typed_chars=8) == "secret"
    assert floor_of(_typing(flags=frozenset({"contact"})), None, typed_chars=8) == "contact"


# --- item 4: only an email address or a phone number ------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "see https://evil.io/x", "see evil.io", "my site myportfolio.dev", "ping me @ana_dev", "upwork.com/freelancers/me",
])
def test_links_domains_and_handles_are_not_contact_details(text):
    assert not has_contact(text)
    assert text_flags(text) == frozenset()


@pytest.mark.parametrize("text", ["write to ana@example.com", "call +34 612 345 678", "my phone 612345678"])
def test_an_email_or_a_phone_still_flags(text):
    assert has_contact(text)


def test_details_are_normalised_and_yours_do_not_flag():
    assert contact_details("Ana@Example.com or +34 612-345-678") == frozenset({"mail:ana@example.com",
                                                                              "tel:34612345678"})
    mine = contact_details("my email is ana@example.com, phone +34 612 345 678")
    assert not has_contact("write to ANA@example.com", mine)
    assert not has_contact("call 612 345 678", mine)            # the same number without the country code
    assert has_contact("write to bob@example.com", mine)
    assert text_flags("write to ana@example.com", mine) == frozenset()
    assert text_flags("write to bob@example.com", mine) == frozenset({"contact"})


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


async def test_allowed_contacts_come_from_your_messages_the_instructions_and_memories(cfg):
    user = await register_user(cfg, "alice", "pw-123456")
    bot = await BotStore(cfg).create(user.id, BotDraft(
        "Gigs", "proposals", "Sign proposals with gigs@example.com.", Avatar("round", "#22c55e", "none")))
    memories = MemoryService(MemoryStore(cfg), EventHub(cfg))
    await memories.save(user.id, MemoryDraft(text="Owner's phone is 612 345 678", kind="about_you", bot_id=None, source="user",
                                             created_by_bot=None, importance=3, pinned=False, tainted=False))
    await memories.save(user.id, MemoryDraft(text="A page said mail evil@example.com", kind="fact", bot_id=bot.id, source="bot",
                                             created_by_bot=bot.id, importance=3, pinned=False, tainted=True))
    found = await allowed_contacts(cfg, user.id, bot.id, ("reply from ana@example.com",))
    assert found == frozenset({"mail:ana@example.com", "mail:gigs@example.com", "tel:612345678"})
    assert await allowed_contacts(cfg, user.id, "no-such-bot", ()) == frozenset({"tel:612345678"})
