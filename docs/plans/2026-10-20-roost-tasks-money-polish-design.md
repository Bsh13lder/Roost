# Roost — Tasks & Money polish, design

> Status 2026-10-20: design, ready to plan. Scope: audit `.superpowers/sdd/2026-10-20-tasks-money-audit.md`
> items 1, 2, 3, 4, 6, 7, 9, 10 and every quality issue, plus the user's ruling (same day) that the quick
> lines are **as rich as possible**. Plan: `docs/plans/2026-10-20-roost-tasks-money-polish.md`.

## 0. What the code says today (every audit claim checked)

All ten parser rows were reproduced with `read_words` + `read_date` on a throwaway data dir. The culprit
is `nl_time._rule_absolute_date`: dateutil `fuzzy_with_tokens` reads any digit as a day, month or year.
Bare "Friday", "next week" and "end of month" match no rule. Also confirmed: `TaskIn` (`routes/tasks.py:38`)
has no `recurring` / `reminder_at` (`TaskPatchIn` already has both); the Tasks tab is one flat
`listTasks("open")` (`TasksBoard.tsx:35`); the money routes have no edit or delete; nothing reads
`reminder_at` and `day_summary.py` is used only by its test. Every quality row holds.
Two corrections: priority words without "!" **are** read by `nl_time.extract_priority`, but the quick
line never calls it (it uses its own `!word` regex); and "Pay 1.200€ rent" has a second bug: the
quick line's amount pattern doesn't read a thousands separator, so "€" is left in the title.

## 1. Decisions

