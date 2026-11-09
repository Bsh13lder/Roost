# Roost Routines and Plan — Design

**Status:** DRAFT (2026-10-20). Nothing is built yet. §7 holds the open decisions for the user. This
is spec step 12's routines part (`docs/specs/2026-10-12-roost-design.md` §4.6 "Background", §4.3,
§8.2, step 12), plus a new per-bot **Plan**.

**What the user asked for:** **Routines**, scheduled jobs per bot with an on/off switch in its Profile
("HiMap Instagram inbox: every day at 10:07, 15:07, …", "HiMap Instagram growth: custom schedule"),
which the bot may create or change **with the user's OK**; each run posts a **Report** in the bot's
chat plus a quiet line ("Updated routine · <name>"). A **Plan**: one sealed Markdown file per bot in
the Obsidian Tasks markup, written by the bot and editable by the user, shown as a Calendar and a
Kanban; vault sharing is opt-in per bot, off by default. **The user's tasks stay on the Board.**

**What exists:** `WorkKind.ROUTINE` is reserved (`roost/work/models.py`); the drain loop
(`roost/talk/runner.py`) runs one batch per thread under one lock per bot and counts runs against
`DAILY_RUN_CAP` per Madrid day; memory capture skips routine runs (`roost/memory/capture.py`);
`croniter` and `react-day-picker` are dependencies; notes give the sealed-blob + `revision` CAS.

## 1. Shape in one paragraph

A routine is a row with a name, instructions and a schedule. A scheduler task in the gateway finds
due routines and **queues a `routine` work item**; it never runs a model itself. The bot's own drain
loop runs it like any other item, in the routine's own **run-log thread**, under the same gate,
taint, caps and Ask cards. When the run ends, its final reply becomes a **Report** in the bot's main
chat, linked to the run log. The Plan is a separate sealed Markdown blob per bot. It never wakes a
bot: times in the Plan are information; **only routines wake a bot.**

## 2. Schema (v17, one migration "routines and plan")

v15 is memory and v16 is R1's `bots.group`. This takes **v17**; if computers-2's migration (site
logins, `api_keys`, `skills`) lands first, this takes the next free number. All three tables are
scoped by `user_id`; every query has `user_id` in its WHERE, and another user's id gives 404.

**`routines`:**
- `id`, `user_id`, `bot_id` (FK, cascade on Retire this bot), `thread_id` (its run-log thread);
- `name`, `instructions`, `schedule` (JSON, §3.1): `enc:v2`, AAD `routines:<column>`;
- `enabled` (0/1), `tainted` (0/1: written by a tainted run, §3.3), `created_by` (`user` | `bot`);
- `next_run_at`, `last_run_at`, `created_at`, `updated_at` (UTC ISO; plaintext timestamps only);
- index `(enabled, next_run_at)` for the due query.

**`routine_runs`** (history; retention `RUN_LOG_RETENTION_DAYS`, start value 90, spec §4.7):
- `id`, `user_id`, `routine_id` (cascade), `bot_id`, `slot_at` (the planned time), `work_item_id`;
- `state`: `queued` · `running` · `done` · `missed` · `skipped` · `held` · `expired` · `error`;
- `note` (`enc:v2`, AAD `routine_runs:note`: "missed 3 runs while the Mac slept", the error),
  `started_at`, `finished_at`.

**`bot_plans`** (one row per bot):
- `id`, `user_id`, `bot_id` (unique, cascade);
- `content` (`enc:v2`, AAD `bot_plans:content`): the Markdown file;
- `item_taint` (`enc:v2`, AAD `bot_plans:item_taint`): a JSON list of item ids written by tainted
  runs (§6.4);
- `revision` (CAS, 409 + current copy, as notes), `export_enabled` (0/1, default 0),
  `created_at`, `updated_at`.

## 3. Routines

### 3.1 Schedules (pure, `roost/routines/schedule.py`)

Two kinds, validated by pydantic at every boundary:
- **`times`**: a set of weekdays (Mon–Sun) plus 1–`ROUTINE_MAX_TIMES` (12) `HH:MM` times.
  "Every day at 10:07, 15:07, 20:07" is `{"kind":"times","days":[1..7],"times":["10:07",…]}`.
- **`cron`** ("Custom"): a 5-field `croniter` expression, refused if two consecutive fires are
  closer than `ROUTINE_MIN_INTERVAL_MINUTES` (15), checked over the next 50 fires.

