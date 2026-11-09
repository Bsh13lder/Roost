"""The ``declined`` signal (docs/plans/2026-10-31-roost-lessons.md §2, producer agent B), read at run end.

A card of this thread you said No to, parked on or answered by one of the run's items, is a signal: its host is the
frozen page resolution's (``act``), its action the step's floor or else its tool. Never the card's title, request,
crop or arguments. The card's own parked item, when it is your untainted message, also counts as your words for the
lesson (a run that reads your No is made of the card's answer, not of a message)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

from roost.approvals.models import ApprovalCard
from roost.lessons.constants import LESSON_DECLINED_CARDS_MAX
from roost.lessons.signals import LessonSignal
from roost.work.models import WorkItem, WorkKind


class DeclinedCards(Protocol):
    async def declined_for_items(self, user_id: str, thread_id: str,
                                 item_ids: Sequence[str]) -> tuple[ApprovalCard, ...]: ...

    async def card_for_answer(self, user_id: str, item_id: str) -> ApprovalCard | None: ...


class ItemReader(Protocol):
    async def get(self, user_id: str, item_id: str) -> WorkItem | None: ...


@dataclass(frozen=True)
class Declined:
    signals: tuple[LessonSignal, ...] = ()
    items: tuple[WorkItem, ...] = ()       # the cards' parked items, for your words


def declined_signal(card: ApprovalCard) -> LessonSignal:
    step = card.steps[0] if card.steps else None
    if step is None:
        return LessonSignal("declined", "", card.kind)
    host = step.act.get("host") if step.act is not None else None
    return LessonSignal("declined", host if isinstance(host, str) else "", step.floor or step.tool)


async def parked_items(queue: ItemReader | None, user_id: str, thread_id: str,
                        cards: Sequence[ApprovalCard]) -> tuple[WorkItem, ...]:
    if queue is None:
        return ()
    found = [await queue.get(user_id, c.work_item_id) for c in cards if c.work_item_id]
    return tuple(item for item in found if item is not None and item.thread_id == thread_id)


async def declined_in_run(cards: DeclinedCards | None, queue: ItemReader | None, user_id: str, thread_id: str,
                          items: Sequence[WorkItem]) -> Declined:
    if cards is None or not items:
        return Declined()
    found = (await cards.declined_for_items(user_id, thread_id, [item.id for item in items]))
    found = found[:LESSON_DECLINED_CARDS_MAX]
    if not found:
        return Declined()
    return Declined(tuple(declined_signal(c) for c in found), await parked_items(queue, user_id, thread_id, found))


async def answered_cards(cards: DeclinedCards | None, user_id: str,
                         items: Sequence[WorkItem]) -> tuple[ApprovalCard, ...]:
    """The cards this run's card answers answer: an approved re-run records its signals under the card's key, and
    the card's parked item holds your words."""
    if cards is None:
        return ()
    found = [await cards.card_for_answer(user_id, i.id) for i in items if i.kind is WorkKind.CARD_ANSWER]
    return tuple(card for card in found if card is not None)
