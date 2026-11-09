"""Per-bot workspace container — a locked-down Debian sandbox
(``docker/workspace/Dockerfile``, built as ``roost-workspace:dev`` via
``make workspace-image``) where a bot's own shell commands run.
``exec`` here is reached only through ``POST /desks/{bot_id}/workspace/exec``,
itself only reachable from the gateway's signed keeper client: the user's
own "run a command" action, and a bot's program tools (``run_program``,
``write_file``, ``read_file``, ``list_files`` in ``roost/programs/``), which
the gateway's gate judges first (docs/plans/2026-10-22-roost-programs.md).

Container name ``roost-desk-<bot_id>``; image ``roost-workspace:dev``.
Every argv below is built by its own small, independently unit-tested
function (see ``tests/test_workspace_spec.py``) — ``docker`` is always
invoked as an argv list via ``asyncio.create_subprocess_exec``, never
through a shell, and nothing here interpolates untrusted input into a
shell string.

Orphan reaping: ``docker exec`` has no primitive for "kill everything
this command started, including anything it detached from" — a command
that backgrounds a process with ``setsid -f`` outlives the exec call
itself. So after *every* exec (clean return, timeout or error alike),
``_reap`` sends ``kill -9 -1`` inside the container (reaching every
process the bot's own commands could have started) and then inspects
``docker top``. Empirically, on this Docker Desktop build ``docker
top``'s PID column reports the *host* pid, not the container-namespace
pid a literal "is it PID 1" check would need — so the portable signal
used here is row count, not a PID value: the container's own foreground
process (``sleep infinity``) is always exactly one row, and a second row
means something survived the kill, at which point the container is
destroyed and recreated from scratch rather than trusted to be clean.
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from typing import Awaitable, Callable, Literal, Protocol, Sequence

from roost.config import RoostConfig
from roost.constants import COMPUTER_NETWORK_PREFIX, EGRESS_CONTAINER, EGRESS_PORT
from roost.keeper.paths import workspace_dir

IMAGE = "roost-workspace:dev"

_CONTAINER_PREFIX = "roost-desk-"
_CONTAINER_UID = 10001
_CONTAINER_GID = 10001
_MEMORY_LIMIT = "1g"
_CPU_LIMIT = "1"
_PIDS_LIMIT = "256"
_TMPFS_TMP = "/tmp:rw,size=64m"
# Ruling 8 (controller, 2026-10-13): `--read-only` alone leaves
# /home/desk unwritable (useradd -m made it the shell's $HOME), so a
# second tmpfs mount gives the bot's shell a writable home without
# opening up the rest of the rootfs.
_TMPFS_HOME = f"/home/desk:rw,size=64m,uid={_CONTAINER_UID},gid={_CONTAINER_GID}"
_WORKDIR = "/workspace"
_EXEC_PATH_ENV = "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
_LABEL_KEY = "app.roost.bot"
# Internet in the workspace (A4, 2026-10-23): on the bot's own internal network, out only through roost-egress.
_INTERNET_LABEL = "app.roost.internet"
_INTERNET_ON = "1"
_PROXY_URL = f"http://{EGRESS_CONTAINER}:{EGRESS_PORT}"
_PROXY_ENV_NAMES = ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy")

_OUTPUT_KEEP_CHARS = 8000
_TRUNCATION_MARKER = "\n…[cut]…\n"

# docker exec/top/kill/stop are all short, local daemon calls -- never
# bounded by the caller's own exec timeout_s, which governs only the
# bot's command itself.
_CONTROL_CALL_TIMEOUT_S = 10.0

# `docker rm -f` is NOT one of the fast ones above: real-desk smoke
# (Task 13) saw the retire route occasionally run past the original 10s
# bound here. Direct, isolated timing of `docker rm -f` (including
# through this exact async subprocess path) never showed it taking more
# than a few hundred ms on this machine -- the actual root cause turned
# out to be roost/desk/client.py's KeeperDesk.retire() abandoning an
# open CDP WebSocket instead of closing it (fixed there). This wider
# margin is kept anyway as cheap defense in depth: this dev machine also
# runs other Docker-backed projects' containers (confirmed with `docker
# ps -a`), and `--mount type=bind` teardown is a plausible, if
# unconfirmed, place for real contention with a shared Docker Desktop
# VM to show up. Used only for the actual removal call, not
# status/stop/kill/top.
_CONTAINER_REMOVE_TIMEOUT_S = 60.0


def container_name(bot_id: str) -> str:
    return f"{_CONTAINER_PREFIX}{bot_id}"


@dataclass(frozen=True)
class ExecResult:
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool
    truncated: bool


class WorkspaceStartError(RuntimeError):
    """Raised when the workspace container fails to start."""


class WorkspaceStopError(RuntimeError):
    """Raised when ``docker stop`` fails for a reason other than the
    container already being gone (daemon unreachable, permission error,
    ...). The already-gone case is treated as a successful stop, not an
    error — see ``_container_already_gone``."""


class WorkspaceRemoveError(RuntimeError):
    """Raised when ``docker rm -f`` fails for a reason other than the
    container already being gone. The already-gone case is treated as a
    successful remove, not an error — see ``_container_already_gone``."""


@dataclass(frozen=True)
class _RunOutcome:
    returncode: int
    stdout: bytes
    stderr: bytes
    timed_out: bool


# Injectable in place of the real `docker` subprocess so unit tests can
# assert on the exact argv built for each operation without a daemon --
# mirrors `roost.keeper.browsers.Spawner`.
Runner = Callable[[Sequence[str], float], Awaitable[_RunOutcome]]


async def _run_docker(argv: Sequence[str], timeout_s: float) -> _RunOutcome:
    proc = await asyncio.create_subprocess_exec(
        *argv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
        return _RunOutcome(returncode=proc.returncode, stdout=stdout, stderr=stderr, timed_out=False)
    except asyncio.TimeoutError:
        with contextlib.suppress(ProcessLookupError):
            proc.kill()
        with contextlib.suppress(Exception):
            await proc.wait()
        return _RunOutcome(returncode=-1, stdout=b"", stderr=b"", timed_out=True)


def _network_argv(bot_id: str, internet: bool) -> list[str]:
    """No network at all, or (A4) the bot's own internal network with the proxy as the only way out."""
    if not internet:
        return ["--network", "none"]
    proxy_env = [part for name in _PROXY_ENV_NAMES for part in ("--env", f"{name}={_PROXY_URL}")]
    return ["--network", f"{COMPUTER_NETWORK_PREFIX}{bot_id}", *proxy_env,
            "--label", f"{_INTERNET_LABEL}={_INTERNET_ON}"]


