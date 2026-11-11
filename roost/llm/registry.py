"""Model ids — the ONLY place they're allowed to live (Global Constraints).

Nothing else in the codebase hardcodes a model id: callers use the
constants here, ``resolve_bot_model``, or ``make_model``, which picks a
provider from ``RoostConfig.model_mode``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from roost.config import RoostConfig
from roost.llm.types import Model


@dataclass(frozen=True)
class ModelChoice:
    key: str  # "fable" | "opus" | "sonnet" | "haiku"
    id: str
    label: str
    line: str


FABLE = ModelChoice("fable", "claude-fable-5-2", "Fable 5.2", "fable")
# The Fable before 5.2 (owner, 2026-11-10): no longer offered, but a bot or routine set to it keeps running on it.
FABLE_51 = ModelChoice("fable", "claude-fable-5-1", "Fable 5.1", "fable")
OPUS = ModelChoice("opus", "claude-opus-5-5", "Opus 5.5", "opus")
SONNET = ModelChoice("sonnet", "claude-sonnet-5-5", "Sonnet 5.5", "sonnet")
HAIKU = ModelChoice("haiku", "claude-haiku-5-5", "Haiku 5.5", "haiku")

# Bots choose among these (owner 2026-10-22: Haiku too, strong and cheap); Haiku also runs background jobs.
BOT_MODELS = (FABLE, SONNET, OPUS, HAIKU)
DEFAULT_BOT_MODEL = SONNET.id
WORKER = HAIKU.id
# A voice call's turns run on Haiku unless the bot has a pickable model of its own (fast first words).
CALL_MODEL = HAIKU.id
HELPER_MODELS = {"haiku": HAIKU.id, "sonnet": SONNET.id}
DEFAULT_HELPER_MODEL = "haiku"
EFFORTS = ("low", "medium", "high", "max")
# Display only: what each model does when no effort is set.
DEFAULT_EFFORT = {FABLE.id: "high", FABLE_51.id: "high", OPUS.id: "medium", SONNET.id: "high", HAIKU.id: "medium"}
KNOWN_MODEL_IDS = frozenset(
    {FABLE.id, FABLE_51.id, OPUS.id, SONNET.id, HAIKU.id, "claude-sonnet-5", "claude-haiku-4-5-20251001"}
)

_BOT_MODEL_IDS = frozenset(choice.id for choice in (*BOT_MODELS, FABLE_51))
_LABELS = {choice.id: choice.label for choice in (FABLE, FABLE_51, OPUS, SONNET, HAIKU)}


def pickable_model_ids(extra_ids: frozenset[str] = frozenset()) -> frozenset[str]:
    """What a bot may be set to: Fable, Sonnet, Opus, Haiku and any newly seen model."""
    return _BOT_MODEL_IDS | extra_ids


def resolve_bot_model(override: str | None, extra_ids: frozenset[str] = frozenset()) -> str:
    """The model a bot runs on: its override if pickable, else the default."""
    if override and override in pickable_model_ids(extra_ids):
        return override
    return DEFAULT_BOT_MODEL


def resolve_routine_model(
    routine_model: str | None, bot_override: str | None, extra_ids: frozenset[str] = frozenset(),
) -> str:
    """A routine run's model: the routine's own if pickable, else the bot's (owner, 2026-11-09)."""
    if routine_model and routine_model in pickable_model_ids(extra_ids):
        return routine_model
    return resolve_bot_model(bot_override, extra_ids)


def check_model(model_id: str | None) -> str:
    """The model a gate check runs on (owner, 2026-11-03: "use whatever brain is set for the bot"): the run's own
    bot model, resolved by the caller; a run that carries none uses the default bot model."""
    return model_id or DEFAULT_BOT_MODEL


def resolve_call_model(override: str | None, extra_ids: frozenset[str] = frozenset()) -> str:
    """The model a call turn runs on: the bot's override if pickable, else ``CALL_MODEL``."""
    if override and override in pickable_model_ids(extra_ids):
        return override
    return CALL_MODEL


def model_label(model_id: str, seen_labels: Mapping[str, str] | None = None) -> str:
    """A model's display name; unknown ids show as themselves."""
    return _LABELS.get(model_id) or (seen_labels or {}).get(model_id) or model_id


def make_model(config: RoostConfig) -> Model:
    """Build the ``Model`` this run should use, per ``config.model_mode``.

    ``"scripted"`` never imports the Claude SDK at all — the import is
    local to the other branch so a scripted-only run (every test) never
    needs the SDK's process/env plumbing to be importable.
    """
    if config.model_mode == "scripted":
        if config.model_script is not None:
            from roost.llm.scripted_team import ScriptedTeamModel

            return ScriptedTeamModel.from_file(config.model_script)
        from roost.llm.scripted import ScriptedModel

        return ScriptedModel()

    from roost.llm.claude_sdk import ClaudeSdkModel

    return ClaudeSdkModel(DEFAULT_BOT_MODEL)


def make_worker_model(config: RoostConfig) -> Model:
    """The cheap model for memory work; scripted mode never ignores itself."""
    if config.model_mode == "scripted":
        from roost.llm.scripted_worker import ScriptedWorker

        return ScriptedWorker()

    from roost.llm.claude_sdk import ClaudeSdkModel

    return ClaudeSdkModel(WORKER)