- **P1. One server parser.** The web never reads a line. It shows the server's reading as chips, and it
  adds exactly that reading (redesign P3's rule, kept). Autocomplete only *suggests* names from lists the
  web already loads (projects, bots); the server then reads the accepted text.
- **P2. The safe date grammar (§2) replaces dateutil.** `_rule_absolute_date` and the `dateutil` import
  go. A number is a date only beside a month name, in `d/m`, in ISO, or after "the"/"el día".
- **P3. Rich task line (§3).** Priority shorthand, star, estimate, reminder, repeat, `@bot`, `#project`,
  amount. Two markers of one kind: **the last wins**, every marker of that kind leaves the title, and a
  warning chip says so ("Two priorities: kept !low").
- **P4. Priority scale is unchanged.** Roost already has four levels, `low · medium · high · urgent`;
  "highest" *is* `urgent`. No enum or schema change for priority.
- **P5. Assigning to a bot (`@Scout`) is your own message, not a `handoff` item.** A `handoff` is
  bot-to-bot: it needs an asking run that waits, and `WorkQueue.recover_on_boot` drops open handoffs, so
  an assignment would vanish on restart. Instead the create route, only with `assign_confirmed: true`,
  sets the task's `owner` to the bot id, posts *your* message in that bot's main chat ("Please take this
  task: “Call plumber” (due Wed 21 Oct 09:00).") and queues a `message` item with `ORIGIN_YOU`, exactly
  as `POST /api/threads/{id}/messages` does. The run goes through the same gate, caps and Ask cards; the
  task is untainted (you typed it); `ask_bot` is untouched. The chip must be confirmed before Enter.
- **P6. Expense quick line (§4)** on the Money tab and each project's Money tab: amount, `#project`
  (exact or ask, never made), a past day, `vendor:`, `*`, and a repeat word that makes a repeating expense.
- **P7. Exact or ask everywhere on the web.** `POST /api/money/expenses` with a `project` *name* now
  refuses an unknown name (422, "No project is called “X”. Make it on the Projects tab first."), like the
  task line. A bot's `log_expense` keeps H3 (it may still make a project); this is the web only.
- **P8. Repeating expenses materialise lazily on read.** See §5.
- **P9. Undo is a toast with one action.** `ui/Toast.tsx` gains `action?: {label, run}`; Undo calls a
  real inverse route (restore, reopen, void false, restore-dues, move back). Nothing is "pending".
- **P10. Charts are plain SVG components**, no new dependency, in a lazy chunk (`MoneyReports`).
  Amounts are never added across currencies: one series per currency, labelled.
- **P11. Views are computed on the server** (`roost/tasks/views.py`, pure, Madrid today) because titles
  are `enc:v2` and search needs the decrypted text; the web never filters by date itself.
- **P12. Parallel with polish R1.** Web changes stay in the Board, project pages and the money/tasks
  components. Never touched: `Layout`, `Home`, `ChatList`, `Chat`, `Profile`, `components/panel/*`,
  `components/sidebar/*`, chat CSS, `styles.css`, `tokens.css`, `ui/Sheet.tsx`, `App.tsx`,
  `api/types.ts`, `web/tests/fixtures.ts`. New wire types live in `api/money.ts` / `api/tasks.ts`;
  new styles are appended to `board.css`, `tasks.css`, `projects.css` (each stays ≤ 800 lines), so
  `styles.css` gets no new import.

## 2. The safe date grammar (EN and ES), `roost/tasks/day_words.py`

Words are matched case-insensitively, accents optional (`miércoles`/`miercoles`), whole words only.
`D` = 1–31, `M` = a month name or its 3+ letter start (`jan…dec`, `ene…dic`, `sept`, `set`), `Y` = 4 digits.

| Rule | EN | ES | Reads as (forward, for a due) |
|---|---|---|---|
| named day | today, tonight, tomorrow, day after tomorrow | hoy, esta noche, mañana, pasado mañana | +0, +0 at 20:00, +1, +2 |
| bare weekday | friday (full names only) | viernes | next one; today's weekday → +7 |
| anchored weekday | next/on/this/by fri(day) | el/este/próximo viernes, el viernes que viene, antes del viernes | as today's nl_time rules |
| week / month | next week, this weekend, end of week, next month, end of month | la semana que viene, la próxima semana, este finde, este fin de semana, el mes que viene, fin de mes, a fin de mes | Mon next week, Sat, Fri, 1st next month, last day this month |
| relative | in N days/weeks/months/hours/minutes | en / dentro de N días/semanas/meses/horas/minutos | now + N |
| day + month | 15 march, march 15, 15th of March, Nov 3 [Y] | 15 de marzo [de Y], 3 nov | that day; past without Y → next year |
| numeric | `d/m`, `d/m/Y`, `Y-m-d` | same (`d/m` is day first) | invalid day (31/02) → not a date |
| day of month | the 15th, on the 15th | el 15, el día 15 | next 15th (this month if ahead) |
| clock | at 5, at 9:30, 9am, 9 pm, 21:00, at noon | a las 5, a las 9:30, a las 5 de la tarde / de la mañana / de la noche, al mediodía | see AM/PM |

- **Never a date:** a lone number ("3", "15", "101", "2045"), a number with a unit ("45 eur", "15 case"),
  `d.m` (the dot is money's thousands sign), a 2-digit year.
- **Past rolls forward** for a due: a day + month with no year that is before today is next year's.
- **AM/PM guess** for a bare hour after `at` / `a las` with no am/pm/24h form: 1–7 → 13:00–19:00;
  8–12 as written; 13–23 as 24h. `de la tarde/noche` adds 12 (1–11); `de la mañana` keeps it.
  A time with no day is today if still ahead, else tomorrow (as now).
- **Backwards (expense days, `direction="past"`)**: also `yesterday/ayer`, `day before yesterday/anteayer`,
  `N days ago / hace N días`, `last friday / el viernes pasado`; a bare weekday is the latest past one;
  a day + month with no year is the latest past one; a future day stays refused (`parse_spent_at`).

Examples, today **Tue 2026-10-20 14:00 Madrid** (title = what is left):

| Typed | Due | Title |
|---|---|---|
| Buy 3 apples | none | Buy 3 apples |
| iPhone 15 case | none | iPhone 15 case |
| Room 101 | none | Room 101 |
| Groceries 45 eur | none | Groceries 45 eur |
| 15 march | 2027-03-15 | — |
| 3/11 · 11/3 · 31/02 | 2026-11-03 · 2027-03-11 · none (stays in title) | — |
| 3 de noviembre | 2026-11-03 | — |
| pasado mañana | 2026-10-22 | — |
| Call mom at 5 | 2026-10-20T17:00+02:00 | Call mom |
| Call mom at 9 | 2026-10-21T09:00+02:00 | Call mom |
| Cena a las 9 de la noche | 2026-10-20T21:00+02:00 | Cena |
| Friday · viernes · Tuesday | 2026-10-23 · 2026-10-23 · 2026-10-27 | — |
| next week · la semana que viene | 2026-10-26 | — |
| end of month · fin de mes | 2026-10-31 | — |
| next month · el mes que viene | 2026-11-01 | — |
| the 15th · el día 15 | 2026-11-15 | — |
| Nov 3 at 9:30 | 2026-11-03T09:30+01:00 | — |
| in 2 weeks · en 2 semanas | 2026-11-03 | — |
| (expense) el viernes pasado · 15 march | 2026-10-16 · 2026-03-15 | — |

## 3. The rich task line, `roost/tasks/line_tokens.py` + `repeat_words.py`

A token stands alone (spaces or line ends around it). Order of reading: priority, star, estimate,
reminder, amount, `@bot`, `#project`, repeat, date; what is left is the title.

| Kind | Tokens (EN · ES) | Result |
|---|---|---|
| priority | `!!!` `!urgent` `!urgente`; `!!` `!high` `!alta`; `!` `!medium` `!media`; `!-` `!low` `!baja` | urgent · high · medium · low |
| priority words | urgent, asap, urgente → urgent; alta → high; baja → low — **only as the first or last word** ("dar de baja el seguro" keeps "baja") | as left |
| star | `*` · `!star` · `!fav` | `starred: true` |
| estimate | `~30m` `~2h` `~1h30` `~90min` `~1,5h` | minutes, 1–`TASK_ESTIMATE_MAX_MINUTES` |
| reminder | `^9am` `^17:30` `^1h` `^1h before` `^30m antes`; remind me at 9 / 1h before; recuérdame / avísame a las 9 / 1h antes | `reminder_at`; "before" needs a due (09:00 for a day-only due) |
| repeat | daily, every day, cada día, todos los días; weekdays, every weekday, entre semana, laborables; every Monday (and Thursday), cada lunes (y jueves), todos los lunes; weekly, semanal, cada semana; monthly, mensual, cada mes; monthly on the 1st, every month on the 15th, el día 1 de cada mes; yearly, anual, cada año; `… at 9` | a Madrid cron; with no date, the due is the first occurrence |
| assign | `@Scout`, `@Money Bot` (longest known name) | `assignee`, confirm chip |
| project | `#Renovation`, `#Casa Nueva` (exists) | exact or ask |
| amount | `€200` `200€` `$12.50` `£12,50` `1.200€` `€1,200.50` | the budget slice (needs the project; same currency) |

- Amounts: one separator followed by exactly 3 digits is thousands (`1.200`, `1,200`); with both,
  the last one is the decimal (`1.200,50`, `1,200.50`); 1–2 digits after one separator is the decimal.
- "every 2 weeks", "every other day" and anything a 5-field cron can't say is an **ask** chip
  ("Repeats can be daily, weekdays, weekly, monthly or yearly"); × puts the words back in the title.
- A warning never blocks: "Two priorities: kept !low". An ask blocks Enter until fixed or ×.

## 4. The expense line, `roost/money/expense_line.py`

`€12 lunch #Trip yesterday vendor:Mercadona *` · `12,50€ comida #Viaje ayer tienda:Mercadona` ·
`€9,99 Netflix #Casa monthly`. Tokens: amount (required; its sign sets the currency, else the project's),
`#project` (exact or ask; a project page passes its own), a past day (§2 backwards), `vendor:X` /
`tienda:X` (quotes for spaces: `vendor:"El Corte Inglés"`), `*` (star), a repeat word (monthly, weekly,
yearly, cada mes, …: makes a repeating expense, §5). The rest is the note. The vendor token is a word,
not `~`, because `~` already means an estimate in the task line: one sign, one meaning.

## 5. Repeating expenses — lazy, idempotent, no scheduler

A rule (`money_recurring`) holds project, amount, currency, note, vendor, cadence (`weekly | monthly |
yearly`), anchor day, `next_due` (a Madrid day) and `ends_on`. **When money is read**
(`MoneyService.summary`, `list_expenses`, project detail, reports, and the bots' money tools, which go
through the same service), `RecurringService.catch_up(user_id, today)` makes each due charge with
`spent_at = occurrence`, in one transaction per rule: `INSERT OR IGNORE` on the unique index
`(user_id, recurring_id, occurrence)`, then `next_due` advances by compare-and-swap on its old value.

Why lazy: money is only ever seen when read, and a charge's day is its occurrence day, not when the row
was written, so a late write gives the same sums. The unique index makes two tabs (or a tab and a bot)
reading at once harmless; the CAS stops a double advance. It works after the Mac slept and does not wait
for Routines. Limits: at most `RECURRING_CATCH_UP_MAX` (24) charges per rule per read; a rule whose
project is archived is skipped (not advanced); deleting a project deletes its rules; a voided or deleted
charge is never re-made (the index still holds its row). "Upcoming charges" lists each rule's next
occurrences within `UPCOMING_CHARGES_DAYS` (31) per project, not yet made, never summed into spent.

## 6. Schema (one migration, "tasks and money polish")

v16 is R1 (`bots.group_label`); v17 is claimed by both computers-2 (`site_logins`) and Routines. This
takes **the next free number after them** — written `18` in the plan, re-numbered at build time (19 if
both take one). The previous version's schema is frozen as a fixture first, as every migration does.

- `tasks.starred INTEGER NOT NULL DEFAULT 0` (a flag, like `money_expenses.is_favorite`);
  `tasks.estimate TEXT` (`enc:v2`, AAD `tasks:estimate`, minutes as text).
- `money_recurring`: `id, user_id, project_id (FK cascade), amount (enc:v2), currency, description
  (enc:v2), vendor (enc:v2), cadence (enc:v2), anchor_day, next_due, ends_on, created_at, updated_at,
  deleted_at, created_by_bot, tainted`; index `(user_id, project_id)`, `(user_id, next_due)`.
- `money_expenses.recurring_id TEXT`, `money_expenses.occurrence TEXT`; unique index
  `(user_id, recurring_id, occurrence) WHERE recurring_id IS NOT NULL`.

## 7. Screens (only Board, project pages, money and tasks components)

- **Tasks tab:** views Today · Upcoming · Overdue · Someday · Done (`ui/Tabs`), a search box, sort
  (Due · Priority). Row menu: Tomorrow, +1 day, Next week, "Pick a day…" (typed words through
  `/api/dates/parse`). Overdue shows "Move all overdue to today" with Undo. Completing shows Undo.
  Chips: how a repeat goes ("every Monday 09:00", from the server's `repeat_text`), star, estimate,
  tags; the reminder chip comment is made true (the row has no reminder chip; the drawer shows it).
- **Quick lines:** chips as you type (× each), autocomplete on `#` (projects), `@` (bots) and `!`
  (levels and star): ↑/↓ move, Tab or Enter accepts, Esc closes. A "?" `ui/Popover` lists every token
  with an EN and ES example, one column on a phone.
- **Money tab:** the expense line on top (the form stays for a task's drawer, with the `Button` kit,
  a currency-aware placeholder, `$`/`£` accepted, and its copy fixed for past days); each row edits in
  place (amount, note, day, project, vendor), shows its vendor, and deletes with Undo; Void gets Undo.
  A "Reports" section (lazy): 6-month trend per currency, the month by project (bars, own currency),
  "Export CSV". The **General inbox**: General's expenses with checkboxes and "Move to…" (Undo).
- **Project page, Money tab:** the expense line with the project fixed, "Upcoming charges", and its
  repeating expenses (Stop, Edit amount).

## 8. Security and integrity

Expense edit, delete, restore and bulk move, and the tasks' move-overdue / restore-dues, all name
`user_id` in every `WHERE`; another user's id is 404 (single) or the whole batch refused with 404 and
nothing written (bulk). A move goes only into the user's open, non-archived project; an expense linked
to a task can't leave that task's project (`project_conflict`). Bulk writes are one transaction with a
rowcount check. CSV cells starting with `= + - @` are prefixed with `'`. These routes get one
security review (plan, Batch B).

## 9. Hand-off to Routines

For `docs/plans/2026-10-20-roost-routines-plan-design.md` to pick up, using this round's data:
- **Reminders:** a scheduler pass reads `tasks.reminder_at` and `pre_reminders` (UTC ISO, index
  `idx_tasks_user_reminder`) and sends them; this round only *sets* them (line `^…`, drawer, `TaskIn`).
- **End-of-day summary:** `roost/tasks/day_summary.py` exists, tested and unused; a daily routine
  posts its text as a Report. The task views (`roost/tasks/views.py`) give Today/Overdue for it.
- **Budget alert Reports:** once per project per month when `projects.numbers` tones cross warn/over;
  it reads money through `MoneyService`, so repeating charges are already made (§5).
- **Assigned tasks (`owner` = a bot id)** could be offered to a routine; not needed now.
Out of scope entirely: OCR, bank import, any AI reading of keystrokes.
