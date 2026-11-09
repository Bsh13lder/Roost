"""Day notes: the sealed store and the service's rules (Batch F, G7)."""

from __future__ import annotations

import sqlite3
from datetime import date

import pytest

from roost.config import load_config
from roost.constants import DAY_NOTE_MAX_YEARS, MAX_DAY_NOTE_LENGTH, MAX_DAY_NOTES_PER_DAY
from roost.crypto.encryption import decrypt_field, user_aad
from roost.crypto.key_manager import get_user_dek
from roost.day_notes.models import DayNoteDraft
from roost.day_notes.service import DayNoteService
from roost.day_notes.store import DayNoteStore
from roost.db.connection import get_db_path, init_db
from roost.gateway.auth import register_user

TODAY = date(2026, 10, 21)


class Events:
    def __init__(self):
        self.sent: list[tuple[str, dict]] = []

    async def publish(self, user_id, event):
        self.sent.append((user_id, event))
        return len(self.sent)


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def users(cfg):
    return (await register_user(cfg, "alice", "pw-123456")).id, (await register_user(cfg, "bob", "pw-123456")).id


def _service(cfg, events=None):
    return DayNoteService(DayNoteStore(cfg), events or Events(), today=lambda: TODAY)


async def test_text_is_sealed_with_its_aad(cfg, users):
    alice, _ = users
    note = await DayNoteStore(cfg).add(alice, DayNoteDraft(day=TODAY, text="secret plan"), bot_id=None, tainted=False)
    con = sqlite3.connect(get_db_path(cfg))
    raw = con.execute("SELECT text, day FROM day_notes WHERE id = ?", (note.id,)).fetchone()
    con.close()
    assert raw[0].startswith("enc:v2") and "secret" not in raw[0] and raw[1] == "2026-10-21"
    dek = await get_user_dek(cfg, alice)
    assert decrypt_field(raw[0], dek, user_aad(alice, "day_notes:text")) == "secret plan"
    assert decrypt_field(raw[0], dek, user_aad(alice, "notes:text")) == "[encrypted]"   # the wrong AAD opens nothing


async def test_list_range_is_per_user_and_ordered(cfg, users):
    alice, bob = users
    store = DayNoteStore(cfg)
    for day, text in ((date(2026, 10, 22), "b"), (date(2026, 10, 21), "a"), (date(2026, 11, 30), "far")):
        await store.add(alice, DayNoteDraft(day=day, text=text), bot_id=None, tainted=False)
    await store.add(bob, DayNoteDraft(day=TODAY, text="bobs"), bot_id=None, tainted=False)
    found = await store.list_range(alice, date(2026, 10, 1), date(2026, 10, 31), 100)
    assert [n.text for n in found] == ["a", "b"] and {n.user_id for n in found} == {alice}
    assert await store.count_on(alice, TODAY) == 1 and await store.count_on(bob, date(2026, 10, 22)) == 0


async def test_delete_is_per_user(cfg, users):
    alice, bob = users
    store = DayNoteStore(cfg)
    note = await store.add(alice, DayNoteDraft(day=TODAY, text="mine"), bot_id=None, tainted=False)
    assert await store.delete(bob, note.id) is False
    assert len(await store.list_range(alice, TODAY, TODAY, 10)) == 1
    assert await store.delete(alice, note.id) is True and await store.delete(alice, note.id) is False


async def test_text_length_and_day_are_checked(cfg, users):
    alice, _ = users
    service = _service(cfg)
    for text in ("", "   ", "x" * (MAX_DAY_NOTE_LENGTH + 1)):
        with pytest.raises(ValueError, match="up to 500 characters"):
            await service.add(alice, DayNoteDraft(day=TODAY, text=text))
    far = date(TODAY.year + DAY_NOTE_MAX_YEARS + 1, 1, 1)
    for day in (far, date(TODAY.year - DAY_NOTE_MAX_YEARS - 1, 1, 1)):
        with pytest.raises(ValueError, match="isn't a day I can read"):
            await service.add(alice, DayNoteDraft(day=day, text="ok"))
    kept = await service.add(alice, DayNoteDraft(day=TODAY, text="  trimmed  "))
    assert kept.text == "trimmed" and kept.author_kind == "user" and kept.bot_id is None


async def test_per_day_cap(cfg, users):
    alice, bob = users
    service = _service(cfg)
    for i in range(MAX_DAY_NOTES_PER_DAY):
        await service.add(alice, DayNoteDraft(day=TODAY, text=f"n{i}"))
    with pytest.raises(ValueError, match="already has 20 notes"):
        await service.add(alice, DayNoteDraft(day=TODAY, text="one more"))
    await service.add(alice, DayNoteDraft(day=date(2026, 10, 22), text="other day"))
    await service.add(bob, DayNoteDraft(day=TODAY, text="other user"))


async def test_writes_publish_day_notes_changed_without_the_text(cfg, users):
    alice, _ = users
    events = Events()
    service = _service(cfg, events)
    note = await service.add(alice, DayNoteDraft(day=TODAY, text="private words"))
    assert await service.delete(alice, note.id) is True
    assert await service.delete(alice, note.id) is False
    assert events.sent == [
        (alice, {"type": "day_notes_changed", "change": "created", "id": note.id, "day": "2026-10-21"}),
        (alice, {"type": "day_notes_changed", "change": "deleted", "id": note.id, "day": "2026-10-21"}),
    ]


async def test_concurrent_adds_never_pass_the_day_cap(cfg, users):
    import asyncio
    alice, _ = users
    service = _service(cfg)

    async def one(i):
        try:
            await service.add(alice, DayNoteDraft(day=TODAY, text=f"n{i}"))
            return True
        except ValueError:
            return False

    results = await asyncio.gather(*(one(i) for i in range(MAX_DAY_NOTES_PER_DAY + 10)))
    assert sum(results) == MAX_DAY_NOTES_PER_DAY
    assert await DayNoteStore(cfg).count_on(alice, TODAY) == MAX_DAY_NOTES_PER_DAY
