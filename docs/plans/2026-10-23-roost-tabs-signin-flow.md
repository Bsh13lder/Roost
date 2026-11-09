# Tabs, sign-in clicks and the secret field (owner decisions, 2026-10-23)

Background: the owner's chat with the bot "Gela". The bot could neither see nor close the two extra tabs in
its browser. Clicking Upwork's "Log in" asked for a Yes, and after Yes the chat said "It didn't run" (twice).
And the sign-in flow made the owner Take control for everything, unlike Grok, where the bot drives the sign-in
and asks only for the password.

These decisions are the owner's. They lift the v1 freeze for these three fixes only.

## B1. Tabs

A Linux bot gets three more screen tools (`roost/computer_use/tab_specs.py`, the work in
`roost/computer_use/tabs.py` and `roost/desk/tabs.py`):

| Tool | Gate kind | What it does |
|---|---|---|
| `list_tabs` | `read` | Every page tab of its browser: index (from 1), host and title. The title is the page's own words, so it is escaped and quoted as untrusted data (`<untrusted_page>`); the tab the bot works in is marked. |
| `switch_tab(index)` | `act`, free | Brings that tab to the front (`Target.activateTarget`, then `Page.bringToFront`) and makes it the bot's tab (`DeskBrowserPage.attach_tab`, which moves armed guards with it, the way `follow_front_tab` does). |
| `close_tab(index)` | `act`, free | Closes that tab (`Target.closeTarget`). The last tab is never closed: it goes to `about:blank` instead. Closing the bot's own tab moves it to the tab in front (`front_tab`). |

- "Free" means what it means for `open_app` (`CU_FREE_ACT_TOOLS`): inside its own computer a bot may change
  tabs without a card, in every approval mode, clean or tainted. A tab switch moves nothing but the bot's view,
  so the next act needs a fresh look (the loop counts it as an act).
- The index is the one the run's last `list_tabs` gave (its target ids are kept in memory); a switch or close lists
  again first, so a tab that went away is a plain "There's no tab N any more. List the tabs again." and never
  another tab. With no listing yet: "List the tabs first". A switch or close never navigates anywhere new, so the
  site fence is untouched.
- `open_page` already navigates the bot's own tab: `Target.createTarget` is used only when the browser has no
  page at all (`DeskBrowserPage._ensure_session`). That stays.
- **Popups:** while a screen loop holds the lease, the guards close every new page target (C3). For a sign-in
  popup (Google, Apple, Microsoft) that is wrong: the sign-in can't happen. A new tab whose address is on the
  site fence, or on a sign-in host in `SIGN_IN_POPUP_HOSTS`, is now **kept** as a tab, and the look says
  "A new tab opened: <host>. Use list_tabs and switch_tab to work in it." Anything else is still closed and
  offered on a new-site card, as before. The kept tab is still inside the fence: its navigations are checked
  by the bot's own guards once it switches to it.

## B2. Signing in is not an account change

`roost/computer_use/commit_words.py`: the `account` class lost "sign in", "log in", "iniciar sesion",
"email" and "correo". These words, plus "continue", "next", "continue with google|apple|email|microsoft",
"siguiente" and "continuar", are ordinary browsing (no card; the Browsing actions topic still applies). They are
read only when no committing word matched ("Continue to payment" is still spend), and the sign-in phrases are
taken out before the committing words are read, so "Sign in" is never "sign" (accept). The strong ones (sign in,
log in, continue with Google…) beat a POST form's structure, since a login form posts; the weak ones ("Next",
"Continue") inside a POST form still ask as submit, so a checkout step's Continue keeps its card. These stay
account changes: "sign up", "registrarse", "create account", "crear cuenta", "log out", "cerrar sesion",
"save changes", "change plan", "change password", "change email", "password" and "contrasena" on a button.

