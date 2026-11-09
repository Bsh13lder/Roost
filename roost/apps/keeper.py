"""The gateway's seam to the keeper's apps route (``POST /desks/{id}/computer/apps``).

``KeeperApps`` sends signed requests; ``FakeApps`` keeps installed packages in memory for fake-desk mode and tests.
A refusal word from roost-apt (or ``asleep``) raises ``AppRefused``; an unreachable keeper or any other answer
raises ``DeskUnavailable``, whose text carries the status only (never a package name)."""

from __future__ import annotations

import json
from typing import Any, Protocol, Sequence

import httpx

from roost.apps.constants import APP_REQUEST_GRACE_S, keeper_timeout_s
from roost.apps.models import AppInfo
from roost.config import RoostConfig
from roost.desk import DeskUnavailable
from roost.desk.signing import signed_headers

ASLEEP = "asleep"


class AppRefused(RuntimeError):
    """roost-apt (or the keeper) refused: ``word`` is one of APP_REFUSAL_WORDS or ``asleep``."""

    def __init__(self, word: str) -> None:
        super().__init__(f"the computer refused: {word}")
        self.word = word


class AppKeeper(Protocol):
    async def describe(self, bot_id: str, package: str) -> AppInfo: ...
    async def install(self, bot_id: str, package: str) -> None: ...
    async def remove(self, bot_id: str, package: str) -> None: ...
    async def ensure(self, bot_id: str, packages: Sequence[str]) -> None: ...


class KeeperApps:
    def __init__(self, config: RoostConfig, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._config = config
        self._transport = transport

    async def _call(self, bot_id: str, verb: str, packages: Sequence[str]) -> dict[str, Any]:
        path = f"/desks/{bot_id}/computer/apps"
        body = json.dumps({"verb": verb, "packages": list(packages)}).encode()
        headers = {**signed_headers(self._config.keeper_secret, "POST", path, body), "content-type": "application/json"}
        timeout = keeper_timeout_s(verb) + APP_REQUEST_GRACE_S
        try:
            async with httpx.AsyncClient(transport=self._transport, timeout=timeout) as client:
                response = await client.post(f"{self._config.keeper_url}{path}", content=body, headers=headers)
        except httpx.TransportError as exc:
            raise DeskUnavailable(f"keeper unreachable for apps: {type(exc).__name__}") from exc
        if response.is_success:
            return response.json()
        word = _detail(response) if response.status_code == 409 else ""
        if word:
            raise AppRefused(word)
        raise DeskUnavailable(f"keeper returned {response.status_code} for apps {verb}")

    async def describe(self, bot_id: str, package: str) -> AppInfo:
        data = await self._call(bot_id, "describe", (package,))
        return AppInfo(package=package, version=str(data.get("version", "")),
                       description=str(data.get("description", "")))

    async def install(self, bot_id: str, package: str) -> None:
        await self._call(bot_id, "install", (package,))

    async def remove(self, bot_id: str, package: str) -> None:
        await self._call(bot_id, "remove", (package,))

    async def ensure(self, bot_id: str, packages: Sequence[str]) -> None:
        await self._call(bot_id, "ensure", tuple(packages))


def _detail(response: httpx.Response) -> str:
    try:
        detail = response.json().get("detail")
    except (ValueError, AttributeError):
        return ""
    return detail if isinstance(detail, str) else ""


class FakeApps:
    """In memory: what each bot's computer has. ``refusals`` maps a package to the word roost-apt would say."""

    def __init__(self, refusals: dict[str, str] | None = None) -> None:
        self.installed: dict[str, set[str]] = {}
        self.refusals = dict(refusals or {})
        self.fail = False
        self.calls: list[tuple[str, str, tuple[str, ...]]] = []

    @staticmethod
    def description_of(package: str) -> str:
        return f"{package}: a Debian package (fake computer)"

    def check(self, package: str) -> None:
        word = self.refusals.get(package)
        if word:
            raise AppRefused(word)

    def _on(self, bot_id: str) -> set[str]:
        return self.installed.get(bot_id, set())

    def _record(self, verb: str, bot_id: str, packages: Sequence[str]) -> None:
        self.calls = [*self.calls, (verb, bot_id, tuple(packages))]
        if self.fail:
            raise DeskUnavailable(f"fake keeper failed {verb}")

    async def describe(self, bot_id: str, package: str) -> AppInfo:
        self._record("describe", bot_id, (package,))
        self.check(package)
        if package in self._on(bot_id):
            raise AppRefused("already_installed")
        return AppInfo(package=package, version="1.0", description=self.description_of(package))

    async def install(self, bot_id: str, package: str) -> None:
        self._record("install", bot_id, (package,))
        self.check(package)
        self.installed = {**self.installed, bot_id: self._on(bot_id) | {package}}

    async def remove(self, bot_id: str, package: str) -> None:
        self._record("remove", bot_id, (package,))
        if package not in self._on(bot_id):
            raise AppRefused("not_installed")
        self.installed = {**self.installed, bot_id: self._on(bot_id) - {package}}

    async def ensure(self, bot_id: str, packages: Sequence[str]) -> None:
        self._record("ensure", bot_id, packages)
        self.installed = {**self.installed, bot_id: self._on(bot_id) | set(packages)}


def make_app_keeper(config: RoostConfig) -> AppKeeper:
    """The fake in fake-desk mode (tests, E2E), the keeper otherwise."""
    return FakeApps() if config.desk_mode == "fake" else KeeperApps(config)
