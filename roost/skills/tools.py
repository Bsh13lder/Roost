"""``SkillTools``: a bot lists the user's Skills that are on for it and loads one's steps (both reads), and offers a
new skill or a change on a card (``propose_skill``, ``propose_skill_change``; neither writes a skill).

Every skill string a model sees is escaped and quoted under a head that calls it data. Reading a skill marked *from
web content* taints the run, the way reading a page does; listing taints only when it shows a marked skill. At
most ``SKILL_READS_PER_RUN_MAX`` reads per run, counted here by the run's id."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from roost.constants import (
    SKILL_BODY_MAX,
    SKILL_NAME_MAX,
    SKILL_READS_PER_RUN_MAX,
    SKILL_SEARCH_QUERY_MAX,
    SKILL_SEARCH_RESULTS_MAX,
    SKILL_USE_WHEN_MAX,
)
from roost.records.tool_text import ToolText
from roost.skills.models import Skill, SkillDraft, SkillPatch, SkillProposalPayload, plain_error
from roost.skills.prompt import quote
from roost.skills.proposals import ProposalRequest, SkillProposalRefused, SkillProposalService
from roost.skills.service import SkillRefused, SkillService, needs_a_change
from roost.skills.texts import (
    ASKED, ASKED_CHANGE, LIST_EMPTY, LIST_HEAD, NAME_TAKEN, NO_CHAT, NO_SUCH_SKILL, READ_HEAD, READ_TAINTED_HEAD,
    READS_CAP, SEARCH_EMPTY, SEARCH_HEAD, SEARCH_NONE, SKILL_OFF,
)
from roost.skills.search import rank_skills
from roost.talk.domain_tools import RecordContext
from roost.talk.outcome import ToolOutcome


READ_NAMES = frozenset({"list_skills", "read_skill", "search_skills"})
PROPOSE_NAMES = frozenset({"propose_skill", "propose_skill_change"})
_RUNS_KEPT = 256          # per-run read counts kept; the oldest run's count is dropped first
_MARK = "(from web content)"
_BAD_ARGS = "Refused: {name} needs valid arguments (see its description)."


class ReadArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: ToolText = Field(min_length=1, max_length=SKILL_NAME_MAX * 2)


class SearchArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")

    query: ToolText = Field(max_length=SKILL_SEARCH_QUERY_MAX * 2)


class ProposeArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: ToolText = Field(max_length=SKILL_NAME_MAX * 2)
    use_when: ToolText = Field(max_length=SKILL_USE_WHEN_MAX * 2)
    steps: ToolText = Field(max_length=SKILL_BODY_MAX * 2)


class ChangeArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")

    skill: ToolText = Field(min_length=1, max_length=SKILL_NAME_MAX * 2)
    name: ToolText | None = Field(default=None, max_length=SKILL_NAME_MAX * 2)
    use_when: ToolText | None = Field(default=None, max_length=SKILL_USE_WHEN_MAX * 2)
    steps: ToolText | None = Field(default=None, max_length=SKILL_BODY_MAX * 2)


def _checked(model, **fields):
    """The draft or patch, or ``SkillRefused`` with its plain sentence (a secret is named by kind, never shown)."""
    try:
        return model(**fields)
    except ValidationError as exc:
        raise SkillRefused(plain_error(exc)) from None


def run_key(ctx: RecordContext) -> str:
    return ctx.run_id or f"bot:{ctx.bot_id}"


def list_line(skill: Skill) -> str:
    parts = [quote(skill.name), f"Use when: {quote(skill.use_when)}", _MARK if skill.tainted else ""]
    return "- " + " · ".join(p for p in parts if p)


class SkillTools:
    names = READ_NAMES | PROPOSE_NAMES

    def __init__(self, skills: SkillService, proposals: SkillProposalService | None = None) -> None:
        self._skills = skills
        self._proposals = proposals
        self._reads: dict[str, int] = {}

    def activity(self, name: str) -> str:
        if name in ("list_skills", "search_skills"):
            return "looking at its skills"
        return "reading a skill" if name == "read_skill" else "offering a skill"

    async def run(self, name: str, arguments: dict[str, Any], ctx: RecordContext) -> ToolOutcome:
        try:
            if name == "list_skills":
                return await self._list(ctx)
            if name == "read_skill":
                return await self._read(ReadArgs.model_validate(arguments), ctx)
            if name == "search_skills":
                return await self._search(SearchArgs.model_validate(arguments), ctx)
            if self._proposals is None:
                return ToolOutcome("Refused: skill proposals are not available here.")
            if name == "propose_skill":
                return await self._propose(ProposeArgs.model_validate(arguments), ctx)
            return await self._propose_change(ChangeArgs.model_validate(arguments), ctx)
        except ValidationError:
            return ToolOutcome(_BAD_ARGS.format(name=name))
        except (SkillRefused, SkillProposalRefused) as refused:
            return ToolOutcome(f"Refused: {quote(refused.text)}")

    async def _list(self, ctx: RecordContext) -> ToolOutcome:
        skills = await self._skills.on_for_bot(ctx.user_id, ctx.bot_id)
        if not skills:
            return ToolOutcome(LIST_EMPTY)
        return ToolOutcome("\n".join([LIST_HEAD, *(list_line(s) for s in skills)]),
                           tainted=any(s.tainted for s in skills))

    async def _search(self, args: SearchArgs, ctx: RecordContext) -> ToolOutcome:
        """The best few skills on for this bot that the words name; it taints only when it shows a marked skill."""
        if not args.query.strip():
            return ToolOutcome(SEARCH_EMPTY)
        found = rank_skills(await self._skills.on_for_bot(ctx.user_id, ctx.bot_id), args.query)
        best = found[:SKILL_SEARCH_RESULTS_MAX]
        if not best:
            return ToolOutcome(SEARCH_NONE)
        return ToolOutcome("\n".join([SEARCH_HEAD, *(list_line(s) for s in best)]),
                           tainted=any(s.tainted for s in best))

    async def _read(self, args: ReadArgs, ctx: RecordContext) -> ToolOutcome:
        key = run_key(ctx)
        done = self._reads.get(key, 0)
        if done >= SKILL_READS_PER_RUN_MAX:
            return ToolOutcome(READS_CAP.format(n=done))
        skill = await self._skills.find(ctx.user_id, args.name)
        if skill is None:
            return ToolOutcome(NO_SUCH_SKILL.format(name=quote(args.name)))
        if not await self._skills.is_on(ctx.user_id, ctx.bot_id, skill.id):
            return ToolOutcome(SKILL_OFF.format(name=quote(skill.name)))
        self._count(key, done + 1)
        head = (READ_TAINTED_HEAD if skill.tainted else READ_HEAD).format(name=quote(skill.name))
        return ToolOutcome(f"{head}\n<skill>\n{quote(skill.body)}\n</skill>", tainted=skill.tainted)

    async def _propose(self, args: ProposeArgs, ctx: RecordContext) -> ToolOutcome:
        draft = _checked(SkillDraft, name=args.name, use_when=args.use_when, body=args.steps)
        taken = await self._skills.find(ctx.user_id, draft.name)
        if taken is not None:
            raise SkillRefused(NAME_TAKEN.format(name=taken.name))
        payload = SkillProposalPayload(name=draft.name, use_when=draft.use_when, body=draft.body)
        await self._send(ctx, "create", payload, None)
        return ToolOutcome(ASKED.format(name=quote(draft.name)), created=True)

    async def _propose_change(self, args: ChangeArgs, ctx: RecordContext) -> ToolOutcome:
        skill = await self._skills.find(ctx.user_id, args.skill)
        if skill is None:
            return ToolOutcome(NO_SUCH_SKILL.format(name=quote(args.skill)))
        if not await self._skills.is_on(ctx.user_id, ctx.bot_id, skill.id):
            return ToolOutcome(SKILL_OFF.format(name=quote(skill.name)))
        patch = _checked(SkillPatch, name=args.name, use_when=args.use_when, body=args.steps)
        needs_a_change(patch)
        if patch.name is not None:
            taken = await self._skills.find(ctx.user_id, patch.name)
            if taken is not None and taken.id != skill.id:
                raise SkillRefused(NAME_TAKEN.format(name=taken.name))
        await self._send(ctx, "change", SkillProposalPayload(**patch.model_dump(exclude_none=True)), skill)
        return ToolOutcome(ASKED_CHANGE.format(name=quote(skill.name)))

    async def _send(self, ctx: RecordContext, action, payload: SkillProposalPayload, skill: Skill | None) -> None:
        if ctx.thread_id is None:
            raise SkillRefused(NO_CHAT)
        await self._proposals.propose(ProposalRequest(
            user_id=ctx.user_id, bot_id=ctx.bot_id, action=action, payload=payload, thread_id=ctx.thread_id,
            tainted=ctx.tainted, from_routine=ctx.from_routine, skill=skill))

    def _count(self, key: str, n: int) -> None:
        kept = {k: v for k, v in self._reads.items() if k != key}
        if len(kept) >= _RUNS_KEPT:
            kept = dict(list(kept.items())[1:])
        self._reads = {**kept, key: n}