All times are **Europe/Madrid wall-clock** (`zoneinfo`), stored as the user wrote them, and
`next_run_at` is computed in Madrid then stored in UTC. DST: a time that doesn't exist (02:30 on
the spring-forward day) fires at the first valid minute after it; a time that happens twice (the
autumn fall-back) fires once, on the first. One function, `next_after(schedule, after_utc)`, is the
only place that does this, and `readable(schedule)` gives the words the UI and Ask cards show
("Every day at 10:07, 15:07 and 20:07"; cron gets its next 3 times instead of a translation).

### 3.2 The scheduler (`roost/routines/scheduler.py`)

- **Where:** one asyncio task in the gateway process, started next to `resume_all()` and stopped
  on shutdown. It ticks every `ROUTINE_TICK_SECONDS` (30). The spec's rule holds: one scheduler
  owner per domain (§4.6).
- **Each tick:** `SELECT … WHERE enabled = 1 AND next_run_at <= now` (per user), then for each row:
  record the slot in `routine_runs`, decide (below), and set `next_run_at = next_after(schedule,
  now)` plus that slot's jitter. The update is a CAS on the old `next_run_at`, so a slow tick can't
  fire a slot twice.
- **Jitter:** each slot adds 0–`ROUTINE_JITTER_SECONDS` (90) seconds, derived from a hash of
  `(routine_id, slot_at)`. It is deterministic (testable) and spreads routines that share a minute.
  The user's own odd minutes ("10:07") stay close to what they chose.
- **Missed runs after sleep:** a slot is **missed** when the tick sees it more than
  `ROUTINE_LATE_GRACE_SECONDS` (600) late (the Mac slept, or the gateway was down). All the slots
  missed for one routine collapse into **one** `missed` row ("missed 3 runs, 10:07 to 20:07") and
  the routine **runs once** (spec failure table, "Mac asleep": "marked missed and run once on wake"). The run
  is told "planned 10:07, running late at 14:22". No backlog of runs ever piles up.
- **Concurrency with the work queue:** the scheduler only queues; the bot's run lock and drain loop
  stay the one place runs happen.
  - **Skip while still going** (the OpenMausBot idea): if this routine already has a queued or
    claimed item, the slot is `skipped` ("the last run was still going").
  - **Your messages first:** `claim_batch` prefers `message` and `card_answer` items over `routine`
    items (one ORDER BY change: kind priority, then rowid). A routine never makes you wait behind it
    for more than the run already going.
  - **Off duty:** no item is queued; the slot is recorded `skipped` ("Off duty"). Coming back doesn't
    replay a day of slots.
  - **Stuck or Asking you:** the item is queued as normal and waits its turn.
- **Usage cap and "full limit"** (computers-2 D6):
  - A routine run is a run: it counts against `DAILY_RUN_CAP` and the per-run caps (steps, wall
    time, tokens). When the bot is at its daily cap, the slot is `held` and one notice is posted, as
    `_hit_daily_limit` does today.
  - When the user has told the bot to **use the full limit**, the bot may run past its daily cap
    until the subscription reading (C0) shows `USAGE_RESERVE_FRACTION` (0.10) or less left.
    **Routine runs never start inside that 10%**: their slots are `held` and the bot posts one
    Report, "Paused my routines: the usage limit is nearly used up; I'll start again at <reset,
    Madrid>". The 10% is kept for reporting and for the user's own chat.
  - "Use the full limit" is a per-bot setting changed only from the Profile or from an Ask card the
    user clicks; no model tool writes it (a page could otherwise ask the bot to burn the limit). It
    lasts until the next limit reset. Whether it covers routines at all is open decision §7 D3.

### 3.3 Trust in a routine run (no user present)

