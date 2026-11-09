"""The sentences the screen loop tells the bot (``roost/computer_use/runner.py`` and its parts)."""

from __future__ import annotations

from types import MappingProxyType

from roost.auto_review.constants import AUTO_REVIEW_MARK
from roost.computer_use import desktop
from roost.constants import CU_BLIND_SCROLLS_MAX

NO_SCREEN_TEXT = "My computer's screen isn't available right now."
GUARDS_TEXT = "I couldn't set up my browser's safety guards, so I didn't touch anything."
ASLEEP_TEXT = "My computer is asleep. Ask the user to open it on my Profile."
WAKING_LINE = "Waking my computer"
WOKE_LOOK_FIRST_TEXT = "My computer was asleep, so I woke it. Nothing was clicked or typed. Look first."
CHANGED_TEXT = "The page changed after you said yes, so I didn't click. I'll look again."
MOVED_TEXT = "Something moved under the pointer; I didn't click."
FOCUS_MOVED_TEXT = "The focus moved to another control before I could send that, so I didn't. Look again."
BLIND_SCROLL_TEXT = (f"Look first: you scrolled {CU_BLIND_SCROLLS_MAX} times without looking. Look to see where you "
                     "are; if the page didn't move, scrolling won't help (try another way, or press Escape). To "
                     "read a chat, a list or a long page, use read_text instead of scrolling.")
SCROLLED_TEXT = ("Scrolled {direction}. Look before your next click (read_text reads text without scrolling; "
                 "look with picture=false is enough unless you need to see images).")
AREA_OFF_SCREEN_TEXT = "Area {index} isn't on the screen, so I didn't scroll. Look again."
MISS_TEXT = ("I couldn't find {aim} on the page, so I didn't touch it. Look again and aim another way: a number from "
             "the look, or a point on its picture (x and y). If a pop-up covers it, press Escape or close it; if it "
             "is off screen, scroll; read_text finds its words.")
COVERED_TEXT = ("Something covers {label} (dialog \"{dialog}\"), so I didn't touch it. {how} Then click {label} "
                "again. Don't give up on the site.")
# Owner, 2026-11-05: how to close the covering dialog; these acts need no look first (session.closes_cover).
CLOSE_WITH_TEXT = "Close that dialog first, no look needed: click its button {closers}, or press_key Escape."
CLOSE_UNKNOWN_TEXT = ("Close that dialog first: press_key Escape (no look needed), or look and click the dialog's own "
                      "close, accept or reject button (Close, X, Cerrar, Accept or Reject cookies, Done).")
# A click at a point where nothing clickable is (owner, 2026-11-05: aim by a look's number instead).
POINT_MISS_TEXT = ("Nothing I can click is at ({x}, {y}), so I didn't touch it.{near} Look (look with picture=false "
                   "lists the page's controls with numbers) and click by index instead of a point.")
POINT_NEAR_TEXT = " Nearest control in your newest look: [{index}] {kind} '{label}' at ({cx}, {cy})."
CHECK_TEXT = "Check the confirmation before you say it's done; then say it in a few words."
HELD_TEXT = "You have my computer now, so I didn't touch it."
BAD_ARGS_TEXT = "Refused: {error}"
MISS_NOTE = "I tried several times and still couldn't use {aim} on {host}. Next: take control and do it, or tell me what to click."
BUDGET_NOTE = "I used this job's step budget on {host}. Next: say continue to carry on, or take control and finish it."
BLOCKED_NOTE = "The page tried to go to {host}, which is not one of this job's sites. Click its link again to ask."
POPUP_NOTE = "A new window opened and I closed it: {url}"
YOU_ASKED_MARK = "(you asked)"          # W2: the step line of an act your own message asked for
# The step line's mark for an act that ran without a card, by its verdict's reason (W2 and Full auto).
STEP_MARKS = {"owner_words": YOU_ASKED_MARK, "auto_review": AUTO_REVIEW_MARK}
KEPT_TAB_NOTE = "A new tab opened: {host}. Use list_tabs and switch_tab to work in it."
# Owner, 2026-11-01: a list's popup address (Upwork's /nx/search/jobs/details/~ID) shows a server error on its own.
PLAIN_ADDRESS_NOTE = ("This address opens only inside the site's list and may show an error on its own. To read the "
                      "item, open_page {url}")
APPLY_FORM_NOTE = "To apply, open_page {url} opens the apply form directly."
CHOOSER_NOTE = "The page asked for a file; I don't upload files."
BROWSER_SILENT_TEXT = "My browser didn't answer, so I didn't touch anything. Try again in a moment."
# The browser went silent after an input went out (2026-10-27): it may have run, so it is never sent again.
SENT_THEN_SILENT_TEXT = ("I sent the {what}, but my browser didn't answer afterwards, so I can't tell what it did. "
                         "Look to check before you do anything else.")
SENT_WHAT = MappingProxyType({"click": "click", "type": "typing", "press_key": "key"})
_INPUT_WORDS = MappingProxyType({
    "held": HELD_TEXT,
    "not_chromium": "I couldn't bring my browser window up, so I didn't touch anything.",
    "outside": "That point is outside my browser's page, so I didn't touch it.",
    "too_fast": "My computer asked me to slow down. Look, then try again.",
    "in_browser": desktop.IN_BROWSER_TEXT,
})
# Fast pages (docs/plans/2026-10-26-roost-fast-pages.md): an act aimed by a look's number.
NO_MARK_TEXT = "Your newest look has no control [{index}]. Look again and use a number from it."
STALE_MARK_TEXT = ("The page changed since your look: [{index}] is not the same control any more (or it is out of "
                   "view), so I didn't touch it. Look again.")
INDEX_KEY_TEXT = "press_key with an index needs a text box; click other controls instead."
NO_AREA_TEXT = "Your newest look lists no area {index}. Look again and use an area number from it."
STALE_AREA_TEXT = "Area {index} is gone from the page since your look. Look again."
READ_DESKTOP_TEXT = "Another app is in front, so there is no page to read. open_app browser first."
PDF_NOT_A_LINK_TEXT = "That number is not a link, so there is no PDF to read there. Give a link's number from your look."
PDF_NO_ADDRESS_TEXT = ("This PDF has no address I can read (only a web address, or a blob: address of the page you are "
                       "on, works). Open it from a link, or ask the user to send it to you.")
PDF_BLOB_OFF_SITE_TEXT = "That PDF belongs to a page on {host}, not the page you are on, so I didn't read it."
PDF_OFF_SITE_TEXT = "That PDF is on {host}, which is not one of this job's sites, so I didn't fetch it."
PDF_NOT_PDF_TEXT = "That address did not give a PDF (perhaps a sign-in page), so there is nothing to read."
PDF_TOO_BIG_TEXT = "That PDF is too large for me to read here."
PDF_FAILED_TEXT = "My browser couldn't fetch that PDF ({why})."
PDF_UNREADABLE_TEXT = "I fetched the PDF but couldn't read its text ({why}). It may be scanned pictures: look at it instead."
