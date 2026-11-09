"""One export pass through the Mac seam (the fake keeper): create, leave alone, overwrite only Roost's own
files, conflict copies, never delete, journals, and the ways a pass stops."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from roost.config import load_config
from roost.db.connection import db_session, init_db
from roost.events.hub import EventHub
from roost.gateway.auth import register_user
from roost.journal.service import JournalService
from roost.journal.store import JournalStore
from roost.keeper.macfs.errors import MacFsError
from roost.mac.fake_files import FakeMacFiles
from roost.mac.grants import GrantStore
from roost.mac.models import GrantDraft
from roost.money.expense_store import ExpenseStore
from roost.money.models import ExpenseDraft, ProjectDraft
from roost.money.project_store import ProjectStore
from roost.notes.models import NoteDraft
from roost.notes.store import NoteStore
from roost.tasks.models import TaskDraft, TaskPatch
from roost.tasks.store import TaskStore
from roost.vault_export.exporter import VaultExporter
from roost.vault_export.sources import ExportSources
from roost.vault_export.store import VaultExportStore
from team_helpers import make_bot

HOME = "/Users/me"
BASE = "Vault/Roost/Projects/Garden"


class _Limited(FakeMacFiles):
    """The keeper's per-minute limit after ``room`` creates."""

    def __init__(self, room: int) -> None:
        super().__init__({"Vault/": ""}, HOME)
        self.room = room

    async def create(self, ref, text, *, parents=False):
        if self.room <= 0:
            raise MacFsError("rate_limited")
        self.room -= 1
        return await super().create(ref, text, parents=parents)


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def user_id(cfg):
    return (await register_user(cfg, "alice", "pw-123456")).id


async def _setup(cfg, user_id, files=None, *, access="read_write", journals=False):
    files = files if files is not None else FakeMacFiles({"Vault/": ""}, HOME)
    grants = GrantStore(cfg)
    grant = await grants.create(user_id, GrantDraft(None, f"{HOME}/Vault", "Vault", access, "ask_each", True))
    await files.push_grants(await grants.list_live(user_id))
    project = await ProjectStore(cfg).create(user_id, ProjectDraft(name="Garden"), created_by_bot=None, tainted=False)
    task = await TaskStore(cfg).create(user_id, TaskDraft(title="Dig", project_id=project.id), created_by_bot=None,
                                       tainted=False)
    await NoteStore(cfg).create(user_id, NoteDraft(title="Roses", content="Red.", project_id=project.id),
                                created_by_bot=None, tainted=False)
    await ExpenseStore(cfg).add(user_id, ExpenseDraft(project_id=project.id, amount=Decimal("3"), spent_at="2026-10-20"),
                                created_by_bot=None, tainted=False)
    store = VaultExportStore(cfg)
    await store.save_settings(user_id, grant_id=grant.id, journals=journals)
    await store.set_project(user_id, project.id, True)
    exporter = VaultExporter(store, ExportSources(cfg), files, grants, EventHub(cfg), today=lambda: date(2026, 10, 22))
    return exporter, files, task, grant


def _tree(files: FakeMacFiles) -> dict[str, str]:
    return {k: v for k, v in files._tree.items() if not k.endswith("/")}


async def test_nothing_happens_until_a_grant_and_a_project_are_chosen(cfg, user_id):
    files = FakeMacFiles({"Vault/": ""}, HOME)
    exporter = VaultExporter(VaultExportStore(cfg), ExportSources(cfg), files, GrantStore(cfg), EventHub(cfg),
                             today=lambda: date(2026, 10, 22))
    assert (await exporter.run(user_id)).code == "off"
    assert _tree(files) == {}


async def test_the_first_pass_writes_every_file_and_the_second_nothing(cfg, user_id):
    exporter, files, _task, _grant = await _setup(cfg, user_id)
    first = await exporter.run(user_id)
    assert (first.code, first.written, first.conflicts) == ("ok", 4, 0)
    assert sorted(_tree(files)) == sorted([f"{BASE}/Garden.md", f"{BASE}/Garden · Money.md",
                                           f"{BASE}/Notes/Roses.md", f"{BASE}/Tasks/Dig.md"])
    second = await exporter.run(user_id)
    assert (second.code, second.written) == ("ok", 0)