- **Starting taint:** a routine run starts clean unless the routine row is `tainted`, or the run
  loads tainted data (spec §8.2: "a task created in a tainted handoff makes the 08:00 routine that
  reads it tainted"). An Instagram inbox routine turns tainted at its first DM read, so everything
  outbound asks, as in any tainted run.
- **Origin label:** `routine_origin(name)` → "routine HiMap Instagram inbox", quoted in the
  instructions (§6.1) as the work-item origin, so the model knows nobody is watching live.
- **Approval policy:** the same house rules and hard floor as your chat. "Do it" rules apply in a
  clean run. Anything that asks raises an **Ask card**; the run **parks** (a parked run), the bot
  shows **Asking you**, and the card arrives on Home and in My turn. Per spec A13, a card from an
  unattended run expires after 30 minutes; the run then ends, the slot is `expired`, and the
  Report says what was skipped. (Open decision §7 D2.)
- **Never in a routine run:** `create_bot` (already refused outside a clean 1:1 run), memory
  capture (already skipped), and **routine writes**: a routine run that proposes a routine change
  still gets an Ask card, and the card is marked "a routine asked to change a routine".
- **Stuck:** a routine run follows the R5 path (`talk/instructions.py`): a loud `Blocked:` result,
  no Stuck card, and the Report says it got stuck and on which site.

### 3.4 The bot's routine tools (`roost/routines/tool_specs.py`)

| Tool | Gate kind | Rule |
|---|---|---|
| `list_routines` | `read` | Its own routines: name, schedule in words, on/off, next run. |
| `propose_routine(name, instructions, schedule)` | `write_create` | **Always an Ask card** (new hard-floor row "routine write"). The card shows the name, the schedule in words, the next 3 runs in Madrid time and the full instructions. |
| `propose_routine_change(routine_id, …)` | `write_change` | Always an Ask card, with a diff of what changes. |
| `pause_routine(routine_id)` | `write_change` | "Do it" in a clean run (it only removes power); asks in a tainted run. |

Delete and Run now are UI only. A routine saved from a card in a tainted run keeps `tainted = 1`,
and the card says "This run read outside content." After each change the chat gets a quiet activity line: "Created routine · HiMap Instagram
inbox", "Updated routine · …", "Paused routine · …" (the same pattern as `post_memory_note`).

### 3.5 Reports

- **What:** the routine run's **final reply** is the Report, so there is one per run and no extra
  tool. It goes into the bot's **main chat** as a message of kind `report`: a headline (its first
  line, up to `REPORT_HEADLINE_MAX` (80) characters), the markdown body, and "Open run log". The
  whole run (steps, tool lines) stays in the run-log thread.
- **Quiet runs:** if the reply is exactly `REPORT_QUIET_SENTINEL` ("[nothing new]"), no Report is
  posted, only the activity line "Ran routine · HiMap Instagram inbox · nothing new".
- A Report from a tainted run carries the "from web content" mark (P2 chat). **Limits:** at most `REPORTS_PER_BOT_PER_HOUR` (6) per bot; more fold into the run log with one
  line. Reports set the unread dot on Home and appear in the Feed with a deep link.
- **Failures** (missed, held, expired, error, stuck) always post a short Report, so silence never
  hides a broken routine.

### 3.6 Profile and routes

- **UI:** a list of the bot's routines: name, schedule in words, the next run in Madrid time, an
  on/off switch, and a menu with Run now, Edit, History and Delete. The editor has "Times" (weekday
  chips plus a time list) and "Custom" (cron with a live preview of the next 5 runs). Where the list
  sits is open decision §7 D1.
- **Routes:** `GET/POST /api/bots/{id}/routines`, `PATCH/DELETE /api/routines/{id}`, `POST …/run-now`,
  `GET …/runs`, `POST /api/routines/preview` (next 5 times + words, no write).

## 4. Plan

### 4.1 The file and its strict subset grammar (`roost/plan/grammar.py`, pure)

```
file     := line*                         ; split on "\n"; CRLF read as LF
line     := heading | task | other
heading  := "#"{1,3} " " text             ; kept, shown as section titles
task     := indent "- [" status "] " desc field*
indent   := "" | "  " | "    "            ; at most one level of subtasks (2 or 4 spaces, or a tab)
status   := " "  (Planned) | "/" (On it) | "x" (Done) | "-" (Dropped)
desc     := text with any "#tag" words    ; tags: "#" [A-Za-z0-9_/-]+
field    := " ⏰ " HH:MM | " 📅 " YYYY-MM-DD | " ⏳ " YYYY-MM-DD
          | " ✅ " YYYY-MM-DD | " ❌ " YYYY-MM-DD | " 🆔 " [a-z0-9]{6}
other    := any other line                ; kept byte for byte, never shown as an item
```

- **Lenient read, canonical write.** The parser accepts the fields in any order (the user's example
  writes `📅 … ⏰ … #tag`). The writer emits **`desc ⏰ HH:MM #tags 📅 date ✅ date 🆔 id`**: the
  time and tags inside the description, the Obsidian Tasks fields at the end. Obsidian Tasks parses
  fields from the line's end and stops at text it doesn't know, so a trailing `⏰ 10:07` would hide
  the `📅` date from Obsidian; this order keeps Obsidian, TaskForge and plain editors all reading it.
