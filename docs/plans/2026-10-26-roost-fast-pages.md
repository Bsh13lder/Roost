# Fast pages: numbered controls, read the text, type in search (2026-10-26)

**Why.** Gela (Linux computer, WhatsApp Web) took about 100 steps and 6 minutes to find one appointment in one
chat. The audit showed: about 10 clicks on "Search or start a new chat" and no `type` of "Francis"; about 40 scrolls
of one or two notches, most followed by a screenshot; a PDF read by scrolling screenshots in the viewer; about 8
clicks refused with "Look first". The owner asked for the speed of browser-use style agents, inside Roost's own
computer-use layer and its gate.

## 1. What browser-use does (studied from the MIT wheel 0.13.11, never installed into Roost)

- **The page as numbered elements.** Each step its DOM serializer (`browser_use/dom/serializer/serializer.py`) walks
  the DOM, the accessibility tree and a DOM snapshot, keeps visible interactive elements and gives each a number:
  `[12]<button aria-label=Send />`, with the visible text between them. New elements since the last step get a `*`.
  Scroll containers are marked `|scroll element|` with "pages above / below", and an iframe's hidden content is
  hinted ("3 more elements below"). The numbers map to a selector map of backend node ids for that step only.
- **Actions by number.** `click(index)` (or a viewport point), `input(index, text, clear)` (focus, clear, type in one
  action), `scroll(down, pages, index)` (pages, not wheel notches, optionally inside one element),
  `send_keys`, `select_dropdown_option(index, text)`, `switch_tab`, `navigate`, `search`.
- **Read without looking.** `extract(query, start_from_char)` turns the whole page into markdown (scrolled-out text
  included) and pages through it; `search_page(pattern)` greps the page's text with context; `find_elements`.
- **Screenshots are optional** (`use_vision`: on, off or auto); the element list carries most steps.
- **Several actions per step**, stopped when the page changes. PDFs are downloaded and read as files.

## 2. What fits Roost and what doesn't

| browser-use | Roost |
|---|---|
| Numbered elements per step | **Fits.** `look` numbers its controls; the numbers live only in the runner, for the newest look. |
| Click / input by number | **Fits, re-resolved.** The number names a backend node from the newest look; the runner reads that node again on the live page, checks it is still the same control (kind, words, tag, link host, dialog) and in view, and builds the usual `ActResolution`. `judge_act` and the hard floor judge it exactly as before. A stale number is refused with "Look again". |
| `input` focuses and types in one action | **Fits.** `type` with `index` clicks a text box first (a text box click is always browsing), checks the focus landed there, then types. The typing is judged as today. |
| New state after every action | **Fits as a glance.** An act's result now ends with a text-only glance: the numbered controls, areas and a short page text, read after the page settled. It counts as the check R1 asks for, so the next act needs no separate `look` (the glance is untrusted page text and taints the run, like a look). |
| `extract` / `search_page` | **Fits as `read_text`.** The accessibility text of the whole page or of one numbered area (a list, a grid, a dialog, the message pane), scrolled-out text included where the DOM holds it, escaped in `<untrusted_page>`, with a character budget, a `start` cursor and an optional `find`. |
| Optional screenshots | **Fits.** `look` takes `picture: false`. |
| Scroll by pages / inside an element | **Fits.** `scroll` takes up to 25 notches (default 5) and an `area`. |
| PDFs | **Fits as `read_pdf`.** The bot's own Chromium fetches the PDF (`Network.loadNetworkResource`, its cookies and egress), only for an address on the run's fence; the bytes stay in memory, pypdf/pdfplumber (BSD/MIT, already dependencies) read the text with size, page and time caps. No file is written; no image change. |
| Several actions per model step | **Doesn't fit.** One screen action per model step stays (a blind chain can't happen); the glance removes most extra steps anyway. |
| Driving the browser itself, `navigate`, uploads, `evaluate` JS | **Doesn't fit.** Roost's input goes through `roost-input` and the gate; the page is read only through Chromium's own computations (AX tree, DOM, layout), never a page script. browser-use is not a dependency. |

## 3. Slices

1. **This write-up.**
2. **Numbered controls.** `look` lists `[n] kind "words" at (x, y)`, with `· focused` and `· commits` marks, and
   `PageMarks` (`roost/computer_use/marks.py`) keeps the newest numbering. `click`, `type` and `press_key` take
   `index`. Acts end with the glance (`after_glance`), which also renumbers. A number from an older look, a control
   that changed, went out of view or a page that moved to another address is refused: "Look again".