async def test_the_manifest_is_sealed_and_the_result_kept(cfg, user_id):
    exporter, *_ = await _setup(cfg, user_id)
    await exporter.run(user_id)
    async with db_session(cfg) as db:
        row = await (await db.execute("SELECT manifest, last_result, last_written FROM vault_exports")).fetchone()
    assert row["manifest"].startswith("enc:v2:") and "Garden" not in row["manifest"]
    assert (row["last_result"], row["last_written"]) == ("ok", 4)
    assert len((await VaultExportStore(cfg).settings(user_id)).manifest) == 4


async def test_a_change_in_roost_overwrites_roosts_own_file(cfg, user_id):
    exporter, files, task, _ = await _setup(cfg, user_id)
    await exporter.run(user_id)
    await TaskStore(cfg).update(user_id, task.id, TaskPatch({"description": "Two spades deep"}))
    result = await exporter.run(user_id)
    assert result.written == 1 and "Two spades deep" in _tree(files)[f"{BASE}/Tasks/Dig.md"]


async def test_a_file_edited_in_obsidian_is_kept_and_gets_a_conflict_copy(cfg, user_id):
    exporter, files, task, _ = await _setup(cfg, user_id)
    await exporter.run(user_id)
    files.replace_tree({**files._tree, f"{BASE}/Tasks/Dig.md": "my own words"})
    await TaskStore(cfg).update(user_id, task.id, TaskPatch({"description": "new"}))
    result = await exporter.run(user_id)
    assert result.conflicts == 1 and _tree(files)[f"{BASE}/Tasks/Dig.md"] == "my own words"
    assert "new" in _tree(files)[f"{BASE}/Tasks/Dig.conflict.md"]
    files.replace_tree({**files._tree, f"{BASE}/Tasks/Dig.conflict.md": "edited copy"})
    await exporter.run(user_id)
    assert _tree(files)[f"{BASE}/Tasks/Dig.conflict.md"] == "edited copy"   # an edited copy is left alone too


async def test_a_file_roost_never_wrote_is_never_overwritten(cfg, user_id):
    files = FakeMacFiles({"Vault/": "", f"{BASE}/Garden.md": "the user's own page"}, HOME)
    exporter, files, _task, _ = await _setup(cfg, user_id, files)
    result = await exporter.run(user_id)
    assert result.conflicts == 1 and _tree(files)[f"{BASE}/Garden.md"] == "the user's own page"
    assert f"{BASE}/Garden.conflict.md" in _tree(files)


async def test_nothing_is_ever_deleted(cfg, user_id):
    exporter, files, task, _ = await _setup(cfg, user_id)
    await exporter.run(user_id)
    await TaskStore(cfg).delete(user_id, task.id)
    await exporter.run(user_id)
    assert f"{BASE}/Tasks/Dig.md" in _tree(files)


async def test_journals_go_out_only_when_switched_on(cfg, user_id):
    bot = await make_bot(cfg, user_id, "Ana")
    await JournalService(JournalStore(cfg), EventHub(cfg)).append(user_id, bot.id, bot.name, "Dug the bed")
    exporter, files, *_ = await _setup(cfg, user_id, journals=True)
    await exporter.run(user_id)
    journal = [k for k in _tree(files) if k.startswith("Vault/Roost/Journals/Ana/")]
    assert len(journal) == 1 and "Dug the bed" in _tree(files)[journal[0]]


async def test_a_revoked_or_read_only_grant_stops_the_pass(cfg, user_id):
    exporter, files, _task, grant = await _setup(cfg, user_id, access="read")
    assert (await exporter.run(user_id)).code == "no_grant"
    await GrantStore(cfg).revoke(user_id, grant.id)
    assert (await exporter.run(user_id)).code == "no_grant" and _tree(files) == {}


async def test_the_keepers_limit_makes_a_partial_pass_that_the_next_one_finishes(cfg, user_id):
    files = _Limited(room=2)
    exporter, files, *_ = await _setup(cfg, user_id, files)
    first = await exporter.run(user_id)
    assert (first.code, first.written) == ("partial", 2)
    files.room = 10
    second = await exporter.run(user_id)
    assert (second.code, second.written) == ("ok", 2) and len(_tree(files)) == 4


async def test_an_away_keeper_writes_nothing(cfg, user_id):
    exporter, files, *_ = await _setup(cfg, user_id)
    files.fail = True
    assert (await exporter.run(user_id)).code == "away"