def _build_run_argv(config: RoostConfig, bot_id: str, internet: bool = False) -> list[str]:
    bind_src = workspace_dir(config.desks_dir, bot_id)
    return [
        "docker", "run", "-d",
        "--name", container_name(bot_id),
        "--user", f"{_CONTAINER_UID}:{_CONTAINER_GID}",
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
        "--memory", _MEMORY_LIMIT,
        "--cpus", _CPU_LIMIT,
        "--pids-limit", _PIDS_LIMIT,
        *_network_argv(bot_id, internet),
        "--read-only",
        "--tmpfs", _TMPFS_TMP,
        "--tmpfs", _TMPFS_HOME,
        "--mount", f"type=bind,src={bind_src},dst={_WORKDIR}",
        "--label", f"{_LABEL_KEY}={bot_id}",
        IMAGE,
    ]


def _build_start_existing_argv(bot_id: str) -> list[str]:
    return ["docker", "start", container_name(bot_id)]


def _build_exec_argv(bot_id: str, argv: Sequence[str]) -> list[str]:
    return [
        "docker", "exec",
        "--user", f"{_CONTAINER_UID}:{_CONTAINER_GID}",
        "--workdir", _WORKDIR,
        "--env", _EXEC_PATH_ENV,
        container_name(bot_id),
        *argv,
    ]


def _build_kill_all_argv(bot_id: str) -> list[str]:
    return ["docker", "exec", "--user", f"{_CONTAINER_UID}:{_CONTAINER_GID}", container_name(bot_id), "kill", "-9", "-1"]


def _build_top_argv(bot_id: str) -> list[str]:
    return ["docker", "top", container_name(bot_id), "-eo", "pid,args"]


def _build_stop_argv(bot_id: str) -> list[str]:
    return ["docker", "stop", container_name(bot_id)]


def _build_remove_argv(bot_id: str) -> list[str]:
    return ["docker", "rm", "-f", container_name(bot_id)]


# `docker ps --filter name=<prefix>` matches the filter text anywhere in
# the name by default -- no anchoring needed, since `_CONTAINER_PREFIX`
# is specific enough on its own.
def _build_list_argv() -> list[str]:
    return ["docker", "ps", "-a", "--filter", f"name={_CONTAINER_PREFIX}", "--format",
            "{{.Names}}\t{{.State}}\t{{.Label \"" + _INTERNET_LABEL + "\"}}"]


