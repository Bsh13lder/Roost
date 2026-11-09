# Leftovers round (owner, 2026-10-25)

Goal: close what the last rounds left open, and prove the bot's browser works end to end again.
The owner: "add functionality what we had left if you tested and fixed browser problems what was before".

## Tracks

- **L1. Web: the computer card stays.** Like the phone (1.0.11): when a run ends, the newest computer run's card
  stays in the chat with its last screen and Open screen; a resting computer shows Wake. Older runs fold as today.
- **L2. Take control from a phone's browser.** Over Tailscale the web says "Taking control works from this Mac only."
  Allow it from any signed-in browser the gateway accepts (the origin rules stay), with touch working on noVNC.
- **L3. Phone: the kept card survives a restart.** After the app restarts, the chat still shows the newest
  computer run's card (from the server's snapshot or the chat's history, never a picture stored on the phone).
- **L4. Phone task bar: paste many.** Pasting several lines offers to add them as separate tasks, as the web does.
- **L5. Phone: narrow pickers.** The task bar's Date/Project/Priority row never overflows on a 320 dp phone.
- **L6. Dead code.** The old phone `TaskRow` (no longer used) goes.
- **L7. Browser health.** A live check with Gela (test chat): open, look, click, scroll, tabs on WhatsApp Web and a
  plain site; fix what fails. Old CDP "Session with given id not found" errors on a stale tab are handled quietly.

## Not changed