**Why "It didn't run".** The approved re-run (`ScreenReruns` → `ComputerUse.rerun`) differs from a run's act
in one way that matters: no `look` comes first. A look brings the bot's tab to the front (`page.geometry()`,
`Page.bringToFront`); the re-run went straight to `wait_ready`, whose first step is a screenshot. Chromium
never answers `Page.captureScreenshot` for a tab that is not in front, so with other tabs in front (the
owner's two extra tabs) the CDP call timed out after 30 s with a `CdpReplyError`. `_guarded_rerun` caught only
`DeskAsleep`, `DeskUnavailable` and `InputRefusedByComputer`, so the error reached `ApprovedCalls`, which
answered its catch-all "It didn't run. Nothing changed." And the web only ever showed the card's fixed line
"It didn't run.", never the reason (`approval_result` is hidden in the chat).

The fix:
1. Every wait for the page (`ComputerUse._ready`) brings the bot's tab to the front first.
2. The re-run catches page errors (`CdpClientError`, `ScreenGrabError`) and says why in plain words
   ("My browser didn't answer, so I didn't click. Try again in a moment.").
3. A failed Yes posts a notice line under the card, "It didn't run: <reason>", from the step's own sentence
   (never page text: every screen reason is one of the runner's fixed sentences).

## B3. Grok-style sign-in with a secret field

The bot drives the sign-in itself: it clicks Log in, Continue with Google or Next (browsing, B2), and types
the email or user name the owner gave **in their own message** (the existing rule: your own words don't ask).
An email address the owner typed in their own words (`text_ok`) is now typed without a card, but only into a
sign-in page's box (`PageTarget.sign_in_box`: autocomplete `username`/`webauthn`, a box in a form that also holds
a password box, or a box whose id, name or label says login/user name/usuario) and only when nothing in it looks
secret; anywhere else contact details still ask (a newsletter's email box does).

When the page shows a password, one-time-code or verification-code box, the bot calls
`ask_secret_field(kind: "password" | "code", site, why)`:

- It is refused unless this is your own chat, the bot's computer is Linux, the page in front is on `site`,
  and the page has such a box (`secret_field`, which now also covers `autocomplete=one-time-code`, a numeric
  box with `maxlength` 4 to 8, and boxes named or labelled code/otp/verification/pin/código).
- It stops the run on a Sign-in card with `field` set (schema **v35**: `stuck_cards.secret_field`, plaintext
  `password` | `code`, NULL for every other card; Block and card carry it, and a field card is never "met
  again" by the next field, so a password then a code opens a second card). The card says "Type your <site>
  password; it goes straight into the box on <bot>'s computer. The bot never sees it." and shows a masked field and
  Send, with Take control as the fallback, and Later (no Check again).
- A passkey, security key or QR code is never a field: the bot asks with `request_sign_in` and you Take
  control. "Try another way" choices are the bot's own clicks (browsing): it clicks what you said.

`POST /api/stuck/{id}/secret` (Origin checked like every write; body `{value}`, pydantic, 1–256 characters):

0. The body is read by hand (`SecretIn`, strict, extra forbidden): a bad body is a 422 that never echoes it.
1. Your card, open, a field card, a Linux bot (another user's card: 404; closed: 409; not a field card: 400).
2. Refused while you hold the computer (409: type it on the live screen yourself), and while another job holds
   the computer's screen lease (the secret takes the lease `secret:<card>` for the moment it types).
3. The page is read again: its host must be the card's host, and the box must be a secret box: the focused one,
   or else the single visible one (clicked first to focus it). Wrong host, no box, or several boxes: 409 with
   a plain sentence, and the card stays open.
4. The value goes to the keeper's input route as `type` (text on stdin only, `roost-input`), and nothing else
   is pressed. It is never logged, stored, put in an event, a message, an audit row or a model prompt: the
   audit row (`secret_typed`) keeps the kind and the length only.
5. The card closes as cleared with your continue line "I typed your <kind> into the box. Carry on." The bot
   then clicks Next or Sign in itself (browsing). No Vault row is saved here (merge decision, 2026-10-23): the sign-in is not finished yet, and A1 saves a login only once the computer looks signed in.

The web: the masked field sits inside the Sign-in card (`web/src/components/chat/SecretField.tsx`,
`autocomplete="off"`, `type="password"`), the value lives only in the field's own state and is cleared right
after Send, and it never reaches the store or a log.

## Tests

- Tabs: listing (escaped titles, the bot's mark), switch (attach + front), close (never the last; the bot's own
  tab moves to the front one) with fake CDP pieces in the `tests/test_front_tab.py` style; the gate's free verdict;
  kept sign-in popups.
- B2: the new browsing words and the kept account words; the re-run with the bot's tab behind another tab
  (the fake page hangs a background screenshot) now brings it front and clicks; a CDP error says why; a failed
  Yes posts "It didn't run: …".
- B3: OTP detection; `ask_secret_field` refusals and the card; the route (Origin, 404 for another user, 409 with
  no box or the wrong host, 400 on a non-field card); the value never appears in logs (caplog), events, messages
  or the audit; the web field.

- Not built yet: the scripted E2E of the masked field on the fake shop page (`web/e2e/`); the server, route and
  web component tests cover the flow. The schema is v35 because v34 belongs to another branch, so
  `tests/test_migrations.py::test_versions_are_consecutive_from_one` passes only once that branch is merged.
