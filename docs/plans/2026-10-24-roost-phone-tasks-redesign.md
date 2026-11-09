# Phone Tasks redesign (2026-10-24)

The owner, 2026-10-24: Tasks on the phone "looks rough", the tab line is "awful", a selected project
chip could not be read, and Tasks should open on **all** tasks with chips on top that filter. Visual
reference: Todoist; ideas only from TaskForge (no code or assets). Projects and Money pages stay as they are.

## What changed

**Opens on all open tasks, in day sections.** Overdue (red, with a Reschedule action that runs the
existing reschedule-all-overdue flow with Undo), Today, Tomorrow, then each later day ("Tue 27 Oct"),
then No date. Done tasks get their own last section when the Done chip is on. Each header is bold 16 with
its count in grey; a tap folds the section (animated chevron and size). Pull to refresh.

**The tab line is gone.** The top bar holds "Tasks" with a small count of what the list shows, a layout
menu (List · Kanban · Calendar; Calendar opens the Workspace's Calendar) and ⋯ (Clear filters, All
projects, All money). Under it, one sideways-scrolling row of 32px toggle chips:
Today · Overdue · Upcoming · High priority · No date · Done, a thin rule, every project with its colour
dot (pinned first, archived left out), and No project (the old Inbox). Date chips and Done combine as
OR; High priority (urgent and high) and projects each narrow (AND across groups; projects OR among
themselves). No chip on means All. While any chip is on, a first "✕ n" chip says how many and clears
them, so a filter is never hidden off-screen. Overdue lights red, High priority amber, the rest the
accent; each lit chip shows a ✓. The chips are kept on the phone (the same small storage the
notification settings use); a storage problem only means they start empty.

**Rows like Todoist.** A round check whose ring and faint fill show priority (urgent red, high orange,
medium blue, low grey); a tap fills it with a tick and a small pop, then finishes the task with Undo.
Title up to two lines, then a meta line: the due in colour (overdue red, today green, tomorrow violet,
later grey, with the time when set), a repeat mark, steps "1/4", and the project's name and dot on the
right (tap opens the project). Inset hairline dividers, no borders, at least 56px tall. Swipe right
finishes (green, Undo in the snackbar); swipe left opens the reschedule sheet (violet). Tap opens the
task drawer; long-press keeps the Move / Reschedule / Delete menu. These rows are the Tasks list's own
(`TodoRow`); the project page keeps its `TaskRow`, as asked.

**Empty states.** An icon and one line: "All clear. Nothing on your list.", "All clear for today" (only
Today on), "No tasks match these filters" with Clear filters, or "No task matches “…”" for typed words.

**The bottom bar's picker row** (Date · Project · Priority · Repeat · Remind · ?) shows only on Tasks and
the Calendar, never on Notes.

## The visibility bug

`buildTheme` never set `secondaryContainer` / `onSecondaryContainer`, so Material drew a selected
ChoiceChip's label in the default `onSecondary`, black. The old project chips set the dark accent tint
as their selected colour: black on near-black, 1.25:1. The theme now sets the tint and the accent's soft
shade, which fixes every ChoiceChip in the app (Kanban groups, New bot, avatar editor). Tests compute
WCAG contrast from the tokens for every chip state in every accent (≥4.5:1) and render a selected chip.

## Why no server change

`GET /api/tasks?sort=due` (no view) already answers every open task, sorted by due then priority, each
with the server's `due_bucket` (Madrid's day). The phone loads that one list and filters it locally, so a
chip tap is instant and needs no request; `view=done` is asked only while Done is on. Sections use
`due_bucket` for Overdue / Today / Tomorrow and the due day for later ones, so the phone never decides
what "today" is.

## Files

`mobile/lib/workspace/tasks/`: `task_filter.dart` (the immutable filter and its rules),
`task_sections.dart` (grouping), `filter_store.dart` (kept chips), `tasks_data.dart` (the lists),
`filter_bar.dart` + `filter_pill.dart` (chips), `task_list.dart` + `section_header.dart` +
`tasks_empty.dart` (the list), `todo_row.dart` + `todo_meta.dart` + `todo_check.dart` (rows),
`tasks_header.dart` (title, layout menu, ⋯), `work_projects.dart` (was `work_tabs.dart`; the tabs are
gone). Tokens gained the priority, due, swipe and tint colours and the list sizes.

## Open for the owner

- Comment counts are not on the rows: the task list does not carry them, and adding them means a count
  query per list. Worth it?
- Medium is the default priority, so most rings are blue (as specified). Todoist keeps its default grey;
  say if grey for medium reads better.
- The project page still uses the older row; it can switch to the new one if you like it here.
