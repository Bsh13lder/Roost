# Roost Computers C3, the computer-use loop: Design

**Status:** DRAFT, 2026-10-22. The user pulled this into v1 on 2026-10-22. §12 lists the open points.

**Goal:** a bot on its own Linux computer sees the page in its browser and clicks, types, presses keys and scrolls
there itself, like a person, through real X input. You watch it live, with a ring where it clicks. Clicks that
spend, send, submit, accept, delete or publish always wait for your Yes on a card that shows the button.

**Binding inputs:** `2026-10-20-roost-computers-2-design.md`, mainly its addenda "lessons from a real agent run" and
"computer-use loop rules" R1–R10 (cited below as R1…R10); C1/C2 (`2026-10-20-roost-computers-c1-c2.md`; C1 is built,
C2 Take control is being built); the approval modes (`roost/approvals/`: verdicts, hard floor, cards with full
argument rows, topic switches, Posting locked to ask); the desk (`open_page`, `read_page`, the stuck detector,
`ControlLock`); the keeper's CDP and VNC relays; the `roost-computer` image; and `roost-egress`.

**Renumbering:** this C3 replaces the design's C3 (terminal) and C4's click and type (§12.3). Design §4's "no desktop
click and type now" and "screenshots never to the model" are **reversed, for computer use only** (§2, §3).

## 1. Scope

**In:** Linux-computer bots only (`bots.computer = 'linux'`; Mac Brave has no safe OS input), acting only on the page
in the computer's Chromium window, never the desktop, taskbar, address bar or xterm. **Out (v1):** downloads and
uploads, drag and drop, hover-only menus, the right button, password and one-time-code boxes, the clipboard, tabs the
bot opens itself, desktop apps.

## 2. Tools (in the catalog; no name contains "control", no description contains " role")

| Tool | Arguments | Gate kind | What it does |
|---|---|---|---|
| `look` | — | `read`, taints | A JPEG of the page area (≤1280×800) and a compact text summary (§3). The run is tainted from here on, like `read_page` |
| `wait_ready` | `timeout_s?` | `read` | Waits for "page ready" (§5): "ready" or "still changing" |
| `scroll` | `direction` up/down, `amount` 1–10 notches, `at?` {x, y} | `read` | A real wheel scroll; the next act needs a fresh `look` |
| `click` | `target` {`text`, `kind?`, `nth?`} **or** `x`,`y`; `expect` | `act` | Clicks a visible control found by its text (and kind: button, link, tab, checkbox, option, field…), else a point from the last look |
| `type` | `text`, `source` {`from`: message, card, note or document, `id?`}; `expect` | `act` | Types into the focused field. The text must come from an approved source (R6, §6.3) |
| `press_key` | `key` from a fixed list; `expect` | `act` | Enter, Tab, Shift+Tab, Escape, Backspace, Delete, arrows, Page Up/Down, Home, End, Space. No Ctrl, Alt, Super or F-keys |

- **`expect`** (≤120 characters) is the step's one success check (R1), such as "the dialog is gone". The next `look`
  repeats it: "You expected: … Check it now."
- **New gate kind `act`:** an action on an outside site. `roost/computer_use/gate_rules.py` judges it (§6) on a
  **resolution** that the runner builds from the live page, never on what the model claims.

## 3. What the model sees

- **The screenshot** is the page viewport only (CDP `Page.captureScreenshot`, clipped to the viewport). It never shows
  the desktop, the address bar or the terminal. Xvnc is 1280×800 at device scale 1, so the viewport is about
  1280×690. It goes as JPEG quality 60, under 350 KB, about 46×25 ≈ 1,150 visual tokens (the API's limit is 2,576 px
  on the long edge).
- **Masking (spec S15):** every editable field's box is painted over in the image before the model gets it (Pillow,
  already in the lock through pdfplumber). That covers what you typed in Take control, autofill and passwords. For
  each field the bot typed into during this run, the summary says only "holds what you typed: yes / no", never the
  value.
