# Board toggles: routines on the calendars, Show / hide, who made it (2026-10-26)

The owner's request, in their words: "routines in calendar ... with togle hide show like same hide show to executed
task and agent created task lets add agent name for we knew from where comes".

No schema change. Server, web and phone.

## 1. Routines on the calendars

**Server.** `GET /api/routines/occurrences?from=YYYY-MM-DD&to=YYYY-MM-DD[&bot_id=]` (`roost/gateway/routes/routines_hub.py`)
returns the upcoming run times of the user's enabled routines on those Madrid days:

```json
{"occurrences": [{"routine_id": "…", "routine_name": "Morning news", "bot_id": "…", "bot_name": "Gela",
                  "at": "2026-10-27T08:00:00Z", "day": "2026-10-27", "time": "09:00", "log_thread_id": "…"}],
 "truncated": false}
```

- `CurrentUser`; every read is scoped by `user_id`. `bot_id` narrows to one bot; another user's (or an unknown) bot is
  404.
- Paused routines are left out. Runs already past are left out (the window starts at `max(Madrid midnight of from,
  now)`; a slot due this very minute still shows). Times are schedule slots without the jitter.
- At most `ROUTINE_OCCURRENCE_SPAN_DAYS_MAX` (62) days (422 "Pick at most 62 days."), `to` before `from` is 422
  ("The last day comes before the first."), a malformed day 422. At most `ROUTINE_OCCURRENCES_MAX` (400) times,
  earliest first, with `truncated: true` when cut (a 15-minute cron fills a month quickly).
- The pure work is `roost/routines/occurrences.py` (`madrid_span`, `occurrences_between`, `Occurrence`,
  `OccurrencePage`) over the existing `slots_between`; `RoutinesHub.occurrences` (`roost/routines/hub.py`, now with a
  `clock`) adds the names and the bot check.

**Web.** `listRoutineOccurrences` (`web/src/api/routines.ts`); `groupRoutineDays` (`web/src/lib/routineDays.ts`) folds
the rows into one entry per routine per day ("09:00 +3" when it runs more that day); `useRoutineDays`
(`web/src/components/board/calendar/useRoutineDays.ts`) loads the visible span, again on `routines_changed`, and a
failed load only leaves the routine lines out. `RoutineChip` / `RoutineLines` draw a quiet dashed line (repeat mark,
Madrid time, name, bot) that links to the routine's run log (`/bots/:botId/routines/:routineId/log`).
- The Workspace's Calendar (`workspace/calendar/WorkspaceCalendar.tsx`): the month's day cells get a hollow ring on a
  day a routine runs (and "N routines" in the cell's name), the picked day's agenda lists the runs among the timed
  tasks (`agendaItems` now takes routines); the week grid lists them in each day's All day row.
- The Tasks Calendar grids (`board/calendar/TaskCalendar.tsx`): a month cell shows two routine lines then
  "+N routines" (`CAL_CELL_MAX_ROUTINES`); the week shows them in All day (`WeekGrid` `extras`); the phone agenda
  (`TaskAgenda.tsx`) lists them under the day's tasks and counts such a day as having something.
- A bot's Plan calendar (`plan/PlanCalendar.tsx`, given `botId` by `PlanView`): only that bot's routines
  (`bot_id=`), counted in the day's corner and listed under the day's items without the bot's name.

**Phone.** `RoutinesRepo.occurrences`, `groupRoutineDays`, `routineDaysProvider` (keyed by `(from, to, botId)`,
reloads on `routines_changed`, a failure is no lines) and `RoutineLine` (taps to the run log) in
`mobile/lib/routines/occurrences.dart`. The Workspace calendar (`workspace/calendar/calendar_view.dart`) counts runs in
the month grid's dots and the day's agenda (`day_agenda.dart`) puts them among the timed tasks around the now line. The
Plan's Calendar view (`plan/plan_agenda.dart`, `PlanCalendarPane`) lists that bot's runs for the next 14 days
(`planRoutineDays`) among its items.

## 2. Show / hide

Defaults: everything shows, except that Show finished keeps its old default (off) where it already ruled.

**Web.** `useScreenToggle(screen, toggle)` (`web/src/hooks/useScreenToggle.ts`) keeps one choice per screen and toggle
in `localStorage` (`roost.show.v1.<screen>.<routines|botMade|done>`, `"1"`/`"0"`), every read and write in try/catch
(a refused write lasts the visit), shared live between readers and tabs. Screens: `board-list`, `board-kanban`,
`board-calendar`, `project`, `plan-calendar` (`SCREEN_*` in `board/constants.ts`). `ShowToggles`
(`board/ShowToggles.tsx`) draws the switches with the `ui/Switch` kit:
- Tasks list / Kanban / project page (`TasksBoard` head): Show finished (unchanged, still one shared key, off by
  default, not on the Done view) and **Made by bots**, which hides bot-made rows (`keepMade`, `web/src/lib/madeBy.ts`,
  in `useBoardList`) and says "N by bots hidden".
- The Workspace's Calendar: **Routines · Done · Made by bots**, its own Done (default on, which is what the month view
  showed before) ruling both the month and the week grid (`ownDone` on `TaskCalendarProps`; `useShownCalendarTasks`).
  The Tasks board's calendar layout keeps Show finished for Done and shares the calendar's Routines / Made by bots.
- The Plan calendar: **Routines · Done** (done items hidden when off).

**Phone.** `ScreenToggles` / `screenTogglesProvider` (a family by screen) / `ShowMenuButton` in
`mobile/lib/workspace/show_toggles.dart`, kept in the app's existing key-value store (`FlutterForegroundTask` data,
`roost_show_<screen>`, as the Tasks chips are; a storage problem shows everything). Screens `tasks`, `kanban`,
`calendar`, `plan`. The Show button (a ticked menu) sits in the Tasks top bar on the list (Made by bots; Done stays the
existing Done chip) and on the Kanban (Done · Made by bots, its own `kanban` choices, both on by default so the Done
column fills as before; `kanbanShown` in `board/tasks/kanban_groups.dart`), the calendar header (Routines · Done · Made by bots) and over the Plan's Calendar view (Routines · Done).

## 3. Who made it

Kept on the client, as the web already did: `task_out.created_by_bot` mapped to the bot's name from the live bots list
(a retired bot's tasks carry `NULL`, so no name). Web: `MadeByChip` on rows (unchanged), and now the calendar pill
(`TaskPill`, "· Gela" and "by Gela" in its words) and the Workspace agenda line ("· by Gela"). Phone:
`TaskItem.createdByBot`, a small robot-icon name in the row's meta (`todo_meta.dart`, `todo_row.dart`) and in the
calendar agenda row.

## Not done

- A month cell's "+N more" day popover on the web lists tasks only, not routine runs.
