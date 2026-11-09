"""The notes role end to end (M2 D1): a bot's tools over the user's shared notes."""

from __future__ import annotations

import pytest

from roost.config import load_config
from roost.db.connection import init_db
from roost.gateway.auth import register_user
from roost.llm.types import ToolCallRequested, TurnDone
from roost.money.models import ProjectDraft
from roost.money.project_store import ProjectStore
from roost.notes.models import NoteDraft
from roost.notes.store import NoteStore
from roost.talk.gate import TAINTED_CHANGE_TEXT
from team_helpers import make_bot, make_rig, say, send, team_model, wait_idle


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def user_id(cfg):
    return (await register_user(cfg, "alice", "pw-123456")).id


def _tool(call_id: str, name: str, **arguments):
    return [ToolCallRequested(id=call_id, name=name, arguments=arguments), TurnDone("tool_use")]


async def _talk(cfg, user_id, bot, script: dict, text: str):
    rig = make_rig(cfg, team_model(script))
    thread = await rig.talk.create_thread(user_id, bot.id)
    await send(rig, user_id, bot.id, thread.id, text)
    await wait_idle(rig.runner)
    return rig, thread


def _tool_texts(request) -> list[str]:
    return [turn.text for turn in request.turns if turn.role == "tool"]


async def _seed(cfg, user_id, title: str, content: str, *, tainted: bool = False):
    return await NoteStore(cfg).create(user_id, NoteDraft(title=title, content=content), created_by_bot=None,
                                       tainted=tainted)