- **The summary**, wrapped in `<untrusted_page>` and escaped like `read_page`, gives: the URL, title and ready state;
  an open dialog and its title, or "cookie notice showing" with its buttons; up to 60 interactive targets in the
  viewport (kind, text, centre point in screenshot pixels, and a "commits" mark, §6.1); and the page facts as text
  (`read_page`'s extractor, which skips text boxes), cut to 3,000 characters.
- **Two views (R3):** vision picks the control and sees dialogs; amounts, balances, counts and confirmation URLs come
  from the text, never pixels. **Every look runs the stuck detector** (login, code or human check → Stuck card).

## 4. How input reaches the screen: xdotool inside the computer, through one keeper route

**Decision:** OS-level X input with **xdotool** (BSD-3; a Debian package, unmodified), run as the screen user 10002
inside `roost-computer-<id>` by our stdlib wrapper `roost-input`, through one signed keeper route. The argv is fixed:

`docker exec -i --user 10002:10002 roost-computer-<id> /usr/local/bin/roost-input <verb> <ints…>`

- **Why not CDP `Input.dispatch*`:** those events go into the renderer, so the X pointer never moves and you see no
  cursor. They can't reach the browser's own dialogs (permission bubbles, beforeunload). And input driven through
  DevTools is a known bot signal: the addendum's real run was never flagged because its input was real.
- **Why not RFB events on the VNC relay:** that would mix the bot's input into the channel that C2's `RfbClientFilter`
  guards for *your* input, which weakens that proof. We would also have to write our own keysym mapping for
  non-ASCII text, which xdotool already has.
- **The keeper's side:** `POST /desks/{id}/computer/input` takes a pydantic union (click, key, type, scroll or
  move). Only integers and fixed words go into the argv. **Typed text goes over stdin** (`xdotool type --file -`),
  never in the argv, because `docker events` prints an exec's argv.
- **`roost-input`'s own check** (a second, independent layer): before every action, the active window's class must be
  Chromium (`xdotool getactivewindow getwindowclassname`) and the point must be inside its content area. Otherwise
  it refuses, so a page can't send the bot's clicks into xterm or the taskbar.
- **Human-like, without fake jitter:** 8 short `mousemove --sync` steps then the click; 35 ms per key; wheel notches.
- **Coordinates:** the model gives screenshot pixels. The gateway maps them to the screen using the window geometry
  (`Browser.getWindowForTarget`, plus the window's inner and outer sizes read in a CDP **isolated world**, which the
  page can neither see nor change). Click-by-text uses the element's box centre (`DOM.getBoxModel`), after an
  occlusion check: the node at that point (`DOM.getNodeForLocation`) must be the target or inside it.

## 5. "Page ready"

All three must hold within `CU_READY_TIMEOUT_S` (10 s); otherwise the answer is "still changing", which is not an
error:
1. no main-frame navigation in flight, and `networkAlmostIdle` seen since the last navigation (`Page.lifecycleEvent`);
2. nothing in the viewport is visibly busy: no `aria-busy="true"`, no `role=progressbar`, no common skeleton class;
3. **the layout has held still for about 500 ms:** two 160×100 grey probes of the viewport, taken 500 ms apart,
   differ in under 1% of pixels. This screenshot diff also catches canvas and animation.

`click`, `type` and `press_key` wait for ready before resolving and after acting; the result gives URL, title, state.

## 6. The gate

### 6.1 Resolution and the commit test

The runner resolves every act from the live page into a frozen `ActResolution`: for a click, the target's accessible
text, kind, tag and input type; the form's method and default submit control; the link's host; the dialog it is in;
its box and the page URL; and a padded crop of the screenshot around the box, for the card.

`commit_class(resolution)` answers one of `browsing | consent | spend | send | submit | accept | delete | account |
unknown`. The first rule that matches wins:
- **Label:** the accessible name, value, title and aria-label, casefolded with accents stripped, English and Spanish,
  against `roost/computer_use/commit_words.py`. Spend: pay/pagar, buy/comprar, checkout, order, subscribe, upgrade,
  boost, bid, credits, donate, top up. Send: send/enviar, message, reply, post, publish, share, invite, comment.
  Submit: submit, apply/solicitar, confirm, place, finish. Accept: accept/aceptar, decline, agree, sign/firmar, hire,
  offer, contract. Delete: delete/eliminar/borrar, remove, cancel subscription, deactivate, close account. Account:
  save changes, change plan, password, email.
- **Structure:** a POST form's submit control, or Enter in such a form, is `submit` whatever its label says. A
  cross-origin frame (payment widgets) is `unknown`, and so is an icon-only control with no name inside a form or a
  dialog.
- **Consent:** inside a cookie or consent banner, Reject, Only necessary and Close are `consent`, which counts as
  browsing (R4). "Accept all" there is `accept`.
- **Browsing:** links to a host in the fence, tabs, menus (`aria-expanded`/`haspopup`), pagination, expanders,
  checkboxes, radios, and focusing a field.

A false positive costs one Yes ("Apply filters" asks). False negatives are what the other layers in §9 are for.

### 6.2 Verdict order (`judge_act`, pure; the runner never acts on "ask" without a card)

1. **`never`, with a plain sentence:** the tool is not allowed in this run, or the bot is on Mac Brave; you hold the
   computer, or another loop does (§7); there is no fresh look (§7); the target is a password or one-time-code field
   ("I don't type into password boxes. I'll ask you to take over.", then `ask_for_help`); the point is outside the
   page area; the action would open a file picker; or the budget is spent.
