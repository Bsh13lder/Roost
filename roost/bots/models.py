"""Bot domain model — frozen dataclasses, no mutation.

``Bot`` is the fully-hydrated row (always has an ``id``/``user_id`` and a
``status``); ``BotDraft`` is what ``BotStore.create`` accepts (no id, no
status — those are the store's to assign); ``BotPatch`` is a partial
update where every field defaults to ``None`` meaning "leave unchanged"
(``BotStore.update`` fills in the gaps from the existing row, see its
docstring).

Field-level validation (name pattern, color hex, max lengths) is a
gateway-boundary concern — see ``roost/gateway/routes/bots.py``'s
pydantic models — not this module's: these dataclasses are also
constructed directly in unit tests (``tests/test_bot_store.py``) and by
future non-HTTP callers, so they stay plain, trusted-input containers.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal

from roost.approvals.models import DEFAULT_BOT_APPROVAL, BotApproval
from roost.constants import DEFAULT_COMPUTER, DEFAULT_ROBOT_SCREEN
from roost.voice.constants import DEFAULT_VOICE, VoiceSettings

# The eighteen Lensbot shapes, then the ten ghosts, the six robot heads and the S1.6 bird shapes still
# accepted (roost/constants.py AVATAR_SHAPES, the same list in the same order).
AvatarShape = Literal[
    "mochi", "loaf", "gumdrop", "pebble", "bun", "acorn", "marsh", "dumpling", "muffs", "squish", "cub", "sprout",
    "cheeky", "tower", "helmet", "bell", "puck", "pod",
    "dome", "tall", "wide", "round", "droopy", "spire", "comet", "cape", "puff", "hooded",
    "classic", "soft", "cube", "monitor", "egg", "pear", "plump", "crest",
]
# The job a bot's body shows as an emblem (roost/constants.py BOT_ROLES). None: general.
BotRole = Literal["general", "tasks", "code", "seo", "money", "social", "research", "writer"]
# Accepted and stored, no longer drawn: a ghost has no screen.
AvatarScreen = Literal["glow", "pixel", "signal"]
AvatarBadge = Literal["none", "tasks", "finance", "notes", "docs", "inbox"]
ComputerKind = Literal["linux", "mac_brave"]   # which browser the bot works in (schema v24)


class BotStatus(str, Enum):
    RESTING = "resting"
    ON_IT = "on_it"
    ASKING_YOU = "asking_you"
    STUCK = "stuck"
    OFF_DUTY = "off_duty"


@dataclass(frozen=True)
class Avatar:
    shape: AvatarShape
    color: str  # "#RRGGBB"
    badge: AvatarBadge
    screen: AvatarScreen = DEFAULT_ROBOT_SCREEN  # the robot screen's signal style (redesign V1)
    picture: str | None = None  # the uploaded picture's version tag; the picture itself never rides on a Bot
    role: BotRole | None = None  # the job's emblem (avatars v7); None counts as general


@dataclass(frozen=True)
class Bot:
    id: str
    user_id: str
    name: str
    job: str
    instructions: str
    avatar: Avatar
    template_id: str | None
    status: BotStatus
    model_override: str | None
    created_at: str
    updated_at: str
    off_duty: bool = False
    is_primary: bool = False
    notify: bool = True
    group: str | None = None   # the sidebar label; None: no label
    pinned: bool = False
    pinned_at: str | None = None   # when it was pinned: the order of the sidebar's robot row
    effort: str | None = None      # low | medium | high | max; None: the model's default
    approval: BotApproval = DEFAULT_BOT_APPROVAL   # approval mode and topic switches (schema v23)
    computer: ComputerKind = DEFAULT_COMPUTER      # a plaintext setting; never in a prompt or Template
    full_limit_until: str | None = None            # UTC ISO end of the full limit; None: off (only its route sets it)
    workspace_internet: bool = False               # A4: the workspace reaches public hosts through roost-egress
    voice: VoiceSettings = DEFAULT_VOICE           # v37: how it sounds when it reads a reply aloud


@dataclass(frozen=True)
class BotDraft:
    name: str
    job: str
    instructions: str
    avatar: Avatar
    template_id: str | None = None


@dataclass(frozen=True)
class BotPatch:
    name: str | None = None
    job: str | None = None
    instructions: str | None = None
    avatar: Avatar | None = None
    group: str | None = None   # None keeps the label, "" clears it, text sets it
    computer: ComputerKind | None = None   # None keeps it


class DuplicateBotName(ValueError):
    """Raised by ``BotStore.create``/``update`` on a case-insensitive name collision."""
