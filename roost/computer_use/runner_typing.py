"""Typing that replaces and is checked, and the draft a Send card shows (owner, 2026-10-27).

Gela's Russian message went in after an old Spanish draft (typing only ever added), and one letter was lost on the way.
So ``type`` first selects whatever the box holds, types over it, then reads the box back (``roost/desk/box_text.py``);
when the box doesn't hold the text, it types once more, and if it still doesn't, the bot is told not to send it.
A click or key that sends gets the message as its box holds it on the card, and Yes sends only that same text. Owner,
2026-11-03: every box the run typed into shows on the Send card as a row named by the box's label (a cover letter, a
milestone, an amount), and Yes sends only while every one still holds its text.

Paste typing (owner, 2026-11-01, "make it smooth like Grok"): the text goes into the focused box all at once
(``page.paste_text``: CDP ``Input.insertText``), line breaks and tabs included, so a 1,200-character cover letter
takes a moment instead of 40 s. A one-line box refuses text with line breaks and nothing is typed. Only when the
page can't take a paste (the box sits in another frame, focus moved) does one-line text go key by key through
roost-input as before; text with a line break or a tab never does.

``ComputerUse`` (``roost/computer_use/runner.py``) mixes this in: every attribute it reads is the runner's."""

from __future__ import annotations

from dataclasses import replace

from roost.approvals.models import DRAFT_DEFAULT_LABEL, DraftBox
from roost.approvals.send_card import SEND_CLASSES
from roost.computer_use.page_copy import copied_from_page, keep_seen
from roost.computer_use.commit_words import takes_search_words
from roost.computer_use.models import ActResolution, PageTarget, TextSourceIn
from roost.computer_use.text_source import ApprovedTexts, load_approved_texts, text_is_approved
from roost.constants import CU_DRAFT_BOXES_MAX, CU_DRAFT_LABEL_MAX_CHARS, CU_TYPE_TEXT_CONTROLS, CU_TYPE_TRIES
from roost.desk import ScreenInput
from roost.desk.box_text import NO_PASTE, ONE_LINE, PASTED, same_text

LINE_BREAKS_ONE_LINE_TEXT = ("That box takes one line, so I typed nothing: your text has line breaks. Type it as one "
                             "line, or find the page's bigger box for it.")
NO_PASTE_TEXT = ("I couldn't put the text into that box at once, and text with line breaks or tabs is never typed "
                 "key by key (a line break would press Enter). Click the box and type again, type it as one line, "
                 "or ask_for_help.")
NOTHING_TYPED = frozenset({LINE_BREAKS_ONE_LINE_TEXT, NO_PASTE_TEXT})    # notes that mean nothing went in
TYPED_WRONG_TEXT = ("Careful: the box doesn't hold exactly what you typed, even after typing it again (it holds "
                    "{held} characters, you meant {meant}). Don't send it. Look at the box; type the text again "
                    "(typing replaces what the box holds), or ask_for_help.")
DRAFT_CHANGED_TEXT = ("The text in '{label}' changed after the card was made, so I didn't send it. Look at the page, "
                      "and ask again so the card shows the text as it is now.")


