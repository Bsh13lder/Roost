# Roost — Board redesign (Tasks, Money, project pages), design

> Status 2026-10-21: built. Mockup: `docs/design/board-redesign-mockup.html`
> (open it in a browser; Desktop 1440 and Phone 390 frames, fake data). Screenshots of today's screens:
> `node spikes/board-screens/shoot.mjs` (scripted gateway on 127.0.0.1:5173, temp data, PNGs in
> `spikes/board-screens/out/`, not committed). It changes **no logic** of
> `2026-10-20-roost-tasks-money-polish-design.md` (P1–P12): it gives those features their place, and adds
> Batch G to that plan for what is only about the look.

**User's words:** the Board's Tasks, Money and project pages "look terrible and not informative at all",
and are not as easy as the rest of Roost now looks (P2 chat, R1 shell).

**Clean room:** Todoist, Linear, Things, Copilot Money and YNAB were quality bars only: density, one line
per record, numbers first. No art, icon, layout signature or wording is taken. Words are Roost's
(CLAUDE.md vocabulary); colours, sizes and spaces are `tokens.css` names; controls are `web/src/ui/`.

## 1. What is wrong today (seen at 1440×900 and 390×844, 3 projects, 15 tasks, 25 expenses)

**Everywhere on the Board**
- B1. The page is a 760px column (`--reading-width`) in a 1140px pane: a third of a desktop is empty,
  while every row wraps its chips onto a second line.
- B2. A grey lede sentence and a full-width pill tab bar spend about 110px before any record. No tab
  says how many things wait (no "3 overdue").
- B3. Chips, dates, table text and budget lines are in the **mono** font, lower-case ("project", "spent"):
  it reads like a debug view, not an app. Amounts don't line up.
- B4. Every record is a bordered card with 16px padding: 8 tasks or 9 expenses per screen.

**Tasks tab**
- T1. One flat list, sorted by nothing visible; overdue, today and someday are mixed. No counts.
- T2. A row's chips all look alike: priority, due, project and steps are the same small bordered pill. The
  eye can't find "what's late" or "which project". Project has no colour; priority is a word chip.
- T3. Money is invisible on the Board (only a project page shows a slice, as "€0.00 spent, €250.00 left").
- T4. No row actions until the ⋯ menu (Open, Mark failed). No keyboard. The Add button looks disabled.
- T5. Phone: chips wrap to three lines; a 5-task screen.

**Task drawer**
- D1. A form first: the title twice (heading and field), "List optional", the due as raw `2026-10-20`
  plus a line repeating it, and a mid-form **Save changes**. Steps, money and comments are below the fold;
  the drawer's most useful parts (progress, what's spent) are the least visible.

**Money tab**
- M1. One big number, then a mono table whose third column says "€1,700.20 over €1,500.00": the reader
  must work out which is the limit. No bars on the Money tab at all; bars live only on Projects.
- M2. "Also US$153.00 (not in the total)" is drawn in the warn colour, as if it were a problem.
- M3. The add form is five controls of three heights (the date field is shorter; the calendar icon floats).
- M4. Each expense is a 54px card with an always-visible **Void** button that looks like a status badge.
  No grouping by day, no day total, the project is plain text, nothing is right-aligned in a column.
- M5. No "how is this month going" answer: no top project, no comparison, no upcoming charges.
- M6. Phone: the table squeezes to three wrapped lines per row; the form takes four rows.

**Project page**
- P1. No header card: facts, "0 of 5 done", two bars and three equal pills (Edit · Archive · **Delete**,
  not marked danger) stacked as loose lines.
- P2. "0 of 5 done" while 4 of 9 steps are done and two tasks are overdue: the one stat shown is the
  least informative one.
- P3. The Money tab opens on **Top-ups** and its form (rare) above the month's spending (daily).
- P4. Tabs carry no counts; nothing says the project repeats charges (coming in Task 13).

**Empty states:** one grey line ("Nothing open. Add a task, or ask any bot.") with no picture or action.

## 2. Principles

1. **Numbers first.** Each screen opens with the 3–4 numbers that answer "how am I doing", then the list.
2. **One line per record** on a desktop (≥ 44px rows, hairline separators, no card per row), two short
   lines on a phone. Columns align: due and amount to the right, tabular figures.
