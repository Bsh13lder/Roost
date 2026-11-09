"""The keeper's apps route: ``POST /desks/{bot_id}/computer/apps`` (docs/plans/2026-10-22-roost-install-app.md §4).

The gateway sends it only after the owner's Yes on an Ask card (install, remove), the owner's own Remove, a card
being built (describe) or a fresh computer's reinstall (ensure). The body is strict (``extra="forbid"``): a verb
and a list of package names, each checked against Debian's rule and the deny list again here. The keeper turns
it into one fixed argv, ``docker exec --user 0:0 roost-computer-<id> /usr/local/bin/roost-apt <verb>
<package>...``, run with no shell and no stdin, bounded by roost-apt's deadline plus a grace, its output capped.
roost-apt checks everything a third time inside the computer.

Refusals: unsigned 401, a bad id 400, a bad body or a denied name 422, a computer that is not running 409
``asleep`` (never wakes one), roost-apt's own refusal word 409, anything else 500 ``apps failed``. The audit gets
only ``computer_apps``, the bot id, the verb and a result word: never a package name.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import Awaitable, Callable, Sequence
from typing import Literal

from fastapi import APIRouter, Depends, FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from roost.apps.constants import (
    APP_OUTPUT_MAX_BYTES, APP_REFUSAL_WORDS, APPS_PER_BOT_MAX, APT_BIN, keeper_timeout_s,
)
from roost.apps.names import is_denied, valid_name
from roost.keeper.auth import require_signed_body
from roost.keeper.computers import container_name
from roost.keeper.workspaces import _RunOutcome

logger = logging.getLogger(__name__)

_AUDIT_ACTION = "computer_apps"
_ROOT = "0:0"
_REFUSED_EXIT = 3
_FAILED = "apps failed"
_BAD_NAME = "not an allowed package name"
_ONE_ONLY = "this verb takes exactly one package"

AppVerb = Literal["describe", "install", "remove", "ensure"]


class AppsBody(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    verb: AppVerb
    packages: list[str] = Field(min_length=1, max_length=APPS_PER_BOT_MAX)

    @field_validator("packages")
    @classmethod
    def _allowed(cls, packages: list[str]) -> list[str]:
        if len(set(packages)) != len(packages) or not all(valid_name(p) and not is_denied(p) for p in packages):
            raise ValueError(_BAD_NAME)
        return packages

    @model_validator(mode="after")
    def _one_for_most_verbs(self) -> "AppsBody":
        if self.verb != "ensure" and len(self.packages) != 1:
            raise ValueError(_ONE_ONLY)
        return self


def build_apps_argv(bot_id: str, verb: str, packages: Sequence[str]) -> list[str]:
    """The one argv for this call. A bot id that is not a UUID4 raises ``ValueError``."""
    return ["docker", "exec", "--user", _ROOT, container_name(bot_id), APT_BIN, verb, *packages]


AppsRunner = Callable[[Sequence[str], float], Awaitable[_RunOutcome]]


async def run_apps(argv: Sequence[str], timeout_s: float) -> _RunOutcome:
    """Run ``argv`` with no shell and stdin closed, bounded by ``timeout_s`` (killed after); output capped."""
    proc = await asyncio.create_subprocess_exec(
        *argv, stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
    except asyncio.TimeoutError:
        with contextlib.suppress(ProcessLookupError):
            proc.kill()
        with contextlib.suppress(Exception):
            await proc.wait()
        return _RunOutcome(returncode=-1, stdout=b"", stderr=b"", timed_out=True)
    return _RunOutcome(returncode=proc.returncode or 0, stdout=stdout[:APP_OUTPUT_MAX_BYTES],
                       stderr=stderr[:APP_OUTPUT_MAX_BYTES], timed_out=False)


def _parse_body(body: bytes) -> AppsBody:
    try:
        return AppsBody.model_validate_json(body or b"{}")
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors(include_input=False, include_url=False,
                                                               include_context=False)) from exc


def _outcome_word(outcome: _RunOutcome) -> str:
    """``ok``, roost-apt's own refusal word, or ``error``. Never reads anything but a fixed word."""
    if outcome.timed_out:
        return "error"
    if outcome.returncode == 0:
        return "ok"
    word = outcome.stderr.decode("utf-8", "replace").strip()
    return word if outcome.returncode == _REFUSED_EXIT and word in APP_REFUSAL_WORDS else "error"


def _described(stdout: bytes) -> dict[str, str]:
    """roost-apt's describe answer, as three short strings; anything else is a failure."""
    try:
        data = json.loads(stdout.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise HTTPException(status_code=500, detail=_FAILED) from exc
    if not isinstance(data, dict) or not all(isinstance(data.get(k), str) for k in ("package", "version", "description")):
        raise HTTPException(status_code=500, detail=_FAILED)
    return {k: data[k] for k in ("package", "version", "description")}


def apps_routes(app: FastAPI) -> APIRouter:
    router = APIRouter()
    app.state.apps_runner = run_apps

    async def run(bot_id: str, parsed: AppsBody) -> _RunOutcome | None:
        argv = build_apps_argv(bot_id, parsed.verb, parsed.packages)
        try:
            return await app.state.apps_runner(argv, keeper_timeout_s(parsed.verb))
        except OSError:
            logger.error("apps %s for bot %s could not run", parsed.verb, bot_id)
            return None

    @router.post("/desks/{bot_id}/computer/apps")
    async def computer_apps(bot_id: str, body: bytes = Depends(require_signed_body)):
        try:
            container_name(bot_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="bot_id must be a UUID4") from exc
        parsed = _parse_body(body)
        audit = lambda word: app.state.audit.record(_AUDIT_ACTION, bot_id, word, verb=parsed.verb)  # noqa: E731
        if app.state.computers.state(bot_id) != "running":
            audit("asleep")
            raise HTTPException(status_code=409, detail="asleep")
        app.state.computers.touch(bot_id)
        outcome = await run(bot_id, parsed)
        word = "error" if outcome is None else _outcome_word(outcome)
        audit(word)
        if word in APP_REFUSAL_WORDS:
            raise HTTPException(status_code=409, detail=word)
        if word != "ok" or outcome is None:
            logger.warning("apps %s for bot %s failed (exit %s)", parsed.verb, bot_id,
                           None if outcome is None else outcome.returncode)
            raise HTTPException(status_code=500, detail=_FAILED)
        extra = _described(outcome.stdout) if parsed.verb == "describe" else {}
        return {"done": True, **extra}

    return router