- **Ids:** every item gets a `🆔` (the Obsidian Tasks id field), assigned on first save. Tools and
  the Kanban act by id, so the user's edits elsewhere in the file never retarget a write.
- **Status rules:** `[x]` gets `✅ <Madrid today>` if missing; `[-]` gets `❌ <today>`; leaving
  either clears it. Invalid dates or times make the line `other` (kept, counted as "couldn't read").
- **Round trip:** `render(parse(text))` equals the canonical form of `text`, and every `other` line
  survives unchanged. Unknown emoji fields (`🔁`, `⏫`) stay in `desc`.
- **Limits:** `PLAN_MAX_BYTES` (256 KB) and `PLAN_MAX_ITEMS` (2,000). Done and dropped items older
  than `PLAN_ARCHIVE_DAYS` (60) move under a `## Archive` heading at the end on the next bot write.

### 4.2 Storage and edits (`roost/plan/store.py`, `service.py`)

One sealed blob per bot, CAS on `revision` as notes (stale base → 409 + current copy). A bot write is read-modify-write by id inside one
transaction, so it never clobbers the user's text outside that line. The plan is created empty on
the bot's first plan write or first open.

### 4.3 The bot's plan tools (`roost/plan/tool_specs.py`)

| Tool | Gate kind | Notes |
|---|---|---|
| `plan_read(from?, to?, status?, tag?)` | `read` | Items as data, quoted. Taints the run if it returns a tainted item. |
| `plan_add(text, date?, time?, tags?)` | `write_create` | Returns the new id. |
| `plan_update(id, text?, date?, time?, tags?, status?)` | `write_change` | `status` ∈ planned, on_it, dropped. |
| `plan_complete(id, note?)` | `write_change` | Sets `[x]` and `✅ today`; `note` adds a subtask line. |

- **Default policy: do it, in any run.** The Plan is the bot's own diary, not the user's records,
  so the tainted-run record floor (deletes, >3 writes) does not apply. It has its own cap,
  `PLAN_WRITES_PER_RUN` (20), and a bot may change only its own Plan.