class CheckedTyping:
    """Mixed into ``ComputerUse``."""

    _typed_boxes: tuple[DraftBox, ...]         # the boxes this run typed into, newest last (never a secret box)
    _seen: str                                 # the page text this run was shown (page_copy.py), memory only

    async def _type_checked(self, page, r: ActResolution, text: str, window, x: int, y: int) -> str:
        """Put ``text`` over what the box holds and read it back. "" when it holds the text (or can't be read),
        else the note for the bot. The box's text stays in memory."""
        node = r.target.node_id if r.target is not None else None
        held: str | None = None
        for _ in range(CU_TYPE_TRIES):
            if node is not None and await page.box_text(node):
                await page.select_box(node)
            refused = await self._put_text(page, node, text, window, x, y)
            if refused:
                return refused
            if node is None:
                return ""
            held = await page.box_text(node)
            if held is None or same_text(held, text):
                return ""
        return TYPED_WRONG_TEXT.format(held=len(held or ""), meant=len(text))

    async def _put_text(self, page, node: int | None, text: str, window, x: int, y: int) -> str:
        """Paste the whole text into the box (owner, 2026-11-01); when the page can't take a paste, type one-line
        text key by key through roost-input instead. "" when it went in, else the note (nothing was sent)."""
        self._require_hands()                  # a paste skips the keeper, so your hands are checked here
        sent_before, self._input_sent = self._input_sent, True     # a paste that dies on the way may have gone in
        status = await page.paste_text(node, text) if node is not None else NO_PASTE
        if status == PASTED:
            await self._events.publish(self._run.user_id, {
                "type": "computer_pointer", "bot_id": self._run.bot_id, "x": x, "y": y, "kind": "type",
            })
            return ""
        self._input_sent = sent_before
        if status == ONE_LINE:
            return LINE_BREAKS_ONE_LINE_TEXT
        if any(char in CU_TYPE_TEXT_CONTROLS for char in text):
            return NO_PASTE_TEXT               # a line break or a tab as a key would press Enter or Tab
        await self._send(ScreenInput("type", text=text, window=window), x, y, "type")
        return ""

    def _note_typed(self, r: ActResolution, text: str) -> None:
        """Keep the box this act typed into (never a secret or search box) for the Send card, newest last."""
        target = r.target
        if target is None or target.secret_field or takes_search_words(target):
            return
        box = DraftBox(_label(target), text, target.node_id, r.text_ok is True)
        kept = tuple(old for old in self._typed_boxes if old.node != box.node)
        self._typed_boxes = (*kept, box)[-CU_DRAFT_BOXES_MAX:]

    async def _drafts(self, r: ActResolution) -> tuple[DraftBox, ...]:
        """What a click or key would send: every box this run typed into that holds text now, else the focused box.
        A box is yours only when its text now is your own words (your message or an answered card)."""
        if r.tool == "type":
            return ()                          # a typing card shows its own Text row
        page = self._desk.page()
        boxes = self._typed_boxes or await self._focused_box(page)
        held: list[DraftBox] = []
        for box in boxes:
            text = await page.box_text(box.node) if box.node is not None else None
            if text and text.strip():
                held.append(replace(box, text=text.strip()))
        if not held:
            return ()
        texts = await load_approved_texts(self._run.config, self._run.user_id, self._run.thread_id or "", ())
        return tuple(replace(box, yours=_your_words(box.text, texts)) for box in held)

    @staticmethod
    async def _focused_box(page) -> tuple[DraftBox, ...]:
        focused: PageTarget | None = await page.focused()
        if focused is None or not focused.editable or focused.secret_field:
            return ()
        return (DraftBox(_label(focused), "", focused.node_id),)

    def _note_seen(self, text: str) -> None:
        """Page text that reached the model, minus what this run typed (for the card's mark, page_copy.py)."""
        self._seen = keep_seen(self._seen, text, (box.text for box in self._typed_boxes))

    def _text_basis(self, r: ActResolution, typed: str, drafts: tuple[DraftBox, ...], tainted: bool) -> bool:
        """A card's "Based on outside content" mark: for typing and a Send, only when its text came from a page
        (owner, 2026-11-03); any other card keeps the run's taint or its use of the screen."""
        if r.tool == "type":
            return copied_from_page((typed,), self._seen)
        if r.commit in SEND_CLASSES:
            return copied_from_page((box.text for box in drafts), self._seen)
        return tainted or self.state.used_screen

    async def _drafts_still(self, drafts: tuple[DraftBox, ...]) -> str:
        """On Yes: "" when every box still holds the text the card showed, else the label of the first that doesn't."""
        page = self._desk.page()
        for box in drafts:
            if box.node is None:
                continue
            now = await page.box_text(box.node)
            if now is None or not same_text(now, box.text):
                return box.label
        return ""


def _label(target: PageTarget) -> str:
    return " ".join(target.text.split())[:CU_DRAFT_LABEL_MAX_CHARS] or DRAFT_DEFAULT_LABEL


_SOURCES = (TextSourceIn.model_validate({"from": "message"}), TextSourceIn.model_validate({"from": "card"}))


def _your_words(text: str, texts: ApprovedTexts) -> bool:
    return any(text_is_approved(text, source, texts) for source in _SOURCES)
