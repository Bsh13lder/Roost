"""'Update my instructions?' (docs/plans/2026-10-22-roost-replies.md, part 3).

``propose`` never writes a bot's instructions. It structures the bot's new text into the five sections, seals it
with the instructions it replaces and the bot's reason, and posts an ``instructions_proposal`` card (in the run's
chat, and in the bot's own chat when the run was elsewhere). Only the user's Accept writes, through
``BotStore.update`` (the PATCH path), and only while the bot's instructions are still the ones the card was made
from. A card from a run that read web content or from a routine says so. One open card per bot."""

from __future__ import annotations

import json

from roost.bots.instruction_sections import structure_instructions
from roost.bots.models import Bot, BotPatch
from roost.bots.redact import find_secret_kinds
from roost.bots.store import BotStore
from roost.constants import INSTRUCTION_PROPOSALS_OPEN_PER_BOT_MAX
from roost.events.hub import EventHub
from roost.instruction_proposals.diff import line_diff
from roost.instruction_proposals.models import InstructionPayload, InstructionProposal, ProposalRequest, ProposalView
from roost.instruction_proposals.store import InstructionProposalStore
from roost.instruction_proposals.texts import NO_CHANGE, NO_SUCH_BOT, NOT_OPEN, SECRET, STALE, TOO_MANY_OPEN
from roost.talk.store import TalkStore, message_out

PROPOSALS_CHANGED = "instruction_proposals_changed"
MESSAGE_KIND = "instructions_proposal"


class NoSuchInstructionProposal(LookupError):
    """The card is not there, or not the user's (404)."""


class InstructionProposalRefused(ValueError):
    """A proposal that can't be made or accepted; ``text`` is a plain sentence."""

    def __init__(self, text: str) -> None:
        super().__init__(text)
        self.text = text


class InstructionProposalClosed(RuntimeError):
    """Another press decided it first (409)."""


class InstructionProposalService:
    def __init__(self, store: InstructionProposalStore, bots: BotStore, talk: TalkStore, events: EventHub) -> None:
        self._store = store
        self._bots = bots
        self._talk = talk
        self._events = events

    async def propose(self, request: ProposalRequest) -> InstructionProposal:
        """Store the sealed proposal and post its card; ``InstructionProposalRefused`` with a plain sentence."""
        bot = await self._bots.get(request.user_id, request.bot_id)
        if bot is None:
            raise InstructionProposalRefused(NO_SUCH_BOT)
        if await self._store.count_open(request.user_id, bot.id) >= INSTRUCTION_PROPOSALS_OPEN_PER_BOT_MAX:
            raise InstructionProposalRefused(TOO_MANY_OPEN)
        kinds = find_secret_kinds(request.new_text) + find_secret_kinds(request.why)
        if kinds:
            raise InstructionProposalRefused(SECRET.format(kinds=" or ".join(dict.fromkeys(kinds))))
        after = structure_instructions(request.new_text, name=bot.name, job=bot.job)
        if after in (bot.instructions, structure_instructions(bot.instructions, name=bot.name, job=bot.job)):
            raise InstructionProposalRefused(NO_CHANGE)
        payload = InstructionPayload(before=bot.instructions, after=after, why=request.why)
        proposal = await self._store.create(request.user_id, bot.id, payload, thread_id=request.thread_id,
                                            tainted=request.tainted, from_routine=request.from_routine)
        await self._post_card(proposal)
        await self._changed(proposal)
        return proposal

    async def list_open(self, user_id: str) -> tuple[ProposalView, ...]:
        return tuple([await self._view(p) for p in await self._store.list_open(user_id)])

    async def get(self, user_id: str, proposal_id: str) -> ProposalView:
        proposal = await self._store.get(user_id, proposal_id)
        if proposal is None:
            raise NoSuchInstructionProposal(proposal_id)
        return await self._view(proposal)

    async def accept(self, user_id: str, proposal_id: str, text: str | None = None) -> tuple[ProposalView, Bot]:
        """Write the new instructions (or the user's edit of them). On any refusal the card is open again."""
        proposal = await self._store.decide(user_id, proposal_id, "accepted")
        if proposal is None:
            await self._missing_or_closed(user_id, proposal_id)
        try:
            bot = await self._write(proposal, text)
        except BaseException:
            await self._store.decide(user_id, proposal_id, "open", expected="accepted")
            raise
        await self._changed(proposal)
        return await self._view(proposal), bot

    async def decline(self, user_id: str, proposal_id: str) -> ProposalView:
        proposal = await self._store.decide(user_id, proposal_id, "declined")
        if proposal is None:
            await self._missing_or_closed(user_id, proposal_id)
        await self._changed(proposal)
        return await self._view(proposal)

    async def _write(self, proposal: InstructionProposal, text: str | None) -> Bot:
        bot = await self._bots.get(proposal.user_id, proposal.bot_id)
        if bot is None or bot.instructions != proposal.payload.before:
            raise InstructionProposalRefused(STALE)
        new = text if text is not None else proposal.payload.after
        updated = await self._bots.update(proposal.user_id, bot.id, BotPatch(instructions=new))
        if updated is None:
            raise InstructionProposalRefused(STALE)
        return updated

    async def _view(self, proposal: InstructionProposal) -> ProposalView:
        bot = await self._bots.get(proposal.user_id, proposal.bot_id)
        stale = bot is None or bot.instructions != proposal.payload.before
        return ProposalView(proposal, line_diff(proposal.payload.before, proposal.payload.after), stale)

    async def _missing_or_closed(self, user_id: str, proposal_id: str):
        if await self._store.get(user_id, proposal_id) is None:
            raise NoSuchInstructionProposal(proposal_id)
        raise InstructionProposalClosed(NOT_OPEN)

    async def _post_card(self, proposal: InstructionProposal) -> None:
        body = json.dumps({"proposal_id": proposal.id})
        message = await self._card(proposal, proposal.thread_id, body)
        await self._store.set_message(proposal.user_id, proposal.id, message.id)
        main, _ = await self._talk.ensure_main_thread(proposal.user_id, proposal.bot_id)
        if main.id != proposal.thread_id:      # a routine's run log or a room: the bot's own chat shows it too
            await self._card(proposal, main.id, body)

    async def _card(self, proposal: InstructionProposal, thread_id: str, body: str):
        message = await self._talk.add_message(proposal.user_id, thread_id, "bot", body, tainted=proposal.tainted,
                                               kind=MESSAGE_KIND, author_bot_id=proposal.bot_id)
        await self._events.publish(proposal.user_id, {"type": "message", "thread_id": thread_id,
                                                      "message": message_out(message)})
        return message

    async def _changed(self, proposal: InstructionProposal) -> None:
        await self._events.publish(proposal.user_id, {"type": PROPOSALS_CHANGED, "bot_id": proposal.bot_id})
