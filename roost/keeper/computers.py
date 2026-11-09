"""The keeper's ``ComputerManager``: a bot's hardened Linux computer (``roost-computer:dev``).

One container per bot, ``roost-computer-<bot id>``, on its own internal network ``roost-net-<bot id>`` with its
browser profile on the volume ``roost-profile-<bot id>``. Nothing here publishes a port: the screen and the
DevTools pipe are Unix sockets inside the container, reached through ``docker exec -i ... roost-pipe``.

Every docker argv is built by one small pure function (tested in ``tests/test_computer_spec.py``), run with
``asyncio.create_subprocess_exec`` (never a shell) through an injectable runner, each call bounded by
``COMPUTER_DOCKER_CALL_TIMEOUT_S``. A bot id that is not a UUID4 builds no argv at all, so an id can never be
steered into another name. The two relay tokens are minted once per keeper process per bot and live until
the computer is stopped or removed.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
import time
import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from roost.apps.constants import COMPUTER_APT_CAPS, COMPUTER_TMPFS_VAR_TMP
from roost.config import RoostConfig
from roost.constants import (
    COMPUTER_BOOT_TIMEOUT_S,
    COMPUTER_CONTAINER_PREFIX,
    COMPUTER_CPUS,
    COMPUTER_DOCKER_CALL_TIMEOUT_S,
    COMPUTER_VNC_TICKET_TTL_S,
    COMPUTER_IMAGE,
    COMPUTER_MEMORY,
    COMPUTER_NETWORK_PREFIX,
    COMPUTER_PIDS_LIMIT,
    COMPUTER_PROFILE_VOLUME_PREFIX,
    COMPUTER_SHM_SIZE,
    COMPUTER_TMPFS_TMP,
    COMPUTER_UID,
)
from roost.keeper.networks import EgressNetworks, NetworkError
from roost.keeper.workspaces import Runner, _run_docker

logger = logging.getLogger(__name__)

ComputerState = Literal["running", "paused", "stopped", "absent"]

DEFAULT_SECCOMP_PATH = Path(__file__).resolve().parent / "seccomp" / "chromium.json"

_BOT_LABEL = "app.roost.bot"
_HOSTNAME = "computer"
_USER = f"{COMPUTER_UID}:{COMPUTER_UID}"
_TMPFS_SCREEN = f"/run/screen:rw,mode=0700,uid={COMPUTER_UID},gid={COMPUTER_UID},size=1m"
_TMPFS_HOME = f"/home/comp:rw,uid={COMPUTER_UID},gid={COMPUTER_UID},size=64m"
_PROFILE_DST = "/home/comp/profile"
_PIPE_BIN = "/usr/local/bin/roost-pipe"
# Install an app: the root filesystem is writable (apt writes /usr and /var/lib/dpkg) and apt, run as root by the
# keeper's apps route only, holds these three capabilities. The computer's own uid-10002 processes run with
# no-new-privileges, so they hold none (CapEff 0) and still cannot write /usr; /var/tmp is a tmpfs.
_APT_CAPS = tuple(word for cap in COMPUTER_APT_CAPS for word in ("--cap-add", cap))
_PIPE_SOCKETS = ("cdp", "vnc")
_STOP_GRACE_S = "5"
_REMOVE_TIMEOUT_S = 60.0
_PROBE_TIMEOUT_S = 5.0
_PROBE_EVERY_S = 0.5
_NO_SUCH = ("no such", "not found")
# Owner, 2026-11-01: a pause whose docker call timed out still lands, so the keeper thinks "running" while Docker
# has the container paused; Docker then refuses every exec with these words.
_PAUSED_WORDS = "is paused"

START_FAILED = "The computer did not start. Check that Docker is running."
CONTROL_FAILED = "The computer could not be changed. Check that Docker is running."

Sleep = Callable[[float], Awaitable[None]]


class ComputerStartError(RuntimeError):
    """Starting the computer failed; the message is a plain sentence, never docker's own output."""


class ComputerGoneError(ComputerStartError):
    """The boot probe found no container: the keeper's view was stale (it was removed by hand)."""


class ComputerControlError(RuntimeError):
    """Pausing, stopping or removing the computer failed for a reason other than it already being gone."""


def _check_bot_id(bot_id: str) -> str:
    try:
        parsed = uuid.UUID(bot_id)
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValueError("That is not a bot id.") from exc
    if parsed.version != 4 or str(parsed) != bot_id:
        raise ValueError("That is not a bot id.")
    return bot_id


def container_name(bot_id: str) -> str:
    return f"{COMPUTER_CONTAINER_PREFIX}{_check_bot_id(bot_id)}"


