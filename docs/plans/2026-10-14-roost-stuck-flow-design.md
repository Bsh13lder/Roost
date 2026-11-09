# Roost Stuck Flow (Piece A) — Design

**Status:** design approved in conversation on 2026-10-14; this file is the written record for review.
The task-by-task implementation plan follows in `docs/plans/2026-10-14-roost-stuck-flow.md`.

**Spec background:** `docs/specs/2026-10-12-roost-design.md` §5.6 (the stuck ladder), D7, and the
§7.4 vocabulary (Stuck, Take control / Give it back, Ask cards).

## Goal

A bot that hits a Cloudflare check, a login wall or a 2FA prompt stops cleanly, tells you, and lets
you clear the block in **its own window** with Take control. When you give it back, it carries on.
Your main Brave comes in only when **you** press "Use my main Brave" (the bot may suggest it). A
task that stays blocked is reported loudly, never finished with an empty result.

## Decisions (from the user, 2026-10-14)

- **D-A1.** First answer to a block is always the bot's own window: wait-and-reload, then Take
  control. If that works, the main Brave is never touched.
- **D-A2.** The main Brave is used only when the user asks, or the bot suggests it and the user
  says yes. Never on the bot's own.
- **D-A3.** Piece A ships first. In piece A, "Use my main Brave" only **opens** the URL there (no
  automation). Piece B — the bot drives the main Brave for one approved step — comes later, after a
  feasibility test (Chromium ≥136 may refuse a debug port on the default profile) and needs click /
  type tools that do not exist yet.
- **D-A4.** Piece B overrides the CLAUDE.md rule "never touch the user's main Brave" only for steps
  the user approves one at a time. Piece A does not change that rule: opening a URL with
  `open -a` is not touching the browser's profile, port or automation.
- **D-A5.** A stuck run **ends** and leaves a persisted Stuck card (not an in-memory wait, not a full
  parked run). Clearing the card queues a `card_answer` work item that continues the task.

## 1. Detecting a block

### HTTP status

`DeskBrowserPage` (roost/desk/browser.py) enables `Network` and records the main document's status
from `Network.responseReceived` (`type == "Document"`, the navigated frame). `PageText` gains
`status: int | None` (`None` when unknown, e.g. a `read_page` after the user navigated).

### The detector — `roost/desk/stuck.py`

A pure function `detect_block(page: PageText) -> Block | None`. `Block` is a frozen dataclass:
`reason: BlockReason`, `host: str`, `url: str`. Markers and thresholds live in `roost/constants.py`.

| Reason | Fires when |
|---|---|
| `challenge` | Title or text matches a challenge marker ("Just a moment", "Verify you are human", "Attention Required", "Checking your browser"), or the URL carries `__cf_chl`, or the AX text names an hCaptcha / reCAPTCHA frame. A 403/429 counts only together with one of these. |
| `login` | The AX tree has a password text field. |
| `code` | Text matches a 2FA marker ("verification code", "two-factor", "2-step", "enter the code"). |
| `refused` | Status 403 or 429 with no challenge marker. **Not a card** on first sight: the bot gets a "this site refused you" result and may try another way. A second `refused` on the same host in the same run becomes a card. |

The detector never clicks, never changes the user agent or fingerprint, never solves anything.

### The bot may ask — `ask_for_help`

A new tool `ask_for_help(reason: str, suggest_main_browser: bool = False)` for blocks the detector
cannot see (a payment or identity check, a site the bot judges unusable). Gate kind `read` (it
writes nothing the user owns; it only raises a card). `reason` is capped at
`STUCK_REASON_MAX_CHARS` and is shown as text, never HTML. At most one card per run: a second call
returns "You already asked for help in this run."

### Rung 1 — wait and reload

For `challenge` only: the tool runner waits `STUCK_CHALLENGE_WAIT_SECONDS` (8), reloads once in the
bot's own window, and runs the detector again. Clear → the call returns the page as normal and the
user never hears of it. `login` and `code` skip the wait.

## 2. The Stuck card and the run

### Schema v12 — `stuck_cards`

