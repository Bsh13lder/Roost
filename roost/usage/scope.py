"""Who a model call's tokens belong to: the run's ``UsageScope``, held in a context variable.

The runner opens a scope for each batch (``usage_scope``: the user, the bot, the kind of run), a helper narrows
its kind (``kind_scope``), and the two places that read a model's stream (``roost/talk/steps.py`` and
``roost/memory/worker.py``) call ``note_usage`` when a ``TurnDone`` carries usage. Background tasks spawned from
a run copy its context, so a memory capture after a chat run is still that bot's. No scope, no usage: nothing is
recorded, and a failing recorder is logged and never breaks the call."""

from __future__ import annotations

import contextvars
import logging
from contextlib import contextmanager
from dataclasses import dataclass, replace
from typing import Iterator, Protocol

from roost.constants import (
    USAGE_KIND_BACKGROUND,
    USAGE_KIND_CHAT,
    USAGE_KIND_HANDOFF,
    USAGE_KIND_ROOM,
    USAGE_KIND_ROUTINE,
)
from roost.llm.types import Usage
from roost.work.models import WorkKind

logger = logging.getLogger(__name__)

_KIND_FOR_WORK = {WorkKind.ROUTINE: USAGE_KIND_ROUTINE, WorkKind.HANDOFF: USAGE_KIND_HANDOFF,
                  WorkKind.ROOM_POST: USAGE_KIND_ROOM}


class UsageRecorder(Protocol):
    async def add(self, user_id: str, bot_id: str | None, kind: str, model: str, usage: Usage) -> None: ...


@dataclass(frozen=True)
class UsageScope:
    recorder: UsageRecorder
    user_id: str
    bot_id: str | None
    kind: str


_SCOPE: contextvars.ContextVar[UsageScope | None] = contextvars.ContextVar("roost_usage_scope", default=None)


def kind_for_work(kind: WorkKind) -> str:
    """A run's usage kind from its first item: your messages and card answers are chat."""
    return _KIND_FOR_WORK.get(kind, USAGE_KIND_CHAT)


def current_scope() -> UsageScope | None:
    return _SCOPE.get()


@contextmanager
def usage_scope(scope: UsageScope | None) -> Iterator[None]:
    token = _SCOPE.set(scope)
    try:
        yield
    finally:
        _SCOPE.reset(token)


@contextmanager
def kind_scope(kind: str) -> Iterator[None]:
    """The current scope with another kind (a helper's steps); nothing when there is no scope."""
    scope = _SCOPE.get()
    with usage_scope(replace(scope, kind=kind) if scope is not None else None):
        yield


def background_scope(recorder: UsageRecorder | None, user_id: str, bot_id: str | None):
    """The scope of a worker job started outside a run (an English fix, a teach draft); none without a recorder."""
    return usage_scope(UsageScope(recorder, user_id, bot_id, USAGE_KIND_BACKGROUND) if recorder is not None else None)


async def note_usage(model: str, usage: Usage | None, *, kind: str | None = None) -> None:
    """Record one call's usage against the current scope (``kind`` overrides the scope's)."""
    scope = _SCOPE.get()
    if scope is None or usage is None:
        return
    try:
        await scope.recorder.add(scope.user_id, scope.bot_id, kind or scope.kind, model, usage)
    except Exception:
        logger.exception("Token usage not recorded for bot %s", scope.bot_id)