def profile_volume(bot_id: str) -> str:
    return f"{COMPUTER_PROFILE_VOLUME_PREFIX}{_check_bot_id(bot_id)}"


def build_run_argv(bot_id: str, seccomp_path: Path) -> list[str]:
    return [
        "docker", "run", "-d", "--name", container_name(bot_id), "--hostname", _HOSTNAME,
        "--label", f"{_BOT_LABEL}={bot_id}", "--network", f"{COMPUTER_NETWORK_PREFIX}{bot_id}",
        "--user", _USER, "--cap-drop", "ALL", *_APT_CAPS,
        "--security-opt", "no-new-privileges", "--security-opt", f"seccomp={seccomp_path}",
        "--tmpfs", COMPUTER_TMPFS_TMP, "--tmpfs", COMPUTER_TMPFS_VAR_TMP, "--tmpfs", _TMPFS_SCREEN,
        "--tmpfs", _TMPFS_HOME,
        "--mount", f"type=volume,src={profile_volume(bot_id)},dst={_PROFILE_DST}",
        "--memory", COMPUTER_MEMORY, "--memory-swap", COMPUTER_MEMORY, "--shm-size", COMPUTER_SHM_SIZE,
        "--cpus", COMPUTER_CPUS, "--pids-limit", COMPUTER_PIDS_LIMIT, COMPUTER_IMAGE,
    ]


def build_pipe_argv(bot_id: str, which: str) -> list[str]:
    """``docker exec -i`` of ``roost-pipe cdp|vnc`` as the screen's user; nothing else can be exec'd."""
    if which not in _PIPE_SOCKETS:
        raise ValueError("unknown socket")
    return ["docker", "exec", "-i", "--user", _USER, container_name(bot_id), _PIPE_BIN, which]


def build_probe_argv(bot_id: str) -> list[str]:
    """The boot probe: ``roost-pipe cdp`` without ``-i``, so its stdin is closed and it exits once connected."""
    return ["docker", "exec", "--user", _USER, container_name(bot_id), _PIPE_BIN, "cdp"]


def build_pause_argv(bot_id: str) -> list[str]:
    return ["docker", "pause", container_name(bot_id)]


def build_unpause_argv(bot_id: str) -> list[str]:
    return ["docker", "unpause", container_name(bot_id)]


def build_stop_argv(bot_id: str) -> list[str]:
    return ["docker", "stop", "-t", _STOP_GRACE_S, container_name(bot_id)]


def build_start_existing_argv(bot_id: str) -> list[str]:
    return ["docker", "start", container_name(bot_id)]


def build_remove_argv(bot_id: str) -> list[str]:
    return ["docker", "rm", "-f", container_name(bot_id)]


def build_volume_remove_argv(bot_id: str) -> list[str]:
    return ["docker", "volume", "rm", profile_volume(bot_id)]


def build_list_argv() -> list[str]:
    return [
        "docker", "ps", "-a", "--filter", f"name={COMPUTER_CONTAINER_PREFIX}", "--filter", f"label={_BOT_LABEL}",
        "--format", "{{.Names}}\t{{.State}}",
    ]


def parse_list_output(stdout: str) -> dict[str, ComputerState]:
    """Map each ``roost-computer-<bot id>`` line to running / paused / stopped. Anything else is ignored."""
    states: dict[str, ComputerState] = {}
    for line in stdout.splitlines():
        name, _, docker_state = line.strip().partition("\t")
        if not name.startswith(COMPUTER_CONTAINER_PREFIX):
            continue
        bot_id = name[len(COMPUTER_CONTAINER_PREFIX):]
        try:
            _check_bot_id(bot_id)
        except ValueError:
            continue
        states[bot_id] = {"running": "running", "paused": "paused"}.get(docker_state, "stopped")
    return states


@dataclass(frozen=True)
class ComputerHandle:
    bot_id: str
    cdp_token: str
    vnc_token: str


def _gone(stderr: bytes) -> bool:
    return any(word in stderr.decode("utf-8", errors="replace").lower() for word in _NO_SUCH)