3. **Read text.** `read_text(area?, start?, find?)`; areas are numbered in every look.
4. **Typing into search boxes.** Cause found in the code: WhatsApp's box is a plain `textbox` (or a contenteditable)
   with no `role=searchbox`, no `type=search`, no search landmark and no GET form, so `is_search_box` said no and the
   model's own words would have needed a card; `type` also demanded a `source`, so own search words had none to name,
   and a look never said which box had focus (boxes are greyed out). Fix: `PageTarget.search_named` (a one-line box
   whose label or placeholder says search / buscar / find / filter) takes the model's own short words with no card;
   `source` is optional; a look marks the focused control. **Enter in such a box is unchanged** (only a structural
   search box makes Enter browsing), so a box merely *named* "Search" can't send anything without a card.
5. **PDFs.** `read_pdf(index?, start?)`.
6. **Fewer screenshots, bigger scrolls.** `look(picture=false)`, the glance clears the stale picture, and
   `CU_SCROLL_MAX_NOTCHES` 25 (default 5), sent as inputs of at most `CU_SCROLL_NOTCHES_PER_INPUT` 10, which is
   what the keeper and `roost-input` already take (no image change), plus `scroll(area=n)`. `CU_BLIND_SCROLLS_MAX`
   stays 3 (a scroll still returns no glance) and its sentence points to `read_text`.

## 3a. As built (2026-10-26)

- A card's approved re-run names the stored control (`pinned`), so an act aimed by number still re-runs on exactly
  that control; its result gets no glance (its line goes under the card, never page text).
- `read_pdf` fetches only an address `check_url` accepts, on the current page's own host or the run's fence. Untested
  against a live Chromium: `Network.loadNetworkResource` on the bot's page; if it is refused there, the bot gets
  "My browser couldn't fetch that PDF".
- `blob:` PDFs (2026-10-26, owner request: WhatsApp Web's in-chat documents): a link's `blob:` address, or a tab
  that shows one, is read inside the page that owns it (`roost/desk/blob_fetch.py`): an isolated world
  `roost-blob`, `Runtime.evaluate` with `fetch(blob)` → size checked against `CU_PDF_MAX_BYTES` in the page before
  any copy → base64 (`CU_BLOB_B64_CHUNK`) → returned by value, the base64 length checked again before decoding, into
  memory only; then the same capped pdfplumber path, escaped `<untrusted_page>` text and taint. Only a blob whose
  origin is the current page's own (`page_origin`); another origin's blob ("belongs to a page on …"), a blob with no
  http(s) origin and any other scheme are refused. The fake chats page has a `Receta.pdf` blob link
  (`tests/test_cu_read_pdf_blob.py`). Untested against live WhatsApp Web: a revoked blob gives "My browser couldn't
  fetch that PDF".
- The Francis run on the scripted page (`tests/test_cu_search_box.py`): look, type into search, click the chat,
  read_text with find: four steps.

The prompt and tool specs say: type into search boxes instead of scrolling lists, read text instead of scrolling to
read, aim by number, take a picture only for pictures.

## 4. What did not change

The hard floor, the fence, the commit test, owner words, auto-review, password and file boxes, one action per
step, the step and look budgets, Take control. Every act is still resolved on the live page and judged on that.

## 5. Paste typing (owner, 2026-11-01)

"Make it smooth like Grok": `type` no longer goes key by key. The runner selects what the box holds, then
puts the whole text in at once with CDP `Input.insertText` on the bot's own page (`roost/desk/box_text.py`
`paste_text`, `PageDriver.paste_text`, `CheckedTyping._put_text`), after checking in the `roost-box` isolated
world that the resolved box is the focused one. `insertText` sends no key events, so a line break (`\n`) or a tab
in the text is text: a new line in a `<textarea>` or a content-editable box, never Enter or Tab. A one-line
`<input>` refuses text with a line break and nothing goes in ("That box takes one line ..."). Only when the page
can't take a paste (another frame, focus moved) does one-line text fall back to roost-input's xdotool typing;
text with a line break or a tab never does, and on the desktop (another app in front) it is refused. Any other
control character, `\r` included, is refused by `TypeIn`. The cap is `CU_TYPE_MAX_CHARS = 5000` (Upwork's cover
letter limit), mirrored in the keeper and `roost_input.py`; `CU_BOX_TEXT_MAX_CHARS` stays twice that. The
read-back check `same_text` compares multi-line text line by line (blank lines and `\r\n` forgiven, a lost or
extra break not); one-line text compares as before. Your hands are checked before a paste (it skips the
keeper), and the text is never logged, audited or put in an event: the audit keeps its length and keyed hash.
