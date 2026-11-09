"""Apps after a fresh start (docs/plans/2026-10-22-roost-install-app.md §5): a start that created the computer's
container calls the desk's boot hook once, and the reinstaller puts the owner's approved list back with one
ensure, in the background, a failure being a log line and an audit row, never a crash. The gateway's keeper seam
reaches the real keeper app (in-process, signed) with fake docker and apt runners."""

from __future__ import annotations

import asyncio
import json
import sqlite3
import uuid

import httpx
import pytest

from roost.apps.boot import AppReinstaller
from roost.apps.keeper import AppRefused, FakeApps, KeeperApps
from roost.apps.service import AppService
from roost.apps.store import AppStore
from roost.bots.store import BotStore
from roost.config import RoostConfig, load_config
from roost.db.connection import get_db_path, init_db
from roost.desk.client import KeeperDesk
from roost.gateway.auth import register_user
from roost.keeper.app import create_app as create_keeper
from roost.keeper.computer_room import ComputerRoom
from roost.keeper.computers import ComputerManager
from roost.keeper.workspaces import _RunOutcome
from team_helpers import make_bot

_SECRET = "k" * 32
BOT = str(uuid.uuid4())


class DockerFake:
    async def __call__(self, argv, timeout_s) -> _RunOutcome:
        argv = list(argv)
        if argv[1] == "info":
            return _RunOutcome(0, f"{8000 * 1024 * 1024}\n".encode(), b"", False)
        if argv[1] == "stats":
            return _RunOutcome(0, b"2000MiB / 8GiB\n", b"", False)
        return _RunOutcome(0, b"", b"", False)


class FakeNetworks:
    async def ensure_egress(self) -> None: ...
    async def ensure_bot_network(self, bot_id: str) -> None: ...
    async def remove_bot_network(self, bot_id: str) -> None: ...


class AptFake:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.answer = _RunOutcome(0, b"", b"", False)

    async def __call__(self, argv, timeout_s) -> _RunOutcome:
        self.calls.append(list(argv))
        return self.answer


@pytest.fixture
def keeper_config(tmp_path) -> RoostConfig:
    return RoostConfig(server_secret="x" * 32, database_dir=tmp_path / "data", desks_dir=tmp_path / "desks",
                       keeper_secret=_SECRET)


@pytest.fixture
def keeper(keeper_config):
    app = create_keeper(keeper_config)
    docker = DockerFake()
    app.state.computers = ComputerManager(keeper_config, FakeNetworks(), runner=docker)
    app.state.room = ComputerRoom(app.state.computers, runner=docker)
    app.state.apps_runner = AptFake()
    return app


async def test_a_fresh_start_calls_the_boot_hook_once(keeper, keeper_config):
    seen: list[str] = []

    async def on_fresh() -> None:
        seen.append("fresh")

    desk = KeeperDesk(keeper_config, BOT, transport=httpx.ASGITransport(app=keeper), computer="linux",
                      on_fresh=on_fresh)
    await desk.start_browser()
    await desk.start_browser()
    assert seen == ["fresh"]


async def test_the_seam_signs_and_maps_refusals(keeper, keeper_config):
    seam = KeeperApps(keeper_config, transport=httpx.ASGITransport(app=keeper))
    with pytest.raises(AppRefused) as asleep:
        await seam.install(BOT, "gimp")
    assert asleep.value.word == "asleep"
    desk = KeeperDesk(keeper_config, BOT, transport=httpx.ASGITransport(app=keeper), computer="linux")
    await desk.start_browser()
    apt = keeper.state.apps_runner
    apt.answer = _RunOutcome(0, json.dumps({"package": "gimp", "version": "2.10",
                                            "description": "GNU Image Manipulation Program"}).encode(), b"", False)
    info = await seam.describe(BOT, "gimp")
    assert (info.package, info.description) == ("gimp", "GNU Image Manipulation Program")
    apt.answer = _RunOutcome(3, b"", b"not_debian\n", False)
    with pytest.raises(AppRefused) as refused:
        await seam.install(BOT, "gimp")
    assert refused.value.word == "not_debian"
    apt.answer = _RunOutcome(0, b"", b"", False)
    await seam.ensure(BOT, ["gimp", "vlc"])
    assert apt.calls[-1][-3:] == ["ensure", "gimp", "vlc"]


@pytest.fixture
async def cfg():
    config = load_config()
    await init_db(config)
    return config


class NoDesks:
    def for_bot(self, bot_id, computer="mac_brave"):
        raise AssertionError("a reinstall never wakes a computer: it runs right after its start")


async def _service(cfg, fake: FakeApps) -> tuple[AppService, str, str]:
    user = await register_user(cfg, "alice", "pw-123456")
    bot = await make_bot(cfg, user.id, "Scout")
    store = AppStore(cfg)
    await store.add(user.id, bot.id, "gimp", tainted=False)
    await store.add(user.id, bot.id, "vlc", tainted=False)
    return AppService(cfg, store, fake, BotStore(cfg), NoDesks()), user.id, bot.id


async def test_the_reinstaller_puts_the_list_back_in_one_ensure(cfg):
    fake = FakeApps()
    service, _, bot_id = await _service(cfg, fake)
    reinstaller = AppReinstaller(service)
    await reinstaller.on_fresh(bot_id)          # returns at once; the work runs in the background
    await reinstaller.drain()
    assert [(verb, sorted(pkgs)) for verb, _, pkgs in fake.calls] == [("ensure", ["gimp", "vlc"])]
    await reinstaller.on_fresh(str(uuid.uuid4()))     # a bot with no apps: nothing to do
    await reinstaller.drain()
    assert len(fake.calls) == 1


async def test_a_failed_reinstall_is_quiet(cfg):
    fake = FakeApps()
    fake.fail = True
    service, user_id, bot_id = await _service(cfg, fake)
    reinstaller = AppReinstaller(service)
    await reinstaller.on_fresh(bot_id)
    await reinstaller.drain()
    con = sqlite3.connect(get_db_path(cfg))
    try:
        rows = con.execute("SELECT action, decision, reason, detail FROM audit WHERE user_id = ?",
                           (user_id,)).fetchall()
    finally:
        con.close()
    assert ("reinstall_app", "never", "reinstall_failed", None) in rows


async def test_the_boot_hook_never_blocks_the_start(cfg):
    gate = asyncio.Event()

    class SlowApps(FakeApps):
        async def ensure(self, bot_id, packages):
            await gate.wait()

    service, _, bot_id = await _service(cfg, SlowApps())
    reinstaller = AppReinstaller(service)
    await asyncio.wait_for(reinstaller.on_fresh(bot_id), timeout=1)
    gate.set()
    await reinstaller.drain()
