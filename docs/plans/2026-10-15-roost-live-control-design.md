# Roost Live Control (Take control, Grok-style) — Design

**Status:** design approved in conversation on 2026-10-15, section by section. This file is the
written record for review. The implementation plan comes next.

**Spec background:** `docs/specs/2026-10-12-roost-design.md` §5.5 ("take the wheel": live frames,
input events, secrets out of snapshots), D7 (each bot has its own headed Brave), §7.4 vocabulary
(Computer, Take control / Give it back, Vault: site logins). It builds on the stuck flow
(`docs/plans/2026-10-14-roost-stuck-flow-design.md`) and on S1.8 (screenshots and the in-memory
`ControlLock`, `roost/desk/control.py`).

## Why

Today **Take control** only pauses the bot. The Computer tab shows a screenshot every 3 s, and the
user can't click or type in it. To sign in, the user has to find the bot's own Brave window on the
Mac. The user tried this and couldn't act on the card. Grok's way, which this design copies, is a
live screen inside the app: the user types straight into the page, and the bot never sees what
they typed.

## Decisions (from the user, 2026-10-15)

- **L1.** **This Mac first.** Live control works only on a connection from `127.0.0.1`. The phone
  comes later, as its own step with secure pairing (spec §5.5, mTLS).
- **L2.** **What the user types stays secret.**
  - Keystrokes and frames are never logged, stored or put in events.
  - The bot never sees typed values.
  - **On Give it back, the user may tell the bot which account they used.** That optional label is
    kept per bot and site under **Vault: site logins**, so the bot remembers which account it is
    signed in with. Passwords are never stored.
- **L3.** **Bot windows stay out of the way.** They don't come to the front or steal focus. The
  Computer tab has **Show window on Mac** for when the user wants the real window.
- **L4.** **Approach A: a CDP screencast plus input events.** Only the bot's page is shared,
  through the bot's existing private CDP connection. There is no VNC, no screen sharing and no
  DevTools frontend; all three were rejected as unsafe.

## 1. What the user sees and does

- **Take control**, on a Stuck card or on the Computer tab, opens the **live screen**: the bot's
  page moving in real time (about 10 fps, at most 1280 px wide), filling the Computer view.
- **On the live screen the user can:**
  - click, double-click and scroll;
  - type (letters, digits, symbols, Enter, Tab, Backspace, Delete, the arrows, Escape);
  - paste with Cmd+V, which inserts the user's clipboard text into the page;
  - tick checkboxes, including Cloudflare's "I'm human".
- **A bar on top shows:**
  - the page address, read-only;
  - **Back** and **Reload**;
  - **Show window on Mac**;
  - **Give it back**.
- **Pop-ups are followed.** When the bot's page opens a pop-up or a new tab (for example "Sign in
  with Google"), the live screen switches to it. When it closes, the screen comes back to the bot's
  page.
- **Give it back** shows an optional field, **"Which account did you use?"**.
  - If the user fills it in, Roost saves `(bot, host, label)` in the Vault, and the bot receives
    "I signed in on {host} as {label}." in its continue line (stuck flow) or as a user message
    (Computer tab).
  - Empty means nothing is saved or said.
- **While the user holds control the bot waits**, as today: its browser calls are refused, never
  queued.

## 2. How it works

### The live connection

- **Route:** a WebSocket at `GET /api/bots/{id}/live`. It accepts only when **all** of these hold:
  - the request carries the user's session (`CurrentUser`);
  - the bot is the user's, otherwise it closes with 4404;
  - the `Origin` is Roost's own, otherwise 4403;
  - the peer address is `127.0.0.1` or `::1`, otherwise 4403 with the reason "Live control works
    only on this Mac for now.";
  - the user holds control of that bot, otherwise 4409 with "Take control first.".
- When the user gives control back, the socket closes with 4000 "Given back.". It also closes when
  control is released some other way.
- **Frames:**
  - The gateway sends `Page.startScreencast {format: "jpeg", quality: LIVE_JPEG_QUALITY,
    maxWidth: LIVE_MAX_WIDTH, maxHeight: LIVE_MAX_HEIGHT, everyNthFrame: 1}` on the page being
    shown.
  - Each `Page.screencastFrame` is acked (`Page.screencastFrameAck`) and forwarded to the socket
    as a binary JPEG.
  - Its metadata (device width and height, page scale, offsets) goes in a small JSON text frame
    just before it.
  - Frames are dropped when the socket is behind (one frame in flight), so latency stays low.
  - Frames are never written anywhere.
- **Input** arrives as JSON text frames from the browser, each validated with pydantic:
  - `{"t": "mouse", "kind": "down" | "up" | "move", "x", "y", "button", "clicks", "mods"}`
  - `{"t": "wheel", "x", "y", "dx", "dy"}`
  - `{"t": "key", "kind": "down" | "up", "key", "code", "mods"}`, where `key` must be in an
    allow-list of named keys or a single printable character
  - `{"t": "text", "text"}` for paste, capped at `LIVE_PASTE_MAX_CHARS`
  - `{"t": "nav", "action": "back" | "reload"}`