2. **Site fence (§6.4):** a link, or a key that sends a form, to a host outside the fence asks on a **new-site card**
   ("Let it go to accounts.example.com for this job?").
3. **Hard floor**, asking in every mode and every taint, with no session OK: a `commit_class` other than browsing or
   consent (floor `commit_click`); typed text from no approved source (`typed_text`); typed text with an email
   address, a phone number, or an off-site handle or link (`contact`, R9); `looks_secret` text (`secret`).
4. **Taint:** a tainted run may still act, but only on **non-committing navigation and form filling with approved
   text**. Everything committing already asks at step 3, and the card says "Based on outside content". A tainted run
   never gets `do` for a committing act.
5. **Mode:** Ask → ask. The **"Browsing actions"** topic switched to ask → ask. Plan (Review-first) → ask, because
   clicks depend on the screen and can't be planned. Auto-edit with Browsing actions set to "Just do it" → `do`.
6. **No cards in this run** (handoffs, rooms, routines): every ask becomes `never` with "needs your OK". A routine
   browses only after you set Browsing actions to "Just do it", and it never commits.

### 6.3 Approved text (R6)

- **The rule:** `type` passes only when its text appears **verbatim** (NFC, whitespace collapsed) in a message *you*
  wrote in this chat, an answered card's own words, or a note or document of yours that is not stored tainted.
- **Search boxes** (`role=searchbox`, `type=search` or a GET form) also accept the model's own short text: ≤100
  characters, no contact details, no secret. Searching is browsing.
- **Anything else** asks on a `typed_text` card that shows the full text; the Yes approves exactly that text.
- **The audit** keeps the source, the length and a hash, never the text.

### 6.4 The site fence (your own link scope)

- **What it holds:** the hosts in **your own** messages in this chat (`LinkScope.from_texts`, bare domains included)
  and the hosts you approved on new-site cards in this chat. A host covers its subdomains. Pages the bot reads **never** widen the fence; that is the difference from
  `open_page`'s link scope.
- **How it is enforced:** while a loop holds the computer, `Fetch.enable` for `Document` requests on every page target
  fails any top-level navigation outside the fence (`BlockedByClient`). The bot is told why, and it may ask on a
  card. A new tab or popup that a page opens is closed, and its URL is offered the same way.
- **It is derived, not stored:** each run rebuilds it from the chat's messages and cards. **No migration.**

### 6.5 What the Yes runs

- **The card** has one step per committing act. Its rows show the site, the label text read **as text** (R5, for example
  "Boost" vs "Submit"), the class ("Sends something") and `expect`. The crop is a sealed JPEG of at most 60 KB in the
  step, which sits in `approval_cards.steps` (already `enc:v2`).
- **On Yes,** the executor **resolves again**. The URL, the label, the class and the box (±8 px) must match;
  otherwise: "The page changed after you said yes, so I didn't click. I'll look again." It then moves the pointer,
  checks the node at the point once more, and clicks.
- **After the click,** the result tells the bot to check the confirmation before it says "done" (R7). After spending,
  it reads the balance back as text.

## 7. The loop

- **One loop per computer:** an in-memory `ComputerUseLease` per bot, taken by a run's first look or act until the run
  ends ("My computer is busy with another job of mine."); a restart clears it, like the `ControlLock`.
- **It pauses while you hold control:** calls are refused, like browser calls today (`_hands_refusal`).
  `ControlLock.epoch(bot_id)` counts takes; when it has moved since the run's last look, the next act gets "Look
  first: the screen may have changed while you had it." (R8). The bot never asks for a password again. C2's
  optional "Which account did you use?" stays.
- **Act, then check (R1):** every `click`, `type` and `press_key` needs a `look` taken after the last thing that moved
  the screen (an act or a scroll); the one exception is `type` right after the `click` that focused that field. Only
  one screen tool runs per model step; any more get "One screen action per step". So blind chains can't happen.
- **Budget per run:** 40 acts, 60 looks, 90 model steps once a run uses the screen (instead of 40), and a 20-minute
  deadline. When it runs out, a Stuck card (reason `asked`) carries the note "I used this job's step budget on
  {host}. Next: …".
- **Recovery ladder (R4):** (1) a cookie notice is flagged in the look, and the bot dismisses it with the consent
  buttons. (2) Not found, or the page changed: "Look again and try once more"; a second miss on the same target key
  gives a Stuck card with the URL and a one-line reason. (3) Covered: "Something covers 'Apply' (dialog
  'Newsletter'). Dismiss it or click outside, then try once more", counting toward the same two tries. (4) A login, a
  code, a captcha or a secret: today's detector or `ask_for_help` gives a Stuck card with Take control. Stuck cards
  (`stuck_cards`, v12) use reason `asked` and the free `note`, so no migration.