3. **Colour means something** (tokens' "meaning, never decoration"): danger = overdue / over,
   warn = high priority / near a limit, ok = today / done / under, accent = selection and progress.
   The only decorative colour is the project's own dot (from data, the 9-colour palette).
4. **Group, don't filter by eye:** tasks by Overdue / Today / day; expenses by day with the day's total.
5. **Quiet until hovered:** row actions, the star and edit appear on hover or keyboard focus.
6. **System sans everywhere**; mono only for `kbd` hints. `font-variant-numeric: tabular-nums` on numbers.
7. **The server reckons every number** (H8): the web never adds amounts, so day totals, counts and tones
   come from the API (see §5, the few small server additions).

## 3. Layout per screen (desktop ≥ 1025px; phone ≤ 768px; 769–1024 = desktop at one column)

**Board shell.** Width `--board-width` (new, 1120px) with `--gutter` sides. Header: "Board" at
`--fs-title`, then a **line tab bar** (underline on the selected tab, `--color-accent-strong`) with a count
after Tasks (overdue + today, the count in `--color-danger` when any is overdue) and Projects. The lede
goes. Header and tabs stick while the list scrolls. Phone: the tab bar scrolls sideways, no clipping.

**Tasks tab.**
- Stat line: Overdue N (`--color-danger`) · Today N · Upcoming N (14 days) · Done this week N, numbers
  at `--fs-display`; each is a button to its view.
- View bar: kit `Chip`s with counts (Today · Upcoming · Overdue · Someday · Done; Today holds the
  overdue group too), then search `Input` and sort `Select` at the right (Task 11).
- Quick line: one `--color-panel` box (`--radius-md`), "+" in accent, the rich-line chips under the input
  (Task 5), "?" opens the token help `Popover`.
- Groups: a heading row (`--fs-label`, 600, count in `--color-text-faint`, hairline under); Overdue's
  heading in danger with **Move all to today** (Task 11).
- Row grid: `check 24 | title 1fr | steps 72 | money 112 | project 150 | due 96 | actions 64`, 44px,
  `--space-3` gaps. Priority is a mark before the title: `!!!` danger (urgent), `!!` warn (high), none
  for medium/low. Steps: a 28px `Meter` (accent) and `2/3`. Money: "€80 left" (or "€30 over" in danger).
  Project: colour dot + name (hidden on a project's own page). Due: Yesterday / 4d overdue (danger),
  Today (ok), Tomorrow (warn), a weekday within 7 days, then "29 Oct" (secondary).
- Hover / focus: the row takes `--color-panel`; actions: → Tomorrow, ⋯ (Reschedule…, Open, Mark failed).
- Keys (shown once under the list, hidden on phones): j/k move, x done, t tomorrow, Enter open,
  / search, q add, 1–5 views, Esc close. Completing and moving show a `Toast` with **Undo** (P9).
- Phone: row = check · title (with priority mark) · due on line 1; project dot, steps, money on line 2.
  Swipe is not added; the row's ⋯ (long-press) holds the actions.

**Task drawer** (kit `Sheet`, right, 460px; phone: R1's `size="full"`).
- Head: a round check, the title editable in place (no second Title field), Close. Under it badges:
  project, due (toned), priority, "Made by …" / "from web content".
- Properties as a two-column list (label `--color-text-faint`, value a quiet button that opens its
  editor in a `Popover`): Due (DateTimePicker), Reminder, Repeat (server's `repeat_text`), Priority,
  Project, List, Estimate.
- Sections, each with a heading and count: Steps (Meter + "1 of 3"), Money (Planned · Spent · Left in
  `--fs-lead`, a toned Meter, the linked expenses, "+ Add an expense for this task"), Comments, Activity.
- Foot: Mark failed (quiet) and **Delete task** (danger, at the far right). **Save changes** shows in the
  foot only while a property is changed and not yet saved; the PATCH calls stay as today.

**Money tab.**
- Month nav (‹ October 2026 ›) with Export CSV at the right (Task 15).
- Four summary cards (`.card`, `--radius-md`, `--space-4`): **Spent this month** (main currency; other
  currencies on the sub-line in secondary, not warn; "+36% vs Sep" from the trend), **Monthly limits**
  ("1 over" in danger / "All on track" in ok; the worst project named), **Top project** (dot, name,
  amount, share), **Coming up · 31 days** (upcoming charges, per currency). Never one sum across currencies.
- Two columns, `minmax(0,1fr) | 340px`:
  - Main: the expense line (Task 7) in the same quick box as tasks (`€` instead of `+`), then the list
    grouped by day: day heading ("Today", "Yesterday", "Sun 18 Oct") with the day's totals per currency
    at the right; rows `star 20 | dot 8 | note + vendor 1fr | project tag | amount 104 | actions 56`.
    Void rows: struck-through, faint, a `void` badge. Repeating rows: a "↻ monthly" badge. Hover: ✎
    (edit in place, Task 9), ⋯ (Void, Delete, both with Undo).
  - Side: **Budgets this month** (one `Meter` per project with a limit, server tone; "Over by €1,700.20"
    under it; a total-only project shows its total bar; no-limit ones a quiet line), **General inbox**
    (count badge, one sentence, **Sort them** swaps the main column to the inbox: checkboxes, "Move to…"
    `Select`, Move, Undo — Task 15), **Last 6 months** (plain SVG bars, one series per currency, its own
    scale and legend, a hidden table for screen readers; Reports opens the full lazy chunk — Task 15).
- Phone: cards scroll sideways (snap, 72% wide), then the line and the list (rows: dot · note over
  vendor · amount), then budgets and inbox; the trend shows only in Reports.

**Project page.**
- Breadcrumb header: ‹ Board / Projects / **Casa Nueva**.
- Header card: dot, name at `--fs-title`, status `Badge` (Active ok / Archived neutral / from web content
  with Keep), **Edit** and ⋯ (Archive, Delete in danger) at the right; facts line (Led by …, start → due,
  "120 days left"). Three stats in a row (one column on a phone), each value at `--fs-title` with a
  `Meter` and a sub-line: **Total budget** (left of total; spent, %, top-ups), **This month** (left or
  "over" in danger; spent, days to go), **Tasks** (done of all; overdue in danger, steps done, planned).
  A **Repeating** strip lists the project's rules as badges ("↻ Home insurance €42 · monthly · next 5 Nov",
  Task 13). Other currencies: one secondary line, not warn.
- Line tabs with counts: Tasks · Money · Notes · Docs.
  - Tasks: the same rows without the project column, grouped Overdue / Next up (7 days) / Later / Done.
  - Money: the expense line fixed to the project and its day list; side: **Coming up**, **Repeating**
    (Edit, Stop — Task 13), **Top-ups** (folded to its list with "Add top-up"; the form opens on demand).
  - Notes / Docs: the existing panels with a quick "New …" line on top.

**Empty states** (kit `EmptyState` with the main bot's robot, P5): Tasks "Nothing here. Nice." + a real
first prompt ("Ask Chief: plan my week"); Money "Nothing spent yet this month" + the line focused;
a project "Add the first task, or ask {lead bot}".

## 4. Components, mapped to the kit

| Piece | Kit / file | Notes |
|---|---|---|
| Board and project tab bars | `ui/Tabs` + new `variant="line"` and `TabItem.count` | one tab style, two weights (P5) |
| View bar | `ui/Chip` (`selected`), `ui/Input`, `ui/Select` | Task 11's `TaskViews.tsx` |
| Stat line, summary cards | new `board/StatLine.tsx`, `board/MoneySummaryCards.tsx` | numbers from the server |
| Task row | `TaskRow.tsx` (grid), `ui/Meter`, `ui/Menu`, `ui/Tooltip` | priority mark, money, project dot |
| Groups | new `board/TaskGroups.tsx`, `board/ExpenseDays.tsx` | headings, counts, day totals |
| Quick lines | Task 5 `QuickAdd`, Task 7 `ExpenseLine` in one `board/QuickBox.tsx` frame | chips = `ui/Badge` |
| Drawer | `ui/Sheet`, new `tasks/TaskProps.tsx`, `ui/Popover`, `ui/date/*`, `ui/Select` | replaces the form grid |
| Budgets | `ui/Meter` (server tone) in `projects/BudgetBar.tsx`, new `board/BudgetList.tsx` | replaces `ProjectTable` |
| Trend, inbox | Task 15's `TrendChart.tsx`, `GeneralInbox.tsx` | side column |
| Header card | new `projects/ProjectHeaderCard.tsx` (`Badge`, `Button`, `Menu`, `Meter`) | replaces Head + Summary + Actions |
| Toasts with Undo | `ui/Toast` `action` (Task 9) | |
| Empty states | `ui/EmptyState` + `components/robot` | |

**Type:** page title `--fs-title`/650; section and card titles `--fs-body`–`--fs-heading`/600; row text
`--fs-body`; meta, counts, sub-lines `--fs-caption`/`--fs-label`; stat numbers `--fs-display` (Tasks),
`--fs-title` (cards, header card). **Space:** rows 44px with `--space-2` side padding and `--space-3`
gaps; cards `--space-4`/`--space-5`; groups `--space-5` apart; page top `--space-6`. **Surfaces:**
page `--color-bg`; cards and hovered rows `--color-panel`; inputs `--color-raised`; drawer, menus,
toasts `--color-overlay`; hairlines `--color-border`. **Radii:** cards `--radius-md`, inputs
`--radius-sm`, badges and chips `--radius-pill`.

**New tokens (3), added to `tokens.css` once R1 has landed (R1 owns that file):**
`--board-width: 1120px` (layout), `--color-ok-tint: rgb(52 211 153 / 0.12)` and
`--color-warn-tint: rgb(245 165 36 / 0.12)` (badge backgrounds, like `--color-danger-tint`).
`tokens.test.ts` keeps its 4.5:1 check (`--color-ok`/`--color-warn` text on these tints passes on panel).

## 5. Where each part lands in the Tasks & Money plan

| Part of this design | Plan task |
|---|---|
| Quick-line chips, autocomplete, "?" help inside the quick box | Task 5 |
| Expense line in the quick box; vendor on the row | Task 7 |
| Row ✎ edit in place, ⋯ Void/Delete, Undo toasts | Task 9 |
| View chips, search, sort, Tomorrow / Reschedule…, Move all to today, Undo | Task 11 |
| Repeating strip, Coming up and Repeating cards, ↻ badge | Task 13 |
| Trend card, Reports, Export CSV, General inbox card and mode | Task 15 |
| Everything else (shell, rows, groups, drawer, cards, header card, phone) | Batch G below |

**Server additions Batch G needs (small, read-only, inside the plan's own routes):** with Task 10, the
views response carries `counts` (overdue, today, upcoming_14, someday, done_week) and each task's
`money` (planned / spent / left, as `task_money` today) so the Board's rows show it; with Task 8,
`GET /api/money/expenses` returns `day_totals` (per day, per currency); with Task 12, an all-projects
upcoming list for the "Coming up" card; `by_project` rows gain the server's `tone` and `used_percent`
(from `projects/numbers.py`); a project's `progress` gains `overdue`, `steps_done`, `steps_total`.

## 6. Batch G: Board redesign (add to `2026-10-20-roost-tasks-money-polish.md`)

Order: **G1 before Task 5** (later web tasks build into the new shell), G2–G3 with Task 11, G4 any
time, G5–G6 with Tasks 7/9/15, G7 with Task 13, G8 before Task 16. Each: red → green → `npm test &&
npm run build && npm run size`; new CSS appended to `board.css` / `tasks.css` / `projects.css` (≤ 800
lines; split into a new file only after R1 has landed, with its `styles.css` import).

- **G1. Board shell and line tabs.** Modify `web/src/ui/Tabs.tsx` (`variant?: "pill" | "line"`,
  `TabItem.count?: number`), `web/src/pages/Board.tsx` (no lede, `--board-width`, sticky head, Tasks
  count), `web/src/styles/ui.css`, `board.css`, `tokens.css` (3 tokens, after R1). Tests: `Tabs.test.tsx`
  `it("draws a count and keeps it out of the accessible name")`, `it("line variant scrolls, never clips")`;
  `Board.test.tsx` `it("shows the overdue count on Tasks")`; `tokens.test.ts` green.
- **G2. The task row as one line.** Modify `board/TaskRow.tsx`, `board/taskChips.ts` (`dueTone`:
  over/today/soon/later), `tasks.css`; create `board/PriorityMark.tsx`. Tests (`TaskRow.test.tsx`):
  `it("marks urgent !!! and high !! and nothing for medium")`, `it("shows money left, or over in danger")`,
  `it("hides the project column on a project page")`, `it("shows actions on focus")`.
- **G3. Groups, stat line, keys.** Create `board/TaskGroups.tsx`, `board/StatLine.tsx`,
  `board/useTaskKeys.ts`; modify `TasksBoard.tsx`. Server: `counts` + per-task `money` on the views
  response (`roost/tasks/views.py`, `routes/tasks.py`, `tests/test_task_views.py`
  `test_counts_match_the_views`, `test_view_rows_carry_money`). Tests: `it("groups Today as Overdue then
  Today")`, `it("Upcoming groups by day")`, `it("j/k/x/t/Enter work and never fire inside an input")`.
- **G4. The drawer as properties.** Create `tasks/TaskProps.tsx`; modify `tasks/TaskDrawer.tsx`,
  `TaskDetailsForm.tsx` (to the property editors), `TaskMoneyPanel.tsx` (Planned · Spent · Left + Meter),
  `tasks.css`. Tests: `it("edits the title in the head")`, `it("each property opens its editor in a
  popover")`, `it("Save shows only while something changed")`, `it("Delete is danger")`.
- **G5. Money summary and budgets.** Create `board/MoneySummaryCards.tsx`, `board/BudgetList.tsx`;
  modify `MoneyBoard.tsx` (two columns), `BudgetBar.tsx` (kit `Meter`), `board.css`. Server: `tone`,
  `used_percent` on `by_project` (`roost/money/service.py`, `tests/test_money_summary.py`
  `test_by_project_carries_tone`). Tests: `it("never sums two currencies in a card")`,
  `it("names the worst project under Monthly limits")`, `it("other currencies are secondary, not warn")`.
- **G6. Expenses by day.** Create `board/ExpenseDays.tsx`; modify `ExpenseList.tsx` (row grid, hover
  star/actions), `board.css`. Server: `day_totals` on the list (`routes/money.py`,
  `test_day_totals_per_currency`). Tests: `it("groups by Madrid day with the server's totals")`,
  `it("a void row is struck through with a badge")`, `it("amounts align right")`.
- **G7. The project header card and tabs.** Create `projects/ProjectHeaderCard.tsx`; modify
  `pages/Project.tsx` (breadcrumb, line tabs with counts, Money tab order), `ProjectSummary.tsx`,
  `ProjectActions.tsx` (⋯ menu, Delete danger), `TopupHistory.tsx` (folded), `projects.css`. Server:
  `progress.overdue/steps_done/steps_total` (`roost/projects/numbers.py`,
  `test_progress_counts_overdue_and_steps`). Tests: `it("shows three stats with meters")`,
  `it("Archive and Delete live in the menu, Delete in danger")`, `it("Top-ups sit below the spending")`.
- **G8. Phones, empty states and screenshots.** Modify `tasks.css`, `board.css`, `projects.css`
  (≤ 768px rules), the three boards' empty states (`ui/EmptyState` + robot). Create
  `web/e2e/board-look.spec.ts`: `test("no horizontal scroll at 390 on Tasks, Money and a project")`,
  `test("the drawer is full screen on a phone")`, `test("rows stay one line at 1440")`.

## 7. User additions (2026-10-20)

Approved after the first mockup; all of them are in `docs/design/board-redesign-mockup.html` (Desktop and Phone frames).

**Tasks**
1. **Subtasks open per task.** Clicking a task's step chip ("2/5", with a small chevron) expands or collapses that task's steps inline,
   each with its own tick (click toggles it), done steps struck through; the meter stays. Every task keeps its own open or closed
   state (kept in the view, not on the server). The toolbar's ⋯ menu has a secondary "Expand all / Collapse all subtasks". It works in
   List, in Kanban cards (the card expands) and on the phone. (This replaces the earlier global "Show subtasks" switch.)
2. **Layout switcher List · Kanban · Calendar** next to the views.
   - *Kanban:* columns To do, On it, Done, or grouped by project or priority (a "Group" select). Cards show title, urgent flag pill,
     due, project dot, step progress. Drag a card to another column, or use the card's "Move to…" menu (keyboard and phone).
   - *Calendar:* month grid with a Week toggle. Tasks are chips on their due day, coloured by project; urgent ones carry the flag;
     overdue ones sit on today with a red mark and "Nd". Clicking an empty day or its "+" opens a popover quick add
     ("Add task on Wed 21 Oct") with the same quick line and chips, date pre-filled. Dragging a chip to another day reschedules it.

**Money**
3. **Pinned** section on top: starred expenses (★) and pinned projects as compact cards; pinned projects show their budget bar.
   "Spent this month" stays.
4. **Switcher List · By days · Calendar**, with "Today: €X" beside it.
   - *By days:* a strip of daily bars for the month (today bright, height = that day's euro spending), a list of days with totals,
     other currencies apart. A bar or a day filters the expense list to that day, with a Clear chip.
   - *Calendar:* month grid, each day with its total (other currencies on their own line, never summed). Click a day for its
     expenses in a side list; "+" opens the expense quick line with the date pre-filled ("€12 lunch #Trip" on Wed 21 Oct).
5. **Date filter** beside the switcher: Today, This week, This month, Last month, Custom range (a From-To calendar popover).
   The list and the By days strip show only that range, with a summary ("12 expenses · €340.20", other currencies apart) and a Clear chip.

**Round 3 (calendar polish, day notes, Kanban groups)**

6. **Calmer calendars (Tasks and Money).** Month cells are rounded cards with a clear date number, an accent ring on today, dimmed
   weekends, faded days of other months and a small hover lift. A task is a compact pill: project-colour left edge, time ("09:00") if
   any, truncated title; urgent gets the flag, done is struck through, overdue gets a red tint. Past 3 items the cell shows
   "+N more", which opens a day popover with everything. A tiny corner summary shows a count dot and that day's euro spending.
   **Week view:** day columns, an all-day row on top and a 07 to 22 time grid; timed tasks sit in their slot. The Money calendar
   uses the same cells (total, other currencies on their own line, expense count).
7. **Day notes.** Every day can hold a short note written by you or by a bot; each line shows who wrote it ("You" or a tiny robot
   avatar and the bot's name). The calendar marks a day with a note icon (SVG); the day popover has a "Day note" section and an
   "Add a note for this day" field; on the phone the note sits under the date header of the agenda.
   **New small task (server):** `day_notes` store (`id, user_id, day, author_kind, bot_id, text, created_at`), the text sealed
   (`enc:v2`, AAD `day_notes:text`), every query scoped by `user_id` (404 for another user's note), routes
   `GET/POST /api/day-notes?from&to` and `DELETE /api/day-notes/{id}`, and a bot tool `add_day_note(day, text)` with gate kind
   `write_create`. Schema version to be taken when the task is scheduled. Lands in **G9** (calendar UI) plus new **G11. Day notes**.
8. **Many Kanban layouts.** "Group by" with Status, Due date (Overdue · Today · Tomorrow · This week · Later · No date), Project,
   Priority, Bot (who made it or is assigned, plus "You") and List; "Sort cards by" Due date, Priority, Newest, Oldest, Title A–Z,
   Money left. Columns show counts, collapse, and have a "+" that pre-fills the group's value (the Tomorrow column sets the due date;
   the Casa column sets `#Casa`). An optional **"Split by project" (one row per project, columns by status)** switch gives rows by project with columns by status. Dragging between
   columns updates the grouped field (in a lane it also sets the project); "Move to…" stays. Lands in **G9**; the bot/assignee column
   needs a `tasks.assignee_bot_id` read from the existing created-by data (small server read, noted for G9).

**Round 4 (per-task subtasks, rescheduling)**

9. **Reschedule popover** wherever a due date changes: the overdue group's "Reschedule all", a row's "→" and its ⋯ → "Move to…", the
   Kanban card menu's "Reschedule…", the drawer's Due property, and a "→" on calendar chips where dragging is not possible (phone
   agenda, day popover). It holds quick picks (Today, Tomorrow, This weekend, Next Monday, Next week, +1 week, No date, each with its
   date), a mini month calendar to pick any day, and an optional time field (`HH:MM`, checked). Picking applies at once and shows
   an Undo toast. Lands in **G2** (row and group header) and **G9** (Kanban, calendar), as one shared `board/ReschedulePopover.tsx`
   built on `ui/Popover` and the lazy `DatePicker` calendar; it calls the existing task update route (`due`, `due_time`).

**Phone:** Kanban is horizontal swipeable columns; both Calendars become an agenda list under a small month strip.

**Mapping to the Tasks & Money plan's Batch G** (`2026-10-20-roost-tasks-money-polish.md`):

| Addition | Lands in |
|---|---|
| Per-task subtasks (step chip toggles, ⋯ Expand/Collapse all) | G2 (task row; `board/TaskRow.tsx` renders `SubSteps`, open ids kept in the Tasks view) |
| Kanban and Calendar for tasks | new **G9. Task layouts** (`board/TaskKanban.tsx`, `board/TaskCalendar.tsx`, shared `board/CalendarGrid.tsx`, quick-add popover reusing `QuickAdd`); drag by native HTML5 drag, "Move to…" as a `ui/Menu`; phone rules in G8 |
| Pinned, By days, date filter, Money Calendar | G5/G6 plus new **G10. Money views** (`board/PinnedCards.tsx`, `board/ExpenseDaysChart.tsx`, `board/ExpenseCalendar.tsx`, `board/DateRangeFilter.tsx`); the range and day totals come from the existing read-only expense routes with `from`/`to` params, currencies summed per currency |
| Phone agenda and swipe columns | G8 |

## 8. Out of scope

Projects-tab list and Notes/Documents tabs (they keep today's look, inheriting the shell); a light theme
(V4); drag to reorder; swipe gestures; any change to the parsers, money rules or schema beyond §5's
read-only fields.