- **How input reaches the page:**
  - Coordinates are in frame space; the gateway maps them to CSS pixels using the frame metadata.
    Points outside the frame are dropped.
  - Events go to `Input.dispatchMouseEvent`, `Input.dispatchKeyEvent` or `Input.insertText`. Back
    and Reload use `Page.navigateToHistoryEntry` and `Page.reload`.
  - Input is rate-limited (`LIVE_INPUT_MAX_PER_SECOND`); anything over the limit is dropped.
  - **No input event is ever logged**: no audit row, no log line, no event.
- **The address bar** gets `{"t": "page", "url", "title"}` frames on every navigation of the shown
  target. The bot isn't running while the user holds control, so this shows the user nothing new.

### CDP plumbing

- `CdpClient` today only has one-shot `wait_event`. It gains a **subscription**:
  `subscribe(method, session_id) -> AsyncIterator[dict]`, with a bounded queue (drop-oldest). The
  screencast and target events use it.
- **Which page is shown:**
  - The shown target is the bot's own page.
  - When `Target.targetCreated` reports a new `page` whose `openerId` is the bot's page, the
    screencast moves to it (attach, `startScreencast`).
  - When `Target.targetDestroyed` fires for it, the screencast moves back.
  - `Target.setDiscoverTargets` is on only while live control runs.
- **Ending:** live control never opens a tab and never starts a closed browser. A sleeping
  computer gives the existing "asleep · Open it" state. When the socket closes, the screencast
  stops and the subscriptions end.

### Secrets

- The model's `read_page` text is built from AX roles that exclude text boxes. Chromium can also
  expose a field's value as a `StaticText` child of the box, so `read_page` must skip every node
  **inside** a `textbox`, `searchbox`, `combobox` or `spinbutton` as well. That way typed values
  never reach the bot. A test pins this with password and email fields that hold a value, using a
  realistic AX tree where the value appears as a child `StaticText`.
- Screenshots are pictures for the user only. They are never given to the model.
- **The Vault label**:
  - is the only typed-by-the-user text the bot ever gets;
  - is written by the user, so it is trusted text;
  - is stored `enc:v2`.

### Bot windows out of the way (L3)

- After the keeper starts a bot's Brave, the gateway (on its first CDP attach) sets the window
  aside with `Browser.getWindowForTarget` + `Browser.setWindowBounds`.
- **Spike first (Task 1):** check on the user's Mac whether a **minimised** Brave window keeps
  producing screencast frames, given the keeper's anti-throttling flags.
  - Yes → windows are minimised.
  - No → windows stay normal but are placed behind and out of the way. A launched Brave may
    still come to the front once on start; the plan records what the spike found.
- **Show window on Mac** (`POST /api/bots/{id}/window/show`) restores the window and brings it to
  the front with `Browser.setWindowBounds {windowState: "normal"}`.

### Vault: site logins

- **Schema** (the next free version after the projects hub) — table `site_logins`:
  - `id`, `user_id`, `bot_id` (cascade on bot delete), `host`;
  - `label`, `enc:v2` with AAD `site_logins:label`;
  - `created_at`, `updated_at`;
  - unique on `(user_id, bot_id, host)`.
- **Writing:** Give it back with a label upserts the row.
  - `POST /api/stuck/{id}/clear` and `DELETE /api/bots/{id}/control` gain an optional body
    `{"account": str | null}`, at most `SITE_LOGIN_LABEL_MAX_CHARS`.
- **The bot's prompt** gains a short trusted section: "You are signed in on: github.com (as work
  email), …". It lists that bot's rows, newest first, at most `SITE_LOGINS_IN_PROMPT`.
- **Profile:** the Computer tab lists the rows, each with **Forget**
  (`DELETE /api/bots/{id}/site-logins/{login_id}`).

## 3. Testing

- **Unit:**
  - the input mapping (every allowed key; mouse buttons and click counts; frame-to-CSS coordinate
    mapping; out-of-frame points dropped; disallowed keys refused);
  - the rate limit;
  - the subscription queue (bounded, drop-oldest, ends on close);
  - following a pop-up target and coming back.
- **Integration:**
  - the WebSocket accept rules (4404, 4403 for origin and for non-loopback, 4409 without control);
  - closing on give-back;
  - frames forwarded and acked against the fake CDP server;
  - inputs turning into the exact CDP calls;
  - **nothing logged**: caplog and the audit and event tables stay free of the typed text;
  - `read_page` never includes text-box values;
  - Vault upsert, the prompt line, Forget, and another user's row giving 404.
- **E2E (Playwright, fake desk):**
  - take control of a fake login page, type, and give it back with an account name;
  - the bot carries on, and the Vault shows the label.
  - The fake desk needs a scripted screencast; the plan defines it.
- **Manual, on the user's Mac:** the minimise spike, then one real sign-in together.

## Out of scope

- The phone, and secure pairing (mTLS).
- Dragging, file uploads and drag-and-drop.
- Several tabs side by side.
- The bot driving the user's main Brave (stuck flow piece B).
- Storing passwords or any secret beyond the account label.
- Click and type **tools for the bot**: this is the user's control, not the bot's.
