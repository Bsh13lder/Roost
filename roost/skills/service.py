"""``SkillService``: the one place for the rules the editor and the bots' proposals share.

The user's own save clears the *from web content* mark, a stale save is a ``SkillConflict`` with the current copy,
and every change publishes ``skills_changed``. A bot or skill that is not the user's is ``NoSuchBot`` /
``NoSuchSkill``. Logs carry ids and type names only, never a skill's text."""

from __future__ import annotations

import logging
from typing import Protocol

from pydantic import ValidationError

from roost.bots.store import BotStore
from roost.constants import SKILLS_PER_USER_MAX
from roost.events.hub import EventHub
from roost.records.revision import RevisionConflict
from roost.skills.models import Skill, SkillDraft, SkillForBot, SkillOrigin, SkillPatch, plain_error
from roost.skills.store import SkillNameTaken, SkillsFull, SkillStore
from roost.skills.template_skills import TemplateSkill, import_plan
from roost.skills.texts import NAME_TAKEN, NO_CHANGE, SKILLS_FULL

logger = logging.getLogger(__name__)

SKILLS_CHANGED = "skills_changed"


class NoSuchSkill(LookupError):
    """The skill is not this user's, or it is gone."""


class NoSuchBot(LookupError):
    """The bot is not this user's."""


class SkillRefused(ValueError):
    """A plain sentence for the user or the bot (422)."""

    def __init__(self, text: str) -> None:
        super().__init__(text)
        self.text = text


class SkillConflict(Exception):
    """A save on an older revision (409); ``current`` is the stored skill."""

    def __init__(self, current: Skill) -> None:
        super().__init__("The skill changed since it was read.")
        self.current = current


class _Events(Protocol):
    async def publish(self, user_id: str, event: dict) -> int: ...


class SkillService:
    def __init__(self, store: SkillStore, events: EventHub | _Events, bots: BotStore) -> None:
        self._store = store
        self._events = events
        self._bots = bots

    @property
    def store(self) -> SkillStore:
        return self._store

    async def list(self, user_id: str) -> tuple[Skill, ...]:
        return await self._store.list(user_id)

    async def list_for_bot(self, user_id: str, bot_id: str) -> tuple[SkillForBot, ...]:
        await self._own_bot(user_id, bot_id)
        off = await self._store.off_ids(user_id, bot_id)
        return tuple(SkillForBot(skill=s, on=s.id not in off) for s in await self._store.list(user_id))

    async def on_for_bot(self, user_id: str, bot_id: str) -> tuple[Skill, ...]:
        """The skills switched on for this bot (the caller already knows the bot is the user's)."""
        off = await self._store.off_ids(user_id, bot_id)
        return tuple(s for s in await self._store.list(user_id) if s.id not in off)

    async def is_on(self, user_id: str, bot_id: str, skill_id: str) -> bool:
        return skill_id not in await self._store.off_ids(user_id, bot_id)

    async def get(self, user_id: str, skill_id: str) -> Skill:
        skill = await self._store.get(user_id, skill_id)
        if skill is None:
            raise NoSuchSkill(skill_id)
        return skill

    async def find(self, user_id: str, name: str) -> Skill | None:
        return await self._store.get_by_name(user_id, name)

    async def add(self, user_id: str, draft: SkillDraft, *, origin: SkillOrigin = "user", tainted: bool = False,
                  created_by_bot: str | None = None) -> Skill:
        try:
            skill = await self._store.create(user_id, draft, origin=origin, tainted=tainted,
                                             created_by_bot=created_by_bot)
        except SkillNameTaken as exc:
            raise SkillRefused(NAME_TAKEN.format(name=exc.existing.name)) from None
        except SkillsFull:
            raise SkillRefused(SKILLS_FULL) from None
        await self._changed(user_id)
        return skill

    async def save(self, user_id: str, skill_id: str, patch: SkillPatch, *, base_revision: int,
                   tainted: bool = False) -> Skill:
        """The editor's Save skill (``tainted`` False: the user wrote or checked the text), or a proposal's."""
        try:
            saved = await self._store.update(user_id, skill_id, patch, base_revision=base_revision, tainted=tainted)
        except RevisionConflict as exc:
            raise SkillConflict(exc.current) from None
        except SkillNameTaken as exc:
            raise SkillRefused(NAME_TAKEN.format(name=patch.name or "")) from exc
        if saved is None:
            raise NoSuchSkill(skill_id)
        await self._changed(user_id)
        return saved

    async def delete(self, user_id: str, skill_id: str) -> None:
        if not await self._store.delete(user_id, skill_id):
            raise NoSuchSkill(skill_id)
        await self._changed(user_id)

    async def set_on(self, user_id: str, bot_id: str, skill_id: str, on: bool) -> bool:
        await self._own_bot(user_id, bot_id)
        if not await self._store.set_on(user_id, bot_id, skill_id, on):
            raise NoSuchSkill(skill_id)
        await self._changed(user_id, bot_id)
        return on

    async def import_from_template(self, user_id: str, wanted: tuple[TemplateSkill, ...],
                                   bot_id: str | None = None) -> tuple[tuple[Skill, ...], tuple[str, ...]]:
        """Add the ticked skills of a template file, marked as outside content (``origin='file'``, tainted).
        Names the user has are skipped. Every draft is checked first and the cap counted, so a refusal adds none."""
        if bot_id is not None:
            await self._own_bot(user_id, bot_id)
        lines = import_plan([s.name for s in await self._store.list(user_id)], wanted)
        drafts = [_draft_of(line.skill) for line in lines if line.state == "add"]
        if len(await self._store.list(user_id)) + len(drafts) > SKILLS_PER_USER_MAX:
            raise SkillRefused(SKILLS_FULL)
        added: list[Skill] = []
        for draft in drafts:
            try:
                added.append(await self._store.create(user_id, draft, origin="file", tainted=True,
                                                      created_by_bot=None))
            except (SkillNameTaken, SkillsFull) as exc:
                logger.info("skill import stopped for user %s: %s", user_id, type(exc).__name__)
                raise SkillRefused(SKILLS_FULL if isinstance(exc, SkillsFull) else NAME_TAKEN.format(
                    name=exc.existing.name)) from None
        if added:
            await self._changed(user_id)
        return tuple(added), tuple(line.skill.name for line in lines if line.state == "have")

    async def _own_bot(self, user_id: str, bot_id: str) -> None:
        if await self._bots.get(user_id, bot_id) is None:
            raise NoSuchBot(bot_id)

    async def _changed(self, user_id: str, bot_id: str | None = None) -> None:
        event: dict = {"type": SKILLS_CHANGED}
        if bot_id is not None:
            event["bot_id"] = bot_id
        try:
            await self._events.publish(user_id, event)
        except Exception as exc:  # noqa: BLE001 - the write stands; the frame is a hint to reload
            logger.warning("skills_changed not published for user %s: %s", user_id, type(exc).__name__)


def _draft_of(skill: TemplateSkill) -> SkillDraft:
    try:
        return SkillDraft(name=skill.name, use_when=skill.use_when, body=skill.steps)
    except ValidationError as exc:
        raise SkillRefused(plain_error(exc)) from None


def needs_a_change(patch: SkillPatch) -> None:
    """A bot's change proposal must change something."""
    if patch.is_empty():
        raise SkillRefused(NO_CHANGE)
