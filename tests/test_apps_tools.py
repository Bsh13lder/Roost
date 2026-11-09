"""The app tools (docs/plans/2026-10-22-roost-install-app.md §1): the card names the bot, the package, the reason and
Debian's description; Yes runs exactly the stored call, records it and reaches the computer only through the keeper
seam; refusals are plain sentences with no card. A fake keeper seam: nothing here starts Docker or apt."""

from __future__ import annotations

from dataclasses import replace

import pytest

from roost.approvals.executor import ApprovedCalls
from roost.approvals.models import ApprovalCard, PendingCall
from roost.approvals.rows import with_rows
from roost.apps.keeper import AppRefused, FakeApps
from roost.apps.service import AppService
from roost.apps.store import AppStore
from roost.apps.tools import AppTools
from roost.bots.models import BotPatch
from roost.bots.store import BotStore
from roost.config import load_config
from roost.db.connection import init_db
from roost.events.hub import EventHub
from roost.gateway.auth import register_user
from roost.talk.domain_tools import DomainTools, RecordContext
from roost.talk.gate import Gate
from roost.talk.store import TalkStore
from team_helpers import make_bot


class Desks:
    """Stands in for the DeskFactory: waking the computer just counts."""

    def __init__(self) -> None:
        self.woken: list[str] = []

    def for_bot(self, bot_id: str, computer: str = "mac_brave"):
        outer = self

        class _Desk:
            async def start_browser(self):
                outer.woken.append(bot_id)

        return _Desk()


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


@pytest.fixture
async def world(cfg):
    user = await register_user(cfg, "alice", "pw-123456")
    bot = await make_bot(cfg, user.id, "Scout")
    await BotStore(cfg).update(user.id, bot.id, BotPatch(computer="linux"))
    keeper, desks, store = FakeApps(), Desks(), AppStore(cfg)
    service = AppService(cfg, store, keeper, BotStore(cfg), desks)
    tools = AppTools(service)
    ctx = RecordContext(user_id=user.id, bot_id=bot.id, tainted=False, thread_id=None)
    return user.id, bot.id, tools, keeper, desks, store, ctx


INSTALL = {"package": "gimp", "why": "Edit the team logo"}


async def test_the_card_names_the_bot_the_package_and_debians_line(world):
    _, _, tools, keeper, _, _, ctx = world
    pending = await tools.prepare("install_app", INSTALL, ctx)
    assert isinstance(pending, PendingCall)
    assert pending.title == "Scout wants to install gimp"
    assert pending.detail == keeper.description_of("gimp")
    assert (pending.floor, pending.topic, pending.tainted_basis) == ("install_app", "programs", False)
    shown = with_rows(pending)
    assert dict(shown.arguments) == INSTALL
    assert [(r.label, r.value) for r in shown.rows] == [("Package", "gimp"), ("Why", "Edit the team logo")]
    assert keeper.installed == {}        # describing installs nothing


@pytest.mark.parametrize("arguments,word", [
    ({"package": "sudo", "why": "x"}, "can't be installed"),
    ({"package": "Gimp;rm", "why": "x"}, "not a package name"),
    ({"package": "gimp"}, "why you need it"),
    ({"package": "nosuchpkg", "why": "x"}, "Debian has no package"),
    ({"package": "thirdparty-tool", "why": "x"}, "isn't in Debian's main archive"),
])
async def test_refusals_are_sentences_and_no_card(world, arguments, word):
    _, _, tools, keeper, _, _, ctx = world
    keeper.refusals = {"nosuchpkg": "not_found", "thirdparty-tool": "not_debian"}
    refused = await tools.prepare("install_app", arguments, ctx)
    assert isinstance(refused, str) and word in refused


async def test_a_mac_brave_bot_gets_no_card(world, cfg):
    user_id, bot_id, tools, _, _, _, ctx = world
    await BotStore(cfg).update(user_id, bot_id, BotPatch(computer="mac_brave"))
    assert "Linux computer" in await tools.prepare("install_app", INSTALL, ctx)


async def test_yes_installs_exactly_the_stored_call_and_records_it(world, cfg):
    user_id, bot_id, tools, keeper, desks, store, ctx = world
    pending = with_rows(await tools.prepare("install_app", INSTALL, ctx))
    card = ApprovalCard(id="c1", user_id=user_id, bot_id=bot_id, thread_id="t1", work_item_id=None, kind="ask",
                        state="open", steps=(pending,), request="", tainted=True, session_offer=False,
                        answer_item_id=None, created_at="", closed_at=None)
    approved = ApprovedCalls(DomainTools((tools,)), Gate(cfg), TalkStore(cfg), EventHub(cfg))
    outcome = await approved.run(user_id, card, pending)
    assert outcome.ok and "Installed gimp" in outcome.text
    assert keeper.installed == {bot_id: {"gimp"}} and desks.woken
    [app] = await store.list_for_bot(user_id, bot_id)
    assert (app.package, app.tainted) == ("gimp", True)
    assert "already on this computer" in await tools.prepare("install_app", INSTALL, ctx)


async def test_a_failed_install_records_nothing(world):
    user_id, bot_id, tools, keeper, _, store, ctx = world
    keeper.fail = True
    outcome = await tools.execute("install_app", INSTALL, ctx)
    assert outcome.failed and await store.list_for_bot(user_id, bot_id) == ()


async def test_remove_only_what_install_app_put_there(world):
    user_id, bot_id, tools, keeper, _, store, ctx = world
    assert "wasn't installed with install_app" in await tools.prepare("remove_app", {"package": "xterm2"}, ctx)
    await tools.execute("install_app", INSTALL, ctx)
    pending = await tools.prepare("remove_app", {"package": "gimp"}, ctx)
    assert pending.title == "Scout wants to remove gimp" and pending.floor == "install_app"
    outcome = await tools.execute("remove_app", {"package": "gimp"}, ctx)
    assert not outcome.failed and keeper.installed[bot_id] == set()
    assert await store.list_for_bot(user_id, bot_id) == ()


async def test_run_never_installs_and_list_apps_reads(world):
    _, bot_id, tools, keeper, _, _, ctx = world
    assert "Yes" in (await tools.run("install_app", INSTALL, ctx)).text
    assert keeper.installed == {}
    assert "No apps" in (await tools.run("list_apps", {}, ctx)).text
    await tools.execute("install_app", INSTALL, ctx)
    assert "gimp" in (await tools.run("list_apps", {}, ctx)).text


async def test_another_users_bot_is_refused(world, cfg):
    _, bot_id, tools, keeper, _, _, ctx = world
    bob = (await register_user(cfg, "bob", "pw-123456")).id
    stranger = replace(ctx, user_id=bob)
    assert isinstance(await tools.prepare("install_app", INSTALL, stranger), str)
    outcome = await tools.execute("install_app", INSTALL, stranger)
    assert outcome.failed and keeper.installed == {}


def test_the_fake_keeper_refuses_like_roost_apt():
    with pytest.raises(AppRefused):
        FakeApps(refusals={"x1": "not_found"}).check("x1")
