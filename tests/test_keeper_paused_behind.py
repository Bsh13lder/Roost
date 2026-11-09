"""Owner, 2026-11-01: Gigs' computer stayed frozen. A pause whose docker call timed out left the keeper sure the
computer was running while Docker had paused it, so waking it only probed a frozen container. A probe that Docker
refuses as paused now unpauses it."""

from __future__ import annotations

import pytest

from roost.config import load_config
from roost.keeper.computers import ComputerManager
from roost.keeper.workspaces import _RunOutcome

BOT = "fa6711c5-661f-4cb2-bfe3-30c5235fc750"
_PAUSED = b"Error response from daemon: Container roost-computer-x is paused, unpause the container before exec"


class Networks:
    async def ensure_egress(self) -> None: ...
    async def ensure_bot_network(self, bot_id: str) -> None: ...
    async def remove_bot_network(self, bot_id: str) -> None: ...


class Docker:
    def __init__(self) -> None:
        self.paused = True
        self.calls: list[str] = []

    async def __call__(self, argv, timeout_s) -> _RunOutcome:
        self.calls.append(argv[1])
        if argv[1] == "unpause":
            self.paused = False
        if argv[1] == "exec" and self.paused:
            return _RunOutcome(1, b"", _PAUSED, False)
        return _RunOutcome(0, b"", b"", False)


async def _no_sleep(_s: float) -> None: ...


@pytest.mark.asyncio
async def test_a_computer_paused_behind_the_keepers_back_is_unpaused_on_wake():
    docker = Docker()
    manager = ComputerManager(load_config(), Networks(), runner=docker, sleep=_no_sleep)
    manager._state = {BOT: "running"}            # what the keeper believed after a timed-out pause
    handle = await manager.start(BOT)
    assert handle is not None and docker.paused is False
    assert docker.calls.count("unpause") == 1