def _parse_list_output(stdout: str) -> dict[str, Literal["running", "stopped"]]:
    """Map each ``roost-desk-<bot_id>`` container `docker ps` reports to
    "running"/"stopped" (any other Docker state -- exited, created,
    dead, ... -- is simply "not running", which is all this tri-state
    status distinguishes from "absent" anyway). A line that isn't one of
    this app's own containers (shouldn't happen given the filter, but a
    `docker ps` output format is still external input) is ignored rather
    than trusted."""
    state: dict[str, Literal["running", "stopped"]] = {}
    for line in stdout.splitlines():
        name, _, rest = line.strip().partition("\t")
        if not name.startswith(_CONTAINER_PREFIX):
            continue
        bot_id = name[len(_CONTAINER_PREFIX) :]
        state[bot_id] = "running" if rest.split("\t")[0] == "running" else "stopped"
    return state


def _parse_internet(stdout: str) -> frozenset[str]:
    """The bots whose workspace container carries the internet label (A4), from the same listing."""
    found = set()
    for line in stdout.splitlines():
        parts = line.strip().split("\t")
        if len(parts) == 3 and parts[0].startswith(_CONTAINER_PREFIX) and parts[2] == _INTERNET_ON:
            found.add(parts[0][len(_CONTAINER_PREFIX):])
    return frozenset(found)


class Networks(Protocol):
    """``roost.keeper.networks.EgressNetworks`` (not imported here: it imports this module's runner)."""

    async def ensure_egress(self) -> None: ...
    async def ensure_bot_network(self, bot_id: str) -> None: ...


def _truncate(text: str) -> tuple[str, bool]:
    """Keep the first and last ``_OUTPUT_KEEP_CHARS`` of ``text`` with a
    cut marker in between; leave it alone if it already fits in that
    budget twice over."""
    if len(text) <= _OUTPUT_KEEP_CHARS * 2:
        return text, False
    head = text[:_OUTPUT_KEEP_CHARS]
    tail = text[-_OUTPUT_KEEP_CHARS:]
    return f"{head}{_TRUNCATION_MARKER}{tail}", True


_NO_SUCH_CONTAINER_MARKER = "No such container"


def _container_already_gone(stderr: bytes) -> bool:
    """True when a failing ``docker stop``/``docker rm`` means only that
    the container isn't there any more (already stopped-and-removed, or
    never created) -- the benign case ``stop()``/``remove()`` still treat
    as success. Fix round 1, finding 1: any *other* failure (daemon
    unreachable, permission error, ...) must not be swallowed the same
    way -- it is a real error the route needs to surface as a 500,
    not a false ``{"workspace": "stopped"}`` / ``{"retired": true}``."""
    return _NO_SUCH_CONTAINER_MARKER in stderr.decode("utf-8", errors="replace")


def _has_leftover_process(top_stdout: str) -> bool:
    """True if ``docker top``'s output (``-eo pid,args``) lists more than
    the container's own single foreground process (see module docstring
    for why this counts rows instead of checking a PID value)."""
    lines = [line for line in top_stdout.splitlines() if line.strip()]
    data_rows = lines[1:] if lines else []  # first line is the "PID COMMAND" header
    return len(data_rows) > 1


