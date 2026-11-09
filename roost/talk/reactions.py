"""Tapbacks (chat-feel Task 8): one small reaction per message, from you only.

A reaction is stored as a ``reaction`` message (role ``user``) whose sealed body is JSON
``{"target_id", "key"}``; ``key`` is one of ``REACTION_KEYS``, or ``None`` to clear. It is never replayed to
the model, queues no work, and is never a chat-list preview."""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict

from roost.constants import REACTION_KEYS

ReactionKey = Literal[*REACTION_KEYS]
REACTION_KIND = "reaction"
NOT_FOUND_TEXT = "Message not found"


class ReactionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: ReactionKey | None


def reaction_body(target_id: str, key: str | None) -> str:
    return json.dumps({"target_id": target_id, "key": key})