class ComputerManager:
    """One per keeper process: the state, the tokens and the last-use time of every bot's computer."""

    def __init__(
        self,
        config: RoostConfig,
        networks: EgressNetworks,
        *,
        runner: Runner | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Sleep = asyncio.sleep,
        seccomp_path: Path = DEFAULT_SECCOMP_PATH,
    ) -> None:
        self._config = config
        self._networks = networks
        self._run: Runner = runner if runner is not None else _run_docker
        self._clock = clock
        self._sleep = sleep
        self._seccomp = seccomp_path
        self._state: dict[str, ComputerState] = {}
        self._tokens: dict[str, tuple[str, str]] = {}
        self._tickets: dict[str, tuple[str, float]] = {}    # one-time screen tickets: ticket -> (bot, expiry)
        self._last_used: dict[str, float] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._fresh: frozenset[str] = frozenset()     # created by `docker run` since the last start answered

    def state(self, bot_id: str) -> ComputerState:
        return self._state.get(bot_id, "absent")

    def states(self) -> dict[str, ComputerState]:
        return dict(self._state)

    def handle(self, bot_id: str) -> ComputerHandle | None:
        tokens = self._tokens.get(bot_id)
        if self._state.get(bot_id) != "running" or tokens is None:
            return None
        return ComputerHandle(bot_id, tokens[0], tokens[1])

    def mint_vnc_ticket(self, bot_id: str) -> str:
        """A fresh one-time ticket for one screen socket of a running computer; it expires quickly."""
        now = self._clock()
        self._tickets = {t: v for t, v in self._tickets.items() if v[1] >= now}
        ticket = secrets.token_urlsafe(32)
        self._tickets = {**self._tickets, ticket: (bot_id, now + COMPUTER_VNC_TICKET_TTL_S)}
        return ticket

    def consume_vnc_ticket(self, bot_id: str, ticket: str | None) -> bool:
        """True once for a live ticket made for this bot. A used, expired or other bot's ticket is False."""
        entry = self._tickets.get(ticket or "")
        if entry is None:
            return False
        self._tickets = {t: v for t, v in self._tickets.items() if t != ticket}
        return entry[0] == bot_id and self._clock() <= entry[1]

    def take_fresh(self, bot_id: str) -> bool:
        """Whether the last start created this computer's container (its approved apps must go back); asked once."""
        fresh = bot_id in self._fresh
        self._fresh = self._fresh - {bot_id}
        return fresh

    def touch(self, bot_id: str) -> None:
        self._last_used[bot_id] = self._clock()

    def last_used(self, bot_id: str) -> float | None:
        return self._last_used.get(bot_id)

    async def reconcile(self) -> None:
        """Read what Docker already has at keeper start. Never raises: a down daemon leaves every bot absent."""
        try:
            outcome = await self._run(build_list_argv(), COMPUTER_DOCKER_CALL_TIMEOUT_S)
        except OSError:
            return
        if outcome.timed_out or outcome.returncode != 0:
            return
        self._state.update(parse_list_output(outcome.stdout.decode("utf-8", errors="replace")))

    async def start(self, bot_id: str) -> ComputerHandle:
        """Run, start or unpause the computer, then wait until its DevTools socket answers."""
        _check_bot_id(bot_id)
        async with self._lock(bot_id):
            try:
                await self._boot(bot_id)
            except NetworkError as exc:
                raise ComputerStartError(START_FAILED) from exc
            if bot_id not in self._tokens:
                self._tokens[bot_id] = (secrets.token_urlsafe(32), secrets.token_urlsafe(32))
            self._state[bot_id] = "running"
            self.touch(bot_id)
            handle = self.handle(bot_id)
            assert handle is not None
            return handle

    async def pause(self, bot_id: str) -> None:
        async with self._lock(bot_id):
            if self.state(bot_id) != "running":
                return
            outcome = await self._run(build_pause_argv(bot_id), COMPUTER_DOCKER_CALL_TIMEOUT_S)
            if not outcome.timed_out and outcome.returncode != 0 and _gone(outcome.stderr):
                logger.warning("computer for bot %s was removed behind the keeper's back", bot_id)
                self._state = {b: s for b, s in self._state.items() if b != bot_id}
                self._tokens.pop(bot_id, None)
                self._drop_tickets(bot_id)
                return
            if outcome.timed_out or outcome.returncode != 0:
                logger.error("computer pause failed for %s: %s", bot_id,
                             outcome.stderr.decode("utf-8", "replace")[:300])
                raise ComputerControlError(CONTROL_FAILED)
            self._state[bot_id] = "paused"

    async def stop(self, bot_id: str) -> None:
        async with self._lock(bot_id):
            if self.state(bot_id) not in ("running", "paused"):
                return
            await self._control(build_stop_argv(bot_id), "stop", bot_id, tolerate_gone=True)
            self._state[bot_id] = "stopped"
            self._tokens.pop(bot_id, None)
            self._drop_tickets(bot_id)

    async def remove(self, bot_id: str) -> None:
        """Delete the container, then its profile volume, then its network. "No such" is fine."""
        async with self._lock(bot_id):
            await self._control(build_remove_argv(bot_id), "remove", bot_id, tolerate_gone=True,
                                timeout_s=_REMOVE_TIMEOUT_S)
            await self._control(build_volume_remove_argv(bot_id), "volume remove", bot_id, tolerate_gone=True)
            try:
                await self._networks.remove_bot_network(bot_id)
            except NetworkError as exc:
                raise ComputerControlError(CONTROL_FAILED) from exc
            self._state.pop(bot_id, None)
            self._tokens.pop(bot_id, None)
            self._drop_tickets(bot_id)
            self._last_used.pop(bot_id, None)

    def _drop_tickets(self, bot_id: str) -> None:
        self._tickets = {t: v for t, v in self._tickets.items() if v[0] != bot_id}

    def _lock(self, bot_id: str) -> asyncio.Lock:
        return self._locks.setdefault(bot_id, asyncio.Lock())

    async def _recheck_running(self, bot_id: str) -> None:
        """A computer this keeper thinks is running may have been removed by hand: ask Docker before trusting it."""
        if self.state(bot_id) != "running":
            return
        try:
            outcome = await self._run(build_list_argv(), COMPUTER_DOCKER_CALL_TIMEOUT_S)
        except OSError:
            return
        if outcome.timed_out or outcome.returncode != 0:
            return
        seen = parse_list_output(outcome.stdout.decode("utf-8", errors="replace")).get(bot_id, "absent")
        if seen != "running":
            logger.warning("computer for bot %s was %s, not running; starting it again", bot_id, seen)
        self._state = {**self._state, bot_id: cast(ComputerState, seen)}

    async def _boot(self, bot_id: str) -> None:
        """Bring the computer up and wait for it. A container removed behind the keeper's back is run again once."""
        await self._bring_up(bot_id)
        try:
            await self._wait_for_boot(bot_id)
        except ComputerGoneError:
            await self._recheck_running(bot_id)
            await self._bring_up(bot_id)
            await self._wait_for_boot(bot_id)

    async def _bring_up(self, bot_id: str) -> None:
        state = self.state(bot_id)
        if state == "running":
            return
        await self._networks.ensure_egress()
        await self._networks.ensure_bot_network(bot_id)
        argv = {
            "absent": build_run_argv(bot_id, self._seccomp),
            "stopped": build_start_existing_argv(bot_id),
            "paused": build_unpause_argv(bot_id),
        }[state]
        outcome = await self._run(argv, COMPUTER_DOCKER_CALL_TIMEOUT_S)
        if state != "absent" and not outcome.timed_out and outcome.returncode != 0 and _gone(outcome.stderr):
            logger.warning("computer for bot %s was removed while %s; running it fresh", bot_id, state)
            argv = build_run_argv(bot_id, self._seccomp)
            outcome = await self._run(argv, COMPUTER_DOCKER_CALL_TIMEOUT_S)
        if outcome.timed_out or outcome.returncode != 0:
            logger.error("computer %s failed: %s", argv[1], outcome.stderr.decode("utf-8", "replace").strip()[:300])
            raise ComputerStartError(START_FAILED)
        if argv[1] == "run":
            self._fresh = self._fresh | {bot_id}
        self._state[bot_id] = "running"

    async def _wait_for_boot(self, bot_id: str) -> None:
        deadline = self._clock() + COMPUTER_BOOT_TIMEOUT_S
        while True:
            probe = await self._run(build_probe_argv(bot_id), _PROBE_TIMEOUT_S)
            if not probe.timed_out and probe.returncode == 0:
                return
            if not probe.timed_out and _gone(probe.stderr):
                logger.error("computer for bot %s is gone from Docker", bot_id)
                raise ComputerGoneError(START_FAILED)
            if not probe.timed_out and _PAUSED_WORDS in probe.stderr.decode("utf-8", errors="replace"):
                logger.warning("computer for bot %s was paused behind the keeper's back; unpausing it", bot_id)
                await self._run(build_unpause_argv(bot_id), COMPUTER_DOCKER_CALL_TIMEOUT_S)
            if self._clock() >= deadline:
                logger.error("computer for bot %s never answered its DevTools socket", bot_id)
                raise ComputerStartError(START_FAILED)
            await self._sleep(_PROBE_EVERY_S)

    async def _control(
        self, argv: Sequence[str], what: str, bot_id: str, *, tolerate_gone: bool = False,
        timeout_s: float = COMPUTER_DOCKER_CALL_TIMEOUT_S,
    ) -> None:
        outcome = await self._run(argv, timeout_s)
        if not outcome.timed_out and outcome.returncode == 0:
            return
        if not outcome.timed_out and tolerate_gone and _gone(outcome.stderr):
            return
        logger.error("computer %s failed for %s: %s", what, bot_id, outcome.stderr.decode("utf-8", "replace")[:300])
        raise ComputerControlError(CONTROL_FAILED)