- **Quiet reports (R10):** a routine's run reports only a card, a Stuck card or an asked-for fact; no page narration.

## 8. Model

- **What exists:** the Messages API has a native computer toolset (`computer_toolset_20260801`: GA, no beta header,
  Sonnet 5 included). The Claude Agent SDK can't declare an Anthropic-defined client toolset; its tools are built-ins
  (off in Roost) and MCP tools (Roost's inert stubs). It takes images only in **streaming input mode** (a user
  message whose content is text and image blocks); single-message mode has no images.
- **Decision: plain image input with our own tools.** `ModelRequest.images` (new, frozen) carries **only the newest
  look's** JPEG. When it is set, `ClaudeSdkModel` calls `query(prompt=<async iterable of one user message>)`, with the
  rendered transcript as the text block and the image after it. Nothing else changes: one SDK step (`max_turns=1`),
  built-ins off, the deny hooks, no `ANTHROPIC_API_KEY` in the env. Older looks render as "[screenshot from an
  earlier look, not shown]". `ScriptedModel` ignores images; the tests check what `images` held.
- **Later:** if D5 moves Roost to an API key, the native toolset can replace our coordinate tools. The gate, the floor,
  the fence and the resolver stay, because they judge resolved actions, not the model's tool shape.

## 9. Security: page text steers clicks

Every look is attacker-controlled input next to a tool that clicks. These layers each hold on their own:
1. **The committing floor** (§6.1–6.2): label, structure and frame tests. It fails closed (`unknown` asks). Each Yes
   is single-use and is resolved again before the click.
2. **Typing only approved text** (§6.3): a page can't make the bot type a message, an address or a card number it
   made up.
3. **The site fence** (§6.4): only hosts from your messages or your Yes, enforced in Chromium, not by the model.
4. **No downloads, uploads or permissions:** downloads denied while a loop runs, the file picker intercepted, and
   notifications, location, camera, microphone and clipboard-read denied (`Browser.setPermission`).
5. **The input route** (§4): fixed argv, text on stdin, the browser window only, keys without modifiers.
6. **The masked screen and a summary without field values** (§3). **7. The audit:** one row per act (class, host,
   label, never typed text), which the daily "how I worked" Report reads later.

**Residual risks, said plainly:** a script button with a harmless label that posts over XHR counts as browsing (a
"write fence" blocking non-GET requests was rejected for v1, because GraphQL reads are POSTs; the next look notes "the
page sent data to the site" instead). A page can move a button between the check and the click: the ready wait, the
re-check at the point and a gap under 50 ms shrink that window but can't close it. The fence trusts every subdomain
of an allowed host.

## 10. UX

- **The cursor ring:** each act publishes `computer_pointer` {bot_id, x, y, kind: click | type | key | scroll}, in
  screen coordinates, with no text. `LiveScreen` draws a ring there, scaled to the canvas, that fades over 900 ms.
- **The hand:** the Lensbot face's existing `control` prop turns on while the bot has an open Stuck card asking you to
  take over, and the `ctrl` glyph is redrawn as a hand. Nothing passes `control` today; C3 wires it in the bot list,
  the panel and the chat header.
- **Activity lines** (live `toolLines`): "Clicked 'Apply'", "Typed into 'Search' (12 characters)", "Pressed Enter",
  "Scrolled down", "Looked at the screen", "Waiting for the page". **Cards:** the Ask card shows the crop above its
  rows; the new-site card shows the host. **Settings:** the switch **Browsing actions**, "Clicks and typing that don't
  buy, send or submit. Ask first (default) · Just do it."

## 11. Data and schema

**No migration** (the latest is v25; if one turns out to be needed, it takes **v26** and the controller confirms).
Topic `browsing` asks by default with no row change: `parse_topics` adds it unless the stored list holds the opt-out
word `-browsing`, which `topics_json` writes when you choose "Just do it". The new `FloorKind` words (`commit_click`,
`typed_text`, `contact`, `new_site`) and the crop live in the sealed `approval_cards.steps`; the rest is in memory.

## 12. Open for the user

1. **Every committing click asks, even in Auto-edit,** false positives like "Apply filters" included. Fine for v1?
2. **Browsing actions defaults to ask,** so a new Linux bot asks on its first click; "Just do it" per bot lets it browse.
3. **Renumbering:** C3 computer use, C4 terminal, C5 Vault: API keys, C6 Skills.
4. **Pillow** (MIT-CMU/HPND, permissive, already installed via pdfplumber) becomes a direct dependency (mask, crops).
5. **Linux computers stay opt-in per bot** (Amendment S7); C3 doesn't change that. Plan: `2026-10-22-roost-computers-c3.md`.