class WorkspaceManager:
    """One per keeper process. Tracks at most one workspace container per
    bot id, matching ``roost.keeper.browsers.BraveLauncher``'s shape."""

    def __init__(self, config: RoostConfig, *, runner: Runner | None = None,
                 networks: Networks | None = None) -> None:
        self._config = config
        self._run: Runner = runner if runner is not None else _run_docker
        self._state: dict[str, Literal["running", "stopped"]] = {}
        self._networks = networks
        self._internet: frozenset[str] = frozenset()     # A4: the bots whose workspace has internet

    def status(self, bot_id: str) -> Literal["running", "stopped", "absent"]:
        return self._state.get(bot_id, "absent")

    def internet(self, bot_id: str) -> bool:
        return bot_id in self._internet

    async def set_internet(self, bot_id: str, on: bool) -> None:
        """A4: Internet in the workspace on or off. A container made the other way is removed (its files are in
        the bind mount and stay) and, if it was running, started again the new way. ``WorkspaceRemoveError`` /
        ``WorkspaceStartError`` when docker fails; the switch is remembered either way."""
        if self.internet(bot_id) == on:
            return
        self._internet = self._internet | {bot_id} if on else self._internet - {bot_id}
        previous = self._state.get(bot_id)
        if previous is None:
            return
        await self.remove(bot_id)
        if previous == "running":
            await self.start(bot_id)

    async def reconcile(self) -> None:
        """Rebuild in-memory state from Docker's own ground truth — call
        once at keeper startup (wired into ``roost.keeper.app``'s
        lifespan).

        Docker containers outlive the keeper process; ``self._state``
        does not. Without this, a bot whose workspace container was
        created in a previous keeper run would be reported "absent" by
        ``status()`` after a restart — not just a cosmetic wrong status:
        ``start()`` would then try ``docker run`` for a container name
        Docker already has, which fails outright, instead of ``docker
        start`` (reuse), the path that actually applies here.

        Never raises: a Docker daemon that's unreachable at startup
        leaves ``self._state`` untouched rather than crashing keeper
        boot over what ``status()`` already handles — every bot simply
        reports "absent" until a later call succeeds.
        """
        outcome = await self._run(_build_list_argv(), _CONTROL_CALL_TIMEOUT_S)
        if outcome.returncode != 0:
            return
        listing = outcome.stdout.decode("utf-8", errors="replace")
        self._state.update(_parse_list_output(listing))
        self._internet = self._internet | _parse_internet(listing)

    async def start(self, bot_id: str) -> None:
        """Idempotent: a bot whose workspace is already running is a
        no-op; a bot previously stopped (but not removed) restarts its
        existing container rather than creating a second one under the
        same name (which ``docker run`` would refuse anyway)."""
        previous = self._state.get(bot_id)
        if previous == "running":
            return

        workspace_dir(self._config.desks_dir, bot_id).mkdir(parents=True, exist_ok=True)
        internet = self.internet(bot_id)
        if internet:
            await self._ensure_network(bot_id)
        argv = (_build_start_existing_argv(bot_id) if previous == "stopped"
                else _build_run_argv(self._config, bot_id, internet))
        outcome = await self._run(argv, _CONTROL_CALL_TIMEOUT_S)
        if outcome.returncode != 0:
            raise WorkspaceStartError(
                f"failed to start workspace for bot {bot_id}: {outcome.stderr.decode('utf-8', errors='replace')}"
            )
        self._state[bot_id] = "running"

    async def _ensure_network(self, bot_id: str) -> None:
        """A4: the egress proxy and the bot's own internal network exist before the workspace joins it."""
        if self._networks is None:
            raise WorkspaceStartError(f"no network to give the workspace of bot {bot_id}")
        try:
            await self._networks.ensure_egress()
            await self._networks.ensure_bot_network(bot_id)
        except RuntimeError as exc:
            raise WorkspaceStartError(f"the workspace network of bot {bot_id} could not be set up: {exc}") from exc

    async def exec(self, bot_id: str, argv: list[str], timeout_s: int) -> ExecResult:
        outcome = await self._run(_build_exec_argv(bot_id, argv), float(timeout_s))
        await self._reap(bot_id)

        stdout, stdout_cut = _truncate(outcome.stdout.decode("utf-8", errors="replace"))
        stderr, stderr_cut = _truncate(outcome.stderr.decode("utf-8", errors="replace"))
        return ExecResult(
            exit_code=outcome.returncode,
            stdout=stdout,
            stderr=stderr,
            timed_out=outcome.timed_out,
            truncated=stdout_cut or stderr_cut,
        )

    async def _reap(self, bot_id: str) -> None:
        # kill -9 -1's own exit code is ignored by design (brief): it
        # legitimately returns non-zero once there is nothing left to
        # signal, which is the common, healthy case.
        await self._run(_build_kill_all_argv(bot_id), _CONTROL_CALL_TIMEOUT_S)

        top = await self._run(_build_top_argv(bot_id), _CONTROL_CALL_TIMEOUT_S)
        if top.returncode == 0 and _has_leftover_process(top.stdout.decode("utf-8", errors="replace")):
            await self._recreate(bot_id)

    async def _recreate(self, bot_id: str) -> None:
        await self._run(_build_remove_argv(bot_id), _CONTAINER_REMOVE_TIMEOUT_S)
        self._state.pop(bot_id, None)
        await self.start(bot_id)

    async def stop(self, bot_id: str) -> None:
        if self._state.get(bot_id) != "running":
            return
        outcome = await self._run(_build_stop_argv(bot_id), _CONTROL_CALL_TIMEOUT_S)
        if outcome.returncode != 0 and not _container_already_gone(outcome.stderr):
            raise WorkspaceStopError(
                f"failed to stop workspace for bot {bot_id}: {outcome.stderr.decode('utf-8', errors='replace')}"
            )
        self._state[bot_id] = "stopped"

    async def remove(self, bot_id: str) -> None:
        outcome = await self._run(_build_remove_argv(bot_id), _CONTAINER_REMOVE_TIMEOUT_S)
        if outcome.returncode != 0 and not _container_already_gone(outcome.stderr):
            raise WorkspaceRemoveError(
                f"failed to remove workspace for bot {bot_id}: {outcome.stderr.decode('utf-8', errors='replace')}"
            )
        self._state.pop(bot_id, None)
