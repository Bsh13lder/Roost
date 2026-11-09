"""The per-bot internal Docker networks and the ``roost-egress`` proxy container.

A computer sits only on ``roost-net-<bot id>`` (``--internal``: no route out, no outside DNS). ``roost-egress``
is attached to each of them and to ``roost-out`` (the one outbound bridge), so the only way out is its proxy.
Nothing here publishes a port. Every name starts with ``roost-``; the docker calls are argv lists, never a shell.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence

from roost.constants import (
    COMPUTER_DOCKER_CALL_TIMEOUT_S,
    COMPUTER_NETWORK_PREFIX,
    EGRESS_CONTAINER,
    EGRESS_IMAGE,
    EGRESS_OUT_NETWORK,
    EGRESS_UID,
)
from roost.keeper.workspaces import Runner, _run_docker

logger = logging.getLogger(__name__)

_BOT_LABEL = "app.roost.bot"
_PART_LABEL = "app.roost.part=egress"
_EGRESS_MEMORY = "128m"
_EGRESS_PIDS = "64"
_EGRESS_CPUS = "0.5"
_ALREADY_THERE = ("already exists",)
_NOT_FOUND = ("no such", "not found", "is not connected")


class NetworkError(RuntimeError):
    """A docker network call failed; the message is a plain sentence for the user."""


def _check_bot_id(bot_id: str) -> str:
    try:
        parsed = uuid.UUID(bot_id)
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValueError("That is not a bot id.") from exc
    if parsed.version != 4 or str(parsed) != bot_id:
        raise ValueError("That is not a bot id.")
    return bot_id


def network_name(bot_id: str) -> str:
    return f"{COMPUTER_NETWORK_PREFIX}{_check_bot_id(bot_id)}"


def build_network_create_argv(bot_id: str) -> list[str]:
    return ["docker", "network", "create", "--internal", "--label", f"{_BOT_LABEL}={_check_bot_id(bot_id)}",
            network_name(bot_id)]


def build_network_remove_argv(bot_id: str) -> list[str]:
    return ["docker", "network", "rm", network_name(bot_id)]


def build_egress_connect_argv(bot_id: str) -> list[str]:
    return ["docker", "network", "connect", network_name(bot_id), EGRESS_CONTAINER]


def build_egress_disconnect_argv(bot_id: str) -> list[str]:
    return ["docker", "network", "disconnect", network_name(bot_id), EGRESS_CONTAINER]


def build_out_network_create_argv() -> list[str]:
    return ["docker", "network", "create", EGRESS_OUT_NETWORK]


def build_egress_inspect_argv() -> list[str]:
    return ["docker", "container", "inspect", "-f", "{{.State.Running}}", EGRESS_CONTAINER]


def build_egress_start_argv() -> list[str]:
    return ["docker", "start", EGRESS_CONTAINER]


def build_egress_run_argv() -> list[str]:
    return [
        "docker", "run", "-d", "--name", EGRESS_CONTAINER, "--network", EGRESS_OUT_NETWORK,
        "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--user", f"{EGRESS_UID}:{EGRESS_UID}", "--memory", _EGRESS_MEMORY, "--cpus", _EGRESS_CPUS, "--pids-limit", _EGRESS_PIDS,
        "--label", _PART_LABEL, EGRESS_IMAGE,
    ]


class EgressNetworks:
    def __init__(self, *, runner: Runner | None = None) -> None:
        self._run: Runner = runner if runner is not None else _run_docker

    async def ensure_egress(self) -> None:
        """``roost-out`` and the ``roost-egress`` container exist and run."""
        await self._call(build_out_network_create_argv(), tolerate=_ALREADY_THERE)
        state = await self._run(build_egress_inspect_argv(), COMPUTER_DOCKER_CALL_TIMEOUT_S)
        if state.timed_out:
            raise NetworkError("Docker did not answer in time.")
        if state.returncode != 0:
            await self._call(build_egress_run_argv())
        elif state.stdout.decode().strip() != "true":
            await self._call(build_egress_start_argv())

    async def ensure_bot_network(self, bot_id: str) -> None:
        await self._call(build_network_create_argv(bot_id), tolerate=_ALREADY_THERE)
        await self._call(build_egress_connect_argv(bot_id), tolerate=_ALREADY_THERE)

    async def remove_bot_network(self, bot_id: str) -> None:
        await self._call(build_egress_disconnect_argv(bot_id), tolerate=_NOT_FOUND)
        await self._call(build_network_remove_argv(bot_id), tolerate=_NOT_FOUND)

    async def _call(self, argv: Sequence[str], *, tolerate: tuple[str, ...] = ()) -> None:
        outcome = await self._run(argv, COMPUTER_DOCKER_CALL_TIMEOUT_S)
        if outcome.timed_out:
            raise NetworkError("Docker did not answer in time.")
        if outcome.returncode == 0:
            return
        detail = outcome.stderr.decode(errors="replace").lower()
        if any(word in detail for word in tolerate):
            return
        logger.error("docker %s failed: %s", " ".join(argv[1:3]), detail.strip()[:300])
        raise NetworkError("The computer's network could not be set up. Check that Docker is running.")