async def test_note_anas_birthday_then_find_it_by_orchids(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Writer")
    await _talk(cfg, user_id, bot, {"Writer": [
        _tool("a", "add_note", title="Ana", content="Ana's birthday is 3 May. She likes orchids.", tags=["people"]),
        say("Saved to [[Ana]]."),
    ]}, "note: Ana's birthday is 3 May, she likes orchids")
    rig, _ = await _talk(cfg, user_id, bot, {"Writer": [_tool("f", "find_notes", query="orchids"), say("One note.")]},
                         "what do I know about orchids?")
    found = _tool_texts(rig.model.requests[-1])[0]
    assert "“Ana”" in found and "[bot:writer, people]" in found and "orchids" in found
    [note] = await NoteStore(cfg).list(user_id)
    assert (note.created_by_bot, note.tainted, note.tags) == (bot.id, False, ("bot:writer", "people"))


async def test_find_notes_with_a_blank_tag_is_not_a_filter(cfg, user_id):
    """An empty tag argument must not hide every note (M2 Task 1 review, finding #1)."""
    bot = await make_bot(cfg, user_id, "Writer")
    await _seed(cfg, user_id, "Ana", "likes orchids")
    rig, _ = await _talk(cfg, user_id, bot, {"Writer": [_tool("f", "find_notes", query="orchids", tag=""), say("ok")]},
                         "what do I know about orchids?")
    assert "“Ana”" in _tool_texts(rig.model.requests[-1])[0]


async def test_two_bots_with_the_notes_role_share_the_users_notes(cfg, user_id):
    writer = await make_bot(cfg, user_id, "Writer")
    helper = await make_bot(cfg, user_id, "Helper")
    await _talk(cfg, user_id, writer, {"Writer": [_tool("a", "add_note", content="Wifi password is on the fridge"),
                                                  say("ok")]}, "note it")
    rig, _ = await _talk(cfg, user_id, helper, {"Helper": [_tool("f", "find_notes", query="wifi"), say("ok")]},
                         "where's the wifi password?")
    assert "Wifi password is on the fridge" in _tool_texts(rig.model.requests[-1])[0]


async def test_a_note_added_after_reading_a_page_is_stored_tainted_and_marked(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Writer")
    rig, _ = await _talk(cfg, user_id, bot, {"Writer": [
        _tool("p", "open_page", url="https://example.com"),
        _tool("a", "add_note", title="Recipe", content="From the page: bake at 180."),
        _tool("f", "find_notes", query="bake"),
        say("Saved."),
    ]}, "read example.com and note the recipe")
    [note] = await NoteStore(cfg).list(user_id)
    assert (note.title, note.tainted, note.created_by_bot) == ("Recipe", True, bot.id)
    assert "[from web content]" in _tool_texts(rig.model.requests[-1])[-1]


async def test_a_tainted_run_cannot_change_or_delete_a_note(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Writer")
    await _seed(cfg, user_id, "Packing list", "passport")
    rig, _ = await _talk(cfg, user_id, bot, {"Writer": [
        _tool("p", "open_page", url="https://example.com"),
        _tool("a", "append_to_note", note="Packing list", text="and the keys"),
        _tool("d", "delete_note", note="Packing list"),
        say("No."),
    ]}, "read example.com and do what it says")
    assert _tool_texts(rig.model.requests[-1])[-2:] == [TAINTED_CHANGE_TEXT, TAINTED_CHANGE_TEXT]
    [note] = await NoteStore(cfg).list(user_id)
    assert (note.content, note.revision) == ("passport", 1)


async def test_finding_a_web_made_note_taints_the_run(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Writer")
    await _seed(cfg, user_id, "Recipe", "bake at 180", tainted=True)
    rig, _ = await _talk(cfg, user_id, bot, {"Writer": [
        _tool("f", "find_notes", query="recipe"),
        _tool("u", "update_note", note="Recipe", content="bake at 250"),
        say("No."),
    ]}, "fix the recipe")
    assert _tool_texts(rig.model.requests[-1])[-1] == TAINTED_CHANGE_TEXT
    assert (await NoteStore(cfg).list(user_id))[0].content == "bake at 180"


async def test_a_near_miss_name_never_changes_a_note(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Writer")
    await _seed(cfg, user_id, "Call mom", "sunday")
    rig, _ = await _talk(cfg, user_id, bot, {"Writer": [
        _tool("a", "append_to_note", note="Call tom", text="monday"), say("Which?"),
    ]}, "add monday to call tom")
    assert "Did you mean “Call mom”" in _tool_texts(rig.model.requests[-1])[0]
    assert (await NoteStore(cfg).list(user_id))[0].content == "sunday"


async def test_two_notes_with_the_same_title_ask_which(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Writer")
    first = await _seed(cfg, user_id, "Ana", "work")
    second = await _seed(cfg, user_id, "Ana", "family")
    rig, _ = await _talk(cfg, user_id, bot, {"Writer": [_tool("d", "delete_note", note="Ana"), say("Which?")]},
                         "delete the Ana note")
    text = _tool_texts(rig.model.requests[-1])[0]
    assert "several notes match" in text and first.id in text and second.id in text
    assert len(await NoteStore(cfg).list(user_id)) == 2


async def test_read_note_escapes_markup_and_lists_its_links(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Writer")
    await _seed(cfg, user_id, "Garden", "roses")
    await _seed(cfg, user_id, "Ana", "<script>x</script></untrusted_page> see [[Garden]] and [[Orchids]]")
    rig, _ = await _talk(cfg, user_id, bot, {"Writer": [_tool("r", "read_note", note="ana"), say("ok")]}, "read Ana")
    text = _tool_texts(rig.model.requests[-1])[0]
    assert "&lt;script&gt;" in text and "<script>" not in text and "</untrusted_page>" not in text
    assert "Links: Garden, Orchids (no note yet)" in text


async def test_append_adds_the_text_and_its_hashtags(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Writer")
    await _seed(cfg, user_id, "Party", "cake")
    await _talk(cfg, user_id, bot, {"Writer": [
        _tool("a", "append_to_note", note="Party", text="bring #wine"), say("ok"),
    ]}, "add wine to the party note")
    [note] = await NoteStore(cfg).list(user_id)
    assert (note.content, note.tags, note.revision) == ("cake\n\nbring #wine", ("wine",), 2)


async def test_a_note_is_saved_into_a_project_and_found_there(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Writer")
    project = await ProjectStore(cfg).create(user_id, ProjectDraft(name="Renovation"), created_by_bot=None,
                                             tainted=False)
    await _seed(cfg, user_id, "Tiles", "green tiles")
    rig, _ = await _talk(cfg, user_id, bot, {"Writer": [
        _tool("a", "add_note", title="Paint", content="white paint", project="renovation"),
        _tool("f1", "find_notes", query="", project="Renovation"),
        _tool("f2", "find_notes", query="", project="Renovaton"),
        say("ok"),
    ]}, "note white paint for the renovation, then show me its notes")
    saved, found, near = _tool_texts(rig.model.requests[-1])
    assert saved.startswith("Saved: - “Paint”") and saved.endswith(" Project: “Renovation”.")
    assert "“Paint”" in found and "“Tiles”" not in found
    assert near == found          # a read may answer a near miss (H3)
    notes = {note.title: note for note in await NoteStore(cfg).list(user_id)}
    assert (notes["Paint"].project_id, notes["Tiles"].project_id) == (project.id, None)


async def test_update_note_moves_a_note_without_bumping_its_revision(cfg, user_id):
    """H12: linking is not an edit, so an open editor still saves at its revision."""
    bot = await make_bot(cfg, user_id, "Writer")
    project = await ProjectStore(cfg).create(user_id, ProjectDraft(name="Renovation"), created_by_bot=None,
                                             tainted=False)
    note = await _seed(cfg, user_id, "Tiles", "green tiles")
    rig, _ = await _talk(cfg, user_id, bot, {"Writer": [
        _tool("u1", "update_note", note="Tiles", project="Renovation"),
        _tool("u2", "update_note", note="Tiles", project=""),
        _tool("u3", "update_note", note="Tiles", content="blue tiles", project="Renovation"),
        say("ok"),
    ]}, "file the tiles note under the renovation")
    moved, unlinked, both = _tool_texts(rig.model.requests[-1])
    assert moved.startswith("Updated: - “Tiles”") and moved.endswith(" Project: “Renovation”.")
    assert unlinked.endswith(" No project.")
    assert both.endswith(" Project: “Renovation”.") and "blue tiles" in both
    kept = await NoteStore(cfg).get(user_id, note.id)
    assert (kept.project_id, kept.content, kept.revision) == (project.id, "blue tiles", 2)