"Continue" inside a dialog still asks every time (hard floor, needs the owner's words to relax).

## Found and fixed in L7 (2026-10-25)

- **Clicks under a see-through layer.** WhatsApp lays a `pointer-events: none` span over its filter tabs. The
  covering check hit-tested with `ignorePointerEventsNone: True`, so it hit that layer and called the tab covered;
  two "misses" made a Stuck card. The hit test now reaches what a real click reaches (`False`,
  `roost/desk/page_targets.py` `_hit`), for `covering` and `node_at` alike.
- **Pop-ups clear themselves (owner: "if he need accept continue or reject cookies or something that he should do
  automatically").** A button whose whole label is a dismiss word (`DISMISS_WORDS` in
  `roost/computer_use/commit_words.py`: OK, Got it, Not now, Close, Skip, Continue, Entendido, Ahora no…, and icon
  names like "ic-close") is
  browsing, so it runs with no card. A label that also says an action ("OK, delete") and a POST form's submit
  still ask. Cookie banners: Reject / Only necessary already run freely (`consent`); Accept all still asks.
- **Chat rows are clickable.** WhatsApp's chats are focusable `gridcell`s, which no control kind covered, so a
  click on a chat found nothing and missed twice. A focusable `row`, `gridcell` or `treeitem` is now the kind `row`
  (`roost/desk/page_targets.py`, `CU_TARGET_KINDS`), browsing unless its leading words say an action; a plain
  table's rows and cells stay words.
- **Gela's Browsing actions** is "Just do it" (owner, 2026-10-25).
- **Your message shows on every screen.** `POST /api/threads/{id}/messages` publishes your stored message as a
  `message` frame, so a message sent from the Mac shows on the phone at once and the other way round (both keep
  it once, by id; phone alerts only fire for a bot's message).
- **Short replies.** Every run's instructions carry `LENGTH_RULE` (`roost/talk/chat_feel.py`): the answer first,
  a few short lines, lists of at most five, more only when the user asks for detail.
- **Viewers and keys (Gela's Francis run).** Escape, Tab, the arrows, Page Up/Down, Home and End are browsing even
  with nothing focused (`_MOVE_KEYS`); a short label that opens something to look at ("Open picture", "Ver foto",
  `VIEW_WORDS`, at most four words, no account) is browsing; a fourth scroll in a row without a look is refused
  with `BLIND_SCROLL_TEXT` (`CU_BLIND_SCROLLS_MAX` = 3); the screen prompt tells the bot to close viewers itself
  and go back once it has what it came for.
- **Back.** `press_key` takes `Back` (`XF86Back`, the browser's back, no modifier; `roost-input`'s keysym list
  gained it, so the computer image is rebuilt). Moving keys are browsing except inside a cross-origin frame, and
  Enter on no focused control still asks (a page may listen for Enter on a whole dialog).

## Chat mode pill and auto-review (owner, 2026-10-25)

The owner said "Yes" to a chat button "like claude auto plan accept actions", on the condition that paying stays
safe.

- **The pill.** Beside the composer in a Linux bot's 1:1 chat (web `web/src/components/chat/ChatModePill.tsx`, phone
  `mobile/lib/chat/chat_mode_pill.dart`), one tap opens three modes with a line each. The Info tab's Browsing actions row
  shows the same three (`web/src/lib/chatMode.ts` is shared by both on the web):
  - **Ask me**: the `browsing` topic is on, so every ordinary click asks.
  - **Just browse**: `browsing` off (the old "Just do it"); a button Roost can't read still asks.
  - **Full auto**: `browsing` off and the bot's `auto_review` on.
  A mode is one `PUT /api/bots/{id}/approval` with `ask_topics` and the optional `auto_review` (left out, the
  stored value stays; another user's bot is 404). Schema v36 adds `bots.auto_review INTEGER NOT NULL DEFAULT 0`;
  the bot's wire shape carries `approval.auto_review`.
- **The reviewer.** In Full auto, a click or key on the page whose floor is `commit_click` and whose commit class
  is exactly `unknown` goes to a reviewer instead of the Ask card (`roost/auto_review/`): Fable 5.1 on the worker,
  W2's pattern (`roost/owner_words/check.py`). It reads, as escaped data, your newest own message in this chat, the
  host, the page title, the control's label, visible text, kind and dialog, the bot's `expect`, and the button's
  crop as a picture. Only an exact `safe` lets it run (verdict `do`, reason `auto_review`, audited like every
  decision); any other reply, no request, an error or a timeout is the usual Ask card. The chat's step line ends
  with "(auto-checked)". The scripted worker answers `safe` when your request names one of the control's words.
- **What never changes.** Paying, sending, deleting, account changes, accepting and submitting always ask; so do
  typed text, new sites, consent boxes, cross-origin frames, covered controls, password and file boxes. Only your
  own chat is reviewed (a run of your messages or card answers, outside rooms); routines, handoffs, rooms and
  card-less runs never are, and their asks stay what they were.

## Remember after web content (owner, 2026-10-25)

Gela's reminder pattern was never saved: its chat's last replies read WhatsApp, so `remember` was refused, and the
Remember it line it got instead was web-only. The owner: "I want better he saves normally, if tap cancel and show
what he is saving".

- **Saved with Undo.** In a run of your own new message that has read no new outside content yet (W7's
  site-fresh run: 1:1, cards possible), `remember` runs even when the chat's older history is tainted (gate reason
  `fresh_remember`). The memory is saved clean and the chat shows "Remembered: …" with Undo. Once the run reads a
  page, a search or any other outside content, `remember` is refused again and posts the Remember it line.
- **Plain words.** A refused `remember` tells the bot to say it is not saved and that you can tap Remember it
  (`OFFERED_TOOL_TEXT`), never that it saved it.
- **The phone.** The chat shows the "Not remembered: … · Remember it" line (`MemoryOfferLine`), and What I remember
  has Edit beside Forget (`PATCH /api/memories/{id}`).

## Fresh start, and a dropped browser socket (owner, 2026-10-25)

Every reply in Gela's chat read "from web content": its last 12 messages held WhatsApp replies, so each new run
started tainted and its reply kept the chain going. The owner chose a Fresh start that keeps the context
reachable ("it can see summary if necessary").

- **Fresh start** in the chat's ⋯ menu (web and phone) posts a `fresh_start` line (role `system`, never replayed;
  `POST /api/threads/{id}/fresh-start`, another user's thread is 404). `_age_taint` ages every row before the
  newest such line as if it were older than `CHAT_TAINT_KEEP`: its text reaches the model only as the
  placeholder, which names `search_chat`, and it no longer taints the run. Nothing is deleted; reading the hidden
  text back with `search_chat` taints only that run. A summary of web content would still be web content, so none
  is made.
- **A closed socket.** When the relay closed Gela's CDP socket (4503) mid-run, `CdpClient.send` raised websockets'
  `ConnectionClosedError`, which no caller catches, and the run ended with "Something went wrong on my side". It now
  raises `CdpClientError`, which the screen loop turns into "the browser didn't answer".