- **Prompt:** each run's instructions carry today's and tomorrow's **clean** items (at most
  `PLAN_PROMPT_ITEMS`, 15). Tainted items show only as a count ("2 more from outside content; use
  plan_read").
- **Activity line:** one per run, "Updated plan · 3 items" (not one per write).

### 4.4 Taint per item

Writes from a tainted run add that item's id to `item_taint`. Loading a tainted item taints the run
(spec §8.2), but one tainted item doesn't taint the whole Plan. A user edit to an item's line in
Roost clears its id from `item_taint`, because the user wrote that text. External edits come in
only through §4.6's later import, which marks changed lines tainted.

### 4.5 The web views (lazy chunk `web/src/components/plan/`)

- **One parser, on the server:** `GET /api/bots/{id}/plan` → `{content, revision, items, unreadable}`.
- **Calendar:** a `react-day-picker` month grid with a dot per day that has items, and that day's
  list below sorted by `⏰`; undated items sit in "No date".
- **Kanban:** Planned / On it / Done (Dropped behind a toggle). Drag, or a card's menu for keyboards,
  calls `PATCH /api/bots/{id}/plan/items/{item_id}` with `base_revision`.
- **Text:** "Edit as text" (`PUT /api/bots/{id}/plan`, CAS); a 409 shows the newer copy, as notes.
- Lazy: loads only when the Plan opens (`npm run size`); colours and sizes only from `tokens.css`.

### 4.6 Sharing to the Obsidian vault (later)

- **Switch:** "Share Plan to my Obsidian vault" per bot, off by default, Profile only (no tool).
- **What it does:** after each plan save, a debounced writer writes `<vault>/<Roost folder>/<bot
  name>.md` as **plaintext** (that is the point). The card explains that the file leaves Roost's
  encryption. The vault path is a Settings value checked to be under `~` and outside `~/Roost`.
- **Direction:** one-way, Roost → vault, first. Two-way is open decision §7 D4.

## 5. Testing

- **Pure:** `next_after` across Madrid DST (2026-03-29 and 2026-10-25), times and cron kinds, the
  15-minute minimum, jitter bounds and determinism, missed-slot collapse; grammar round trip
  (property test with `hypothesis` if already present, otherwise table fixtures), `other` lines kept
  byte for byte, both field orders, Obsidian Tasks fixtures in canonical order.
- **Scheduler with a fake clock:** one item per due slot; CAS stops a double fire; skip while going;
  Off duty records `skipped`; sleep through three slots gives one `missed` row and one run; held at
  the daily cap; held inside the 10% reserve (fake usage reading); a user message claims before an
  older routine item.
- **Taint table rows:** a tainted routine starts its run tainted; a clean routine reading a tainted
  plan item turns tainted; a routine proposed in a tainted run shows the outside-content line;
  `pause_routine` asks only when tainted; a card from a routine expires and the slot is `expired`.
- **Reports:** final reply → `report`; quiet sentinel → a line only; per-hour cap; failures report.
- **Routes:** pydantic refusals, CAS 409s, user B's ids give 404 (routines, runs, plan, plan items).
- **Web:** vitest for the routine list and switch, the schedule editor preview, Calendar and Kanban
  (drag and keyboard move), the lazy-chunk split; one Playwright flow on the scripted gateway.
- No test calls a real model. `pytest --cov=roost --cov-fail-under=80`.

## 6. Phased build

- **P0 (smallest useful):** v17 `routines` + `routine_runs` only; `times` schedules; the scheduler
  with jitter, missed-run catch-up and skip-while-going; `routine` items with message-first claims;
  the final reply as a Report; the Profile list with on/off and Run now. Only the user creates
  routines (UI form). No cron, no bot tools, no Plan.
- **P1:** "Custom" (cron) schedules with the preview; the bot's routine tools and their Ask cards;
  activity lines; the quiet sentinel; history view.
- **P2:** `bot_plans`, the grammar, plan tools, prompt slice, per-item taint, "Edit as text".
- **P3:** the Calendar and Kanban lazy chunk. **P4:** "use the full limit" for routines and the 10%
  reserve (after computers-2 C0 gives a usage reading). **P5:** vault export (one-way).

## 7. OPEN DECISIONS for the user

- **D1. Where Routines and Plan live in the Profile** (vocabulary change).
  - (a) Routines in **Info**; Plan as a new tab **"Plan"** (Info · Plan · Documents · Computer · Links).
  - (b) One new tab **"Schedule"** with Routines on top and the Plan below.
  - (c) Plan under Documents as a special document; Routines in Info.
  - **Recommend (a):** routines are a short list with switches, which fits Info; the Plan needs room
    for a Calendar and a Kanban, and "Plan" is the user's own word.
- **D2. An Ask card from a routine when nobody answers.**
  - (a) Keep spec A13: it expires after 30 minutes, the run ends, the Report says what was skipped.
  - (b) It waits until the routine's next slot (or 24 hours), so a morning card still works after
    lunch.
  - **Recommend (b) for routines only:** the user asked for routines that work while they're away;
    the card is re-checked before it runs anyway (A13), and a new slot is `skipped` while it waits.
- **D3. Does "use the full limit" cover a bot's routines?**
  - (a) No: routines always stay under the normal daily cap; full limit is for chat and code jobs.
  - (b) Yes: the bot's routines may also run past the daily cap, never into the last 10%.
  - **Recommend (b), per bot and until the next reset**, since growth routines are the likely reason
    to say it; the 10% reserve still protects reporting and your chat.
- **D4. Obsidian sync direction.**
  - (a) One-way, Roost → vault: edits made in Obsidian are overwritten on the next save.
  - (b) Two-way: Roost reads the vault file back by mtime, merges by `🆔`, and marks lines changed
    outside Roost as tainted.
  - **Recommend (a) first**, with a header line in the file saying "Edit this in Roost"; (b) later
    if the user wants it, because a file anyone can write is outside content.

## User decisions (2026-10-20)

- **D1.** Routines go in **Info**, and a new **Plan** tab is added. The tabs become Info · Plan · Documents · Computer · Links. This is a vocabulary change the user approved.
- **D2. Question book.** Each bot keeps a book of non-urgent questions.
  - When a question isn't urgent, the bot picks a safe default, says which one it picked, and keeps working. The user answers later, and the bot adapts.
  - Urgent or risky questions (money, deleting, posting publicly, the hard floor) still wait as Ask cards, at most until the routine's next run.
  - The book shows in the bot's panel and in My turn.
- **D3.** "Use the full limit" covers routines too: per bot, until the next limit reset, and never the last 10%.
- **D4. Obsidian sharing is two-way from the start**, off by default for each bot.
  - Ticks and edits made in Obsidian flow back into the Plan, through the `🆔` ids and a revision compare-and-set.
  - Vault text read back counts as user-edited.
  - Lines Roost can't parse are kept byte for byte.
