# Teach a task (design note)

**What.** You show a bot a task once on its Linux computer and it becomes a Skill draft. Teach is a mode of
Take control: **Teach** (next to Take control) takes control and starts recording; **I'm done teaching** (with an
optional one-line description) stops, gives the computer back, and the bot posts a skill Proposal card in its
chat. Nothing is saved as a skill until you press **Save skill** (the existing `roost/skills/proposals.py` path).

**What is recorded (never typed text).** While teaching, every input message your control socket forwards
(`roost/gateway/routes/live.py`, after `RfbClientFilter` and `verdict`) is shown to a `TeachObserver`:

- a pointer press (button mask goes from none to some): the screen point is turned into a viewport point with the
  window geometry (read once per session), then `PageDriver.node_at` gives the control's kind and accessible label
  (Chromium's own AX name, never a field's value), and `url()` / `title()` the page. The URL keeps host and path
  only (no query, no fragment). A press outside the page is "used the browser's toolbar".
- the first key press after a click (or after Tab): "typed into <field label>" from `PageDriver.focused()`. The
  characters are never read. A secret field (password, one-time code) is recorded as "typed a password", and the
  skill step says to ask the user to sign in. Enter / Tab / Escape are recorded by name only. A paste is
  "pasted into <field label>", never its text.
- a capture waits at most `TEACH_CAPTURE_TIMEOUT_S` before the press is forwarded (so it reads the page before
  the click changes it); a failure records nothing and never stops the socket. At most `TEACH_STEPS_MAX` steps;
  a repeat of the same step (a double click) is kept once.

**Schema (v27, one migration).** `teach_sessions(id, user_id, bot_id, steps, step_count, capped, started_at)`,
one row per bot (unique `(user_id, bot_id)`), `steps` sealed `enc:v2` under `teach_sessions:steps` (the step
log JSON). The row is deleted when the proposal is made, or on discard. Every statement names `user_id`.

**Routes.** `GET /api/bots/{id}/teach` (teaching?, step count, capped), `POST /api/bots/{id}/teach/start`
(Linux computer only: 409 for Mac Brave; takes control), `POST /api/bots/{id}/teach/stop`
`{description?, discard?}` (gives the computer back; 422 when nothing was recorded or the proposal is refused,
and the session stays so nothing is lost). Another user's bot is 404.

**Draft.** The worker model (`make_worker_model`, `ask_worker`, agent `teach-skill`) gets the step lines quoted
as data plus your description and answers JSON `{name, use_when, steps[]}`. If it fails or the draft does not
pass `SkillDraft` validation, a plain draft is built from the steps themselves. The proposal is always marked
**from web content** (page titles and labels are web content), so a saved skill keeps `tainted`.

**No new tool.** Only the person starts or stops teaching, over HTTP; no model tool reaches it.

**Risks.** (1) Labels and titles are untrusted: quoted as data to the worker, and the card is tainted. (2) A
label can hold personal words (an account name): it stays sealed, is deleted after the proposal, and the skill
validator refuses secrets; the plain draft leaves out a line with an email address or a secret and is cut to
the skill body limit. (3) The geometry is read once; a moved window or a second tab gives weaker steps
(the URL still says where you were). (4) A session lives only as long as the hold that started it (its `ControlLock`
epoch): I'm done, the Stuck card or a gateway restart stops recording at once and throws the log away, so a
later ordinary Take control is never recorded. (5) The control socket reads the lock again after a capture, so
a press held for the page is never sent after a hand-back.

**Web.** A plain Teach button beside Take control on the Computer panel, and in the control sheet an
"I'm done teaching" bar with an optional description field. Lazy with the control sheet.