| Column | Notes |
|---|---|
| `id` | text id |
| `user_id`, `bot_id`, `thread_id` | plaintext ids |
| `work_item_id` | the item whose run stopped |
| `reason` | plaintext enum `challenge` · `login` · `code` · `refused` · `asked` |
| `url` | `enc:v2`, AAD `stuck_cards:url` |
| `note` | `enc:v2`, AAD `stuck_cards:note` (the bot's `ask_for_help` reason, or empty) |
| `request` | `enc:v2`, AAD `stuck_cards:request` (the original request text to continue) |
| `suggest_main_browser` | 0/1 |
| `tainted` | 0/1 (the run had read outside content) |
| `state` | `open` · `cleared` · `given_up` · `blocked` |
| `created_at`, `closed_at` | timestamps |

A partial unique index allows one `open` card per bot. Every query has `user_id` in its `WHERE`;
another user's card id gives 404.

### When a block is found (after rung 1)

1. The tool runner returns a `ToolOutcome` with a new `block: Block | None` field. The turn stops
   calling the model.
2. The runner opens the card (`roost/stuck/service.py`), posts the bot's chat line
   ("I'm stuck on example.com: a Cloudflare check. Take control to clear it, then give it back."),
   and settles the bot to **Stuck** instead of Resting.
3. An event `stuck_card` (card out-shape) goes over the EventHub. `web/src/lib/attention.ts` fires a
   page notification for `stuck`, like `asking_you`. (No web push exists; out of scope.)

While a card is open the bot still drains its queue and answers new messages. `_settle_status`
shows **Stuck** whenever the bot is idle with an open card.

### The card's buttons — routes in `roost/gateway/routes/stuck.py`

All have `CurrentUser`; mutating ones have `RequireOrigin`.

| Route | Effect |
|---|---|
| `GET /api/stuck` | the user's open cards (Home → My turn) |
| `POST /api/stuck/{id}/clear` | Give it back / Done: state `cleared`, releases any control hold, queues a `card_answer` item |
| `POST /api/stuck/{id}/give-up` | state `given_up`, bot says "OK, I stopped that task.", status Resting |
| `POST /api/stuck/{id}/open-in-main-browser` | see §3 |

Take control on the card is the existing `POST /api/bots/{id}/control`; the card's **Give it back**
calls `/clear`, which also performs the existing give-back.

### The continue item

`kind = card_answer`, same thread, body: "The user cleared the block on <host>. Read the page again
with read_page, then continue: <request>." (After a main-Brave step: "The user did this step in
their own browser. Read your own page again …".) `tainted` copies the card's flag, so the
tainted-write rule still holds.

### Rung 4 — blocked

If a continue run (one whose item is a `card_answer` from a card) hits a block on the **same host**,
no new card opens. The old card becomes `blocked`, and the bot posts: "Blocked: <host> keeps
stopping me. I didn't finish: <request>." Status settles to Resting. Never an empty result.

## 3. "Use my main Brave" (piece A: open only)

- Only the user's press starts it. With `suggest_main_browser`, the card says "The bot suggests doing
  this in your main Brave" and highlights the button.
- The card shows the full real URL. When `tainted`, it adds: "This link came from a web page the bot
  read. Check it before you open it."
- The gateway sends a signed `POST /main-browser/open {url}` to the keeper. The keeper accepts only
  `http`/`https`, runs the same `check_url` as the bot's browser, and calls an injected
  `MainBrowserOpener` that runs `["open", "-a", "Brave Browser", url]` (argument list, no shell).
  No debug port, no profile access, no automation. 400 for a refused URL; 503 when the keeper is
  down.
- The card then shows **Done, carry on** (`/clear`) and **Give up**.
- Tests use a fake opener; no test ever launches a real browser.

## 4. Files

**New:** `roost/desk/stuck.py`; `roost/stuck/{__init__,models,store,service}.py`;
`roost/gateway/routes/stuck.py`; `web/src/components/StuckCard.tsx` (+ test); fixture pages under
`tests/fixtures/pages/` (challenge, login, 2FA, 403, normal).

**Changed:** `roost/desk/__init__.py` (`PageText.status`), `roost/desk/browser.py` (status, reload),
`roost/talk/outcome.py` (`block`), `roost/talk/tool_runner.py` (detector + rung 1),
`roost/talk/tool_catalog.py` (`ask_for_help`), `roost/talk/runner.py` (end with card, Stuck settle,
rung 4), `roost/keeper/app.py` (`/main-browser/open`), `roost/desk/client.py`
(`KeeperClient.open_in_main_browser`), `roost/db/migrations.py` (v12), `roost/constants.py`,
`web/src/lib/attention.ts`, the chat message list and Home's My turn.

## 5. Testing

Tests first, ≥80% line coverage on new code, no real LLM, no real browser.

- **Unit:** the detector against each fixture page; the store (encryption, one-open-card index,
  user scoping); the service state machine (open → cleared / given_up / blocked).
- **Integration:** scripted model through challenge → wait → reload clears (no card); challenge
  stays → card → `/clear` → continue item → finishes; `/give-up`; second block on same host →
  `blocked`; `ask_for_help` twice in one run; another user's card → 404; `open-in-main-browser`
  calls the fake opener with the exact URL and refuses `file:` / `javascript:`.
- **E2E (Playwright):** a local fixture challenge page → Stuck card in chat → Take control → Give it
  back → bot continues.

## 6. Refinements after reading the code (2026-10-14)

These replace the matching lines above where they differ. Behavior the user approved is unchanged.

- **R1. How the block reaches the turn.** `ToolRunner.run` returns a string, not a `ToolOutcome`.
  The block is a public `ToolRunner.block: Block | None`, like `tainted` and `last_host`.
  `_run_steps` stops after the step that set it, and `TurnResult` gains `block`. Once a block is
  set, any later call in the same step returns `STUCK_NOT_PERFORMED_TEXT` without running.
- **R2. Signals the detector needs.** The AX text drops text boxes and frames, so `PageText` gains
  three defaulted fields: `status: int | None`, `password_field: bool` and `captcha_frame: bool`.
  `read_page` fills the last two with `DOM.getDocument` + `DOM.querySelectorAll`. This runs no
  page script, so `Runtime.evaluate` is still never sent.
- **R3. Fewer false alarms.**
  - **Thin page:** a page whose text is at most `STUCK_THIN_PAGE_CHARS` (1500) long.
  - **`challenge`:**
    - a challenge title marker or `__cf_chl` in the URL, at any length;
    - or challenge text markers or a visible captcha frame, but only on a thin page.
  - **`login`:** a password field, plus either a thin page or a login marker in the title or URL path.
  - **`code`:** 2FA text markers on a thin page.
  - **`refused`:** a 403 or 429 status with none of the above.
  - Invisible reCAPTCHA frames never count.
- **R4. Rung 1 repeats the same call.** After the wait it calls `open_page(url)` again, or
  `read_page()` again; it does not use `Page.reload`. That reuses the URL check, the status
  capture and the reconnect, and never reloads a `__cf_chl` address. If the user takes control
  during the wait, the repeat is skipped and the card opens straight away.
- **R5. Cards only in your own chat.**
  - **Chat runs:** a card opens only in a run made of your own messages and continue items
    (`message` / `card_answer`), outside rooms.
  - **Other runs (handoffs, rooms, routines):** the detector still runs rung 1. A block then comes
    back as a loud tool result: `Blocked: <host> shows <what>. You can't get past it in this task.
    Tell whoever asked that the site stopped you.` The model then answers with that, never with an
    empty result.
  - **`ask_for_help` outside chat runs** returns `Refused: you can ask for help only in your own
    chat with the user.`
- **R6. The continue item.**
  - A work item's body never reaches the model, so `/clear` first posts a `role="user"`,
    `kind="card_answer"` message: "I cleared the block on <host>. Read the page again and carry on
    with: <request>." After a main-Brave step it says "I did this step in my own browser".
  - Then it queues `WorkDraft(kind=card_answer, origin=ORIGIN_CARD, message_id=<that message>,
    link_scope=(card.url,), tainted=card.tainted)`. `card_answer` joins `_MODEL_KINDS`.
  - The card stores `answer_item_id`, so rung 4 can find it.
- **R7. The card in the chat** is a `kind="stuck"` bot message. Its body is the card as JSON, the
  same pattern as the Created card.
  - The web folds the card once its live state is no longer `open`.
  - Every state change publishes `{"type": "stuck_card", "card": …}`.
  - Home gets a small **My turn** list of open cards.
- **R8. Main Brave plumbing.** The keeper endpoint is `POST /desks/{bot_id}/main-browser/open`,
  so it has a bot id to validate and audit. The gateway reaches it through an `app.state.main_browser`
  seam: `KeeperMainBrowser` in keeper mode, `FakeMainBrowser` in fake mode. The gateway route runs
  `check_url` itself first and answers 400, because the keeper client turns every non-2xx into a 503.
  The card stores `main_opened`.
- **R9. Status.**
  - `TurnRunner.settle(user_id, bot_id)` is public. While the bot's drain task is running, it
    settles again once that task ends, so a status is never left stale.
  - It shows Stuck while a card is open, and runs after `/clear`, `/give-up` and "back on duty".
  - On boot, bots with an open card are set back to Stuck.
- **R10. Buttons.** Besides Take control, an open card has **Try again** (`/clear` without taking
  control), because a block sometimes clears by itself.
- **R11. E2E** uses a fake `login` page at `https://login.example/` served by `FakeDesk`'s
  fake-pages table, which avoids the 8-second wait. The challenge path is covered by the
  integration tests.

## 7. Decisions after the final review (2026-10-15)

- **R12. Rung 4 needs the same kind of block.** A continue run ends **Blocked** only when the new
  block has the same host **and** the same reason as its card, and the reason isn't `asked`. In
  every other case a new card opens and keeps the first request: a different wall on the same
  site (for example challenge, then sign-in), or the bot asking for help.
- **R13. After "Use my main Brave" → "Done, carry on" the bot does not re-check that page.** The
  continue line says: "I did this step in my own browser on {host}. Don't read that page again;
  carry on with the rest of: {request}. If you can't, tell me exactly what's left." A card the user
  finished in the main Brave never triggers rung 4. If the bot opens the page again anyway and it
  is still blocked, a new card opens.

## Out of scope

Piece B (the bot drives the main Brave); click / type tools; web push to the phone; per-site memory
("this site always needs a human"); mutual-TLS gating of Take control from the phone (spec §5.5).
