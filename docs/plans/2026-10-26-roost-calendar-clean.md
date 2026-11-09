# The clean calendar (owner request, 2026-10-26)

> "in calendar for example I opened there is noise text. I need calendar view and what day what task has, bot,
> where reminder, where routine, where what ok?"

## The noise

- **Phone app** (`mobile/lib/workspace/calendar/`): the grid's grey dots said only "something", and the agenda
  under it mixed day notes, "All day" rows, timed rows, routine lines and a now line in one list, so a day read
  as a run of sentences with no way to tell a task from a routine or see a reminder at all.
- **Web on a narrow screen** (`TaskAgenda.tsx`): a long agenda of every day from today on, each with its
  pills and routine lines, under a sideways strip of day chips.

## What replaces it

1. **A month grid of markers only** (phone `MonthGridView` + `DayCell`; web's narrow `TaskAgenda`), never
   titles. Each day shows up to three task dots (red when late, urgent and high in their priority's colour,
   otherwise the project's colour, grey with none; a done task is a hollow ring) and "+N" past three; then one
   row of a bell (a reminder fires that day), a repeat mark (a routine runs) and the first bot's initial in its
   avatar colour (a bot made a task there or runs a routine). Today is ringed, the picked day tinted. The phone
   keeps its fold-to-one-week handle and swipe.
2. **A day panel** under the grid for the picked day (today to start): its day notes, then **Tasks ·
   Reminders · Routines**, empty sections left out, "Nothing on this day." when all are. Every row is a Madrid
   time ("Late", "All day", "09:30"; a reminder's first time that day, "08:30 +2" when it fires more), the
   title, and the bot and project in one quiet line. A task opens the task drawer; a routine its run log.
3. **One legend line**: Task · Done · Reminder · Routine · By a bot.
4. **Show** (Routines · Done · Made by bots) filters the markers and the panel as before.

Placement is the web grid's: a task sits on its due day, and an open late one on today.

## Reminder days (pure, client side)

`reminder_at` plus each `pre_reminders` entry (a stored UTC instant, or an offset like `-30m` / `-1d2h`
against `reminder_at`), only for open tasks (the reminders job fires nothing for a finished one), each turned
into a Madrid day and clock (`mobile/lib/workspace/calendar/day_marks.dart`, `web/.../calendar/dayMarks.ts`).

## The one server fact that was missing

`GET /api/tasks?from=&to=` listed tasks by due day only, so a reminder that fires inside the month on a task
due later, or on a task with no due day, never reached the calendar. `in_range`
(`roost/tasks/views.py`) now also keeps an **open** task whose reminder or advance reminder fires on a Madrid
day inside the range (`reminder_days`). No schema change; the query is the user's own task list, as before.

## Tests

- `tests/test_task_range_view.py`: reminder-only tasks in the range, done ones not; `reminder_days` in Madrid.
- `mobile/test/workspace/calendar_marks_test.dart` (rules) and `calendar_clean_test.dart` (cells, panel,
  legend, the Workspace calendar end to end); old agenda tests replaced.
- `web/tests/TaskAgenda.test.tsx` and the `dayMarks` unit test for the narrow web calendar.
