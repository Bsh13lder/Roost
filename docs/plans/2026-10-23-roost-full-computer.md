# Full computer, standing permissions and the Fable check

Owner decisions, 2026-10-23 (they lift the v1 freeze for this track, like Install an app did):

- **D1. Inside its own computer a bot is free.** A bot uses its whole Linux computer like a person: it opens apps,
  sees the whole screen, and clicks, types and scrolls in any window with no Ask card. The computer is sealed (no
  Mac, no keys, no other bot), and the worst case is a broken computer that a recreate fixes.
- **D2. Real accounts keep their checks.** Inside Brave nothing changes: the page is resolved, the site fence holds,
  buying, sending, posting, submitting, deleting and account changes ask at the hard floor, and a password box is
  never typed into.
- **D3. An approved routine does not ask again for what it names** (the owner's weekly-posting case). Its standing
  permission is fixed data the code checks (site, action, count per day, end date), never only words.
- **D4. Fable 5.1 checks each act a standing permission lets through.** It can only turn the act into an Ask card;
  it can never allow more than the permission. A failure or a timeout counts as "ask".
- **D5. The computer starts as a computer, not a browser; tabs don't pile up** (owner, 2026-10-23: "spamming tabs
  and not closing ... start the computer, not the browser; the bot will choose what it needs"). See "D5" below.

Known and accepted (owner, 2026-10-23): the computer's egress only refuses private addresses and Roost's ports, so
a terminal on the computer reaches any public host, even one Brave's site fence would block.

Order: step 1 is built first. Steps 2 and 3 are shown to the owner before they are built (they decide what happens
without them).

## Step 1: the full computer (no migration)

### 1.1 What is in front

- `roost-input front` prints one line: `brave L T W H` when the active window is Brave's (`CHROMIUM_CLASSES`), else
  `other`. Nothing else (no titles, no classes: a window title can carry page text).
- Keeper: `front` is an allowed verb of the signed `POST /desks/{id}/computer/input` route, no `--window`, answer
  `{"front": "brave"|"other", "window": [l,t,w,h]|null}`. `Desk.front_window()` returns a frozen `FrontWindow`.
- The runner asks before every look and every act. The model's arguments never decide it.

### 1.2 `look` on the whole screen

- Brave in front: today's look, unchanged (CDP viewport, masked fields, page summary).
- Anything else in front (or Brave closed): a whole-screen grab, 1280×800, through the keeper's VNC relay
  (`Desk.open_screen()`; Xvnc runs `-AlwaysShared`, so the live viewer is not disturbed): handshake, Raw
  encoding, one non-incremental FramebufferUpdateRequest, decode with Pillow (`roost/computer_use/screen_grab.py`,
  a deadline, a size check on every length the server sends).
- **Every visible Brave window is painted black in the grab** (its rect from `front`/`chromium_windows`, a new
  `roost-input browsers` verb printing rects only), so a page's fields and text never reach the model unmasked by
  the side door. To see the browser the bot brings it to the front (`open_app browser`) and looks again.
- The summary for a desktop look is plain: `screen: desktop`, the front window kind, no page text. The image goes to
  the model only, as today (never stored, logged or sent to the web).

### 1.3 Acts in any window

- New argv mode `roost-input <verb> <ints> --screen`: the point must be inside 0..1279 × 0..799 and **not inside a
  visible Brave window** (refused `in_browser`), and the active window must not be Brave's. Keys from `CU_KEYS`,
  text on stdin only, one fixed word on stderr, as today.
- `ActResolution` gains `space: Literal["page","screen"]` (default `page`). A screen act has no DOM target, its
  commit is `browsing`, and `judge_act` returns `do` for it before the floor (D1). `act_commits` must branch on
  `space` before its "no target means committing" rule.
- `runner._dispatch`: front is Brave → today's `_act` (resolve, gate, park or act). Front is other → `_screen_act`
  (no DOM, no `_typing_where_clicked`, `ScreenInput` in screen mode). The lease, step budget, "look first", epoch
  and held-lock checks stay exactly as they are; the point key is used for the two-misses rule.
- Typed text stays out of every log, audit, event and line (length and keyed hash only).

### 1.4 `open_app(app, why?)`

- Kind `act`, free (D1). `app` is one of `browser`, `files`, `terminal`, `images`, or the exact name of a package in
  the bot's `bot_apps` (checked by the gateway in `AppStore.packages()`).
- `roost-input open <id>`: a fixed map (`browser` → `roost-browser`, `files` → `pcmanfm /home/comp`, `terminal` →
  `lxterminal`, `images` → `gpicview`); for a package, the `.desktop` files that `dpkg -L <pkg>` lists under
  `/usr/share/applications`, the first `Exec=` with its field codes (`%f %u …`) removed, split with `shlex`, run as
  an argv with no shell, detached (`setsid`), as the computer's own user. No `.desktop` file → refused `no_window`.
- The audit keeps the verb and the app id only.
- The chat line: "Opened Files", "Opened geany".

### 1.5 Prompt and tests

- The bot's computer section says: the computer is yours; open apps with `open_app`; `look` shows the whole screen
  when an app is in front; the browser's rules are unchanged.
- Tests first for every piece: `front`/`browsers`/`open`/`--screen` parsing and refusals in `test_roost_input.py`,
  the keeper verbs, the grab decoder against `roost/desk/fake_screen.py`, the black-out, the gate's screen branch,
  the runner's branch (front faked), the tool spec count. The Brave-only tests that pin today's fence stay for
  `--window` acts.
- E2E: the scripted fake computer answers `front` as `other` for one scripted step.

## Step 2: standing permissions (outline, owner review before building)

- Schema v33 `routine_permissions`: `id, user_id, bot_id, routine_id, host` (sealed, plus a keyed HMAC `host_key`),
  `action` (`post`, `send`, `submit`: from the hard-floor kinds; never `spend`, `delete`, `account`, `secret`,
  `password`), `max_per_day`, `until` (Madrid date, at most 30 days out), `created_at`, `revoked_at`.
- Made only by the owner's own click: the routine editor's "Let it … on … up to … a day until …" row, or the same
  row on a routine proposal's Approve. A bot can propose one in `propose_routine`; it is stored only on Approve.
- The gate: in a routine's run, `ApprovalState` carries the routine id and its live permissions with today's count
  (precomputed; the judge stays pure). A hard-floor act that matches host, action, count and date gets
  `Verdict("do","standing_ok")` and an audit row; anything else asks as now.
- Info → the routine shows its permission and Revoke (at once).

Decisions made while building (2026-10-23):

- **Acts only.** A standing permission covers screen acts in the bot's browser. No write tool matches: the only
  floor write that sends (`use_connector`) names a connector, not a host the pure judge can trust.
- **Action from the page.** `commit_class` `submit` is `submit`; `send` is `post` when the control's words say post,
  publish, share, tweet or comment (EN/ES), else `send`. Spend, delete, account, accept, unknown, a covered control,
  a form sent to another site, a new site, contact details, secrets and password boxes never match.
- **Typing.** Typing the bot's own words into a box on a permitted site (`typed_text` floor) matches any live
  permission for that site and does not use the count; the click or Enter that sends it does. Fable sees the text.
- **The count** is `used_day`/`used_count` on the row, moved by one compare-and-set `UPDATE` only after Fable says
  `fits`, so one run cannot exceed `max_per_day` and a revoke or end date holds mid-run. The gate re-checks
  liveness before the check (`roost/standing/guard.py`).
- **Several per routine**: at most 3 live; the same site and action replaces the old one (keyed `host_key`).
  Hosts are stored as their site (`www.` dropped) and match its subdomains, like the site fence.
- **Only all-routine batches** carry permissions; a routine run carried on by a card answer asks as before.
- **Approve** stores the proposed permission as it is, or the card's switch drops it (`{"permission": null}`), or
  a body may set another; it is checked (dates, fields) before the routine is written.
- Routes: `GET`/`POST /api/routines/{id}/permissions`, `DELETE /api/routines/{id}/permissions/{permission_id}`.

## Step 3: the Fable check (outline, owner review before building)

- `roost/standing/check.py`: one `ModelRequest(model=FABLE)` on the worker model with the routine's instructions and
  the act as escaped structured fields (host, action, the button's words, typed text's first 200 characters
  escaped), answer `fits` or `ask`. Anything else, an error or a timeout → ask. The reply is never logged.
- Hooked after the standing match, before the act runs (`runner._act` / `Gate.decide`), so `standing_ok` can only
  become `ask`.
- Tests use a scripted worker agent constant; no real model.

Decisions made while building (2026-10-23): the hook is in `Gate.decide` (not the runner), so the screen loop is
untouched; only a reply that is exactly `fits` (spaces and case aside) passes, with a 30 s timeout; the scripted
worker (`standing-check` agent) answers `fits` only when the routine's instructions name the act's host. With no card
to show, a failed check is `never` (`needs_your_ok`), as every other ask.

## D5: Brave on demand, one fresh window, tidy tabs (built 2026-10-23)

- **Boot.** `roost-computerd` starts Xvnc and JWM only: an empty desktop. Brave starts when something wants it:
  the first DevTools bytes on `/run/screen/cdp.sock` (a desk call; the keeper's boot probe connects and sends
  nothing, so it starts nothing), or a connection to `/run/screen/want.sock` (0600, the computer's user), which
  `roost-browser` (tray, Super+B, roost-input's `open browser`) asks through `roost-pipe want` when no Brave runs.
  `BrowserProcess` owns it: a Brave that quits (its last window closed) is not started again until the next want,
  and its bridge client is closed so the gateway reconnects; `RestartBudget` (5 starts a minute) cuts off a crash
  loop by answering no instead of ending the container.
- **One fresh window.** Before each start the profile's restore files go (`Default/Sessions/*`, `Current/Last
  Session/Tabs`; cookies and logins stay) and Preferences say `exit_type: Normal`, `exited_cleanly: true`, with
  `--hide-crash-restore-bubble`: no old windows, no "Restore pages?". The desk gives a just-started Brave
  `CU_FIRST_TAB_WAIT_S` to show its own tab before it makes one, so there is one tab, not two.
- **Tabs.** `roost/computer_use/run_tabs.py` (`RunTabs`): the tabs open when a run first reaches the browser are
  never closed; past `CU_RUN_TABS_MAX` (4) the oldest tab the run opened closes; at the run's end every tab it
  opened closes except the bot's own. Nothing closes while you hold the computer, and with no Brave window nothing
  is listed (a listing would start Brave again). The prompt says the computer starts with an empty desktop and to
  keep to one tab.
- **Deploy.** Rebuild `roost-computer:dev` (the supervisor, `roost-pipe`, `roost-browser` changed) and restart the
  computers; the gateway carries the rest.
