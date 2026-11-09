"""The hearing context (docs/plans/2026-11-06-roost-voice-tuning.md D1): names and site names from the owner's own
words and choices, bounded, remembered a minute per bot, never a reply, a page, a label, an address or a number."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from roost.voice.constants import (
    COMMON_SITE_NAMES, VOICE_CONTEXT_CACHE_S, VOICE_CONTEXT_MEMORY_TERMS_MAX, VOICE_CONTEXT_RECENT_MESSAGES,
    VOICE_CONTEXT_TERMS_MAX, VoiceSettings,
)
from roost.voice.context import HearHints, asr_language, proper_nouns, site_name


# --- the pure parts ---------------------------------------------------------------------------------------------------


def test_proper_nouns_finds_names_but_not_the_word_that_opens_a_sentence():
    text = ("Tell Maka Eremadze that Nino Beridze will call. Yesterday I paid ALSA for the Valencia bus. "
            "Gela knows. The invoice is on Upwork and the chat on WhatsApp.")
    found = proper_nouns(text)
    assert "Maka Eremadze" in found and "Nino Beridze" in found
    assert "ALSA" in found and "Valencia" in found and "Upwork" in found and "WhatsApp" in found
    assert "Gela" not in found          # one capitalised word that opens its sentence: it may just be a sentence
    assert "Tell" not in found and "Yesterday" not in found and "The" not in found and "I" not in found


def test_proper_nouns_keeps_accents_never_repeats_and_reads_a_name_that_opens_a_sentence():
    found = proper_nouns("Dile a María José que Señor Núñez llamó. María José otra vez. Nino Beridze called today.")
    assert found.count("María José") == 1 and "Señor Núñez" in found
    assert "Nino Beridze" in found                        # a two-word run that opens its sentence is kept whole
    assert proper_nouns("Ask Tamar Kiknadze about the flat") == ("Tamar Kiknadze",)   # the verb goes
    assert proper_nouns("Habla con მაკა ერემაძე hoy") == ()  # a script with no case gives nothing


@pytest.mark.parametrize("host, name", [
    ("web.whatsapp.com", "WhatsApp"), ("mail.google.com", "Google"), ("www.upwork.com", "Upwork"),
    ("alsa.es", "ALSA"), ("venta.renfe.com", "Renfe"), ("accounts.bbva.es", "BBVA"), ("idealista.com", "Idealista"),
    ("bbc.co.uk", "Bbc"), ("myshop.example.org", "Example"), ("192.168.1.1", None), ("localhost", None),
    ("", None), ("x.com", "X"),
])
def test_site_name_turns_a_host_into_the_name_people_say(host, name):
    assert site_name(host) == name


def test_asr_language_is_the_models_name_or_none_for_auto():
    assert asr_language("es") == "Spanish" and asr_language("en") == "English"
    assert asr_language("auto") is None and asr_language(None) is None and asr_language("ka") is None


# --- the builder ------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class _Bot:
    id: str
    name: str
    voice: VoiceSettings = VoiceSettings("aiden", "natural", 1.0, False)


@dataclass(frozen=True)
class _Memory:
    text: str
    tainted: bool = False


@dataclass(frozen=True)
class _Message:
    body: str
    role: str = "user"
    kind: str = "text"


@dataclass(frozen=True)
class _Login:
    host: str
    label: str = "me@example.com"


@dataclass(frozen=True)
class _Thread:
    id: str


@dataclass
class _World:
    bots: list = field(default_factory=list)
    memories: list = field(default_factory=list)
    messages: list = field(default_factory=list)
    logins: list = field(default_factory=list)
    reads: int = 0
    thread: _Thread | None = _Thread("t1")

    async def list(self, user_id):
        self.reads += 1
        return list(self.bots)

    async def get(self, user_id, bot_id):
        return next((b for b in self.bots if b.id == bot_id), None)

    async def list_for_bot(self, user_id, bot_id, **kwargs):
        return tuple(self.memories)

    async def main_thread(self, user_id, bot_id):
        return self.thread

    async def list_latest_messages(self, user_id, thread_id, limit=None, **kwargs):
        assert limit == VOICE_CONTEXT_RECENT_MESSAGES
        return list(self.messages)

    async def list_all(self, user_id, limit=50):
        return tuple(self.logins)


def _hints(world: _World, clock=lambda: 0.0) -> HearHints:
    return HearHints(world, world, world, world, clock=clock)


async def test_the_hint_holds_the_bots_names_sites_and_the_owners_own_names_first():
    world = _World(
        bots=[_Bot("b1", "Gela", VoiceSettings("aiden", "natural", 1.0, False, False, "es")), _Bot("b2", "Chief")],
        memories=[_Memory("Her sister is Nino Beridze."), _Memory("Pay Maka Eremadze on Friday", tainted=True)],
        messages=[_Message("Ask Tamar Kiknadze about the flat"), _Message("Sure, Tamar Kiknadze said yes", role="bot"),
                  _Message("Call +34 600 000 000 and mail me@example.com")],
        logins=[_Login("web.whatsapp.com"), _Login("www.upwork.com", label="Secret Label Here")],
    )
    hint = await _hints(world).for_bot("u1", "b1")
    assert hint.terms[:2] == ("Gela", "Chief")                         # the bots first
    assert "WhatsApp" in hint.terms and "Upwork" in hint.terms          # Vault hosts as site names
    assert "Tamar Kiknadze" in hint.terms                               # the owner's own words
    assert "Nino Beridze" in hint.terms                                 # an untainted memory
    assert "Maka Eremadze" not in hint.terms                            # a tainted one never
    assert "Secret Label Here" not in hint.terms and "me@example.com" not in hint.terms
    assert not any(ch.isdigit() for term in hint.terms for ch in term)   # no phone, no number
    assert set(COMMON_SITE_NAMES) <= set(hint.terms) or len(hint.terms) == VOICE_CONTEXT_TERMS_MAX
    assert hint.language == "Spanish" and hint.partial is False


async def test_the_hint_is_bounded_and_the_memory_nouns_are_capped():
    world = _World(bots=[_Bot("b1", "Gela")],
                   memories=[_Memory(" ".join(f"Person{i} Surname{i}." for i in range(80)))])
    hint = await _hints(world).for_bot("u1", "b1")
    assert len(hint.terms) <= VOICE_CONTEXT_TERMS_MAX
    assert sum(1 for t in hint.terms if t.startswith("Person")) <= VOICE_CONTEXT_MEMORY_TERMS_MAX


async def test_no_bot_or_no_chat_still_gives_the_fixed_names_and_auto_language():
    world = _World(bots=[_Bot("b1", "Gela")], thread=None)
    hint = await _hints(world).for_bot("u1", None)
    assert hint.terms[0] == "Gela" and "Google" in hint.terms and hint.language is None
    assert (await _hints(world).for_bot("u1", "b1")).language is None   # auto-detect
    assert (await _hints(world).for_bot("u1", "nope")).language is None


async def test_a_bots_hint_is_remembered_a_minute_and_a_partial_only_marks_it():
    now = [0.0]
    world = _World(bots=[_Bot("b1", "Gela")])
    hints = _hints(world, clock=lambda: now[0])
    first = await hints.for_bot("u1", "b1")
    partial = await hints.for_bot("u1", "b1", partial=True)
    assert partial.terms == first.terms and partial.partial is True and world.reads == 1
    now[0] = VOICE_CONTEXT_CACHE_S + 1
    await hints.for_bot("u1", "b1")
    assert world.reads == 2
    hints.forget()
    await hints.for_bot("u1", "b1")
    assert world.reads == 3
    await hints.for_bot("u2", "b1")          # another user: their own hint
    assert world.reads == 4
