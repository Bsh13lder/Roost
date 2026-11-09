# roost_mobile

A new Flutter project.

## Getting Started

This project is a starting point for a Flutter application.

A few resources to get you started if this is your first Flutter project:

- [Learn Flutter](https://docs.flutter.dev/get-started/learn-flutter)
- [Write your first Flutter app](https://docs.flutter.dev/get-started/codelab)
- [Flutter learning resources](https://docs.flutter.dev/reference/learning-resources)

For help getting started with Flutter development, view the
[online documentation](https://docs.flutter.dev/), which offers tutorials,
samples, guidance on mobile development, and a full API reference.

## Workspace (replaces the Board on the phone)

Home's grid button opens the Workspace (`lib/workspace/`, route `/board`): one fixed bottom bar ("Add or find
anything…" filters the view as you type; Enter or + adds the line as a task through `POST /api/tasks/parse`) with
Tasks · Notes · Calendar.

- Tasks: Today · Inbox · Upcoming, More (Overdue with Reschedule all, Someday, Done, All projects, All money), project
  chips, rows (check with Undo, project pill, due chip, priority mark; long-press: Move to project, Reschedule,
  Delete), and List · Kanban.
- A project pill opens the project page: stats, its tasks, then Money (Add expense, Top-ups, expenses and income).
- Calendar: a Monday-first month grid with dots, a fold-to-week handle, the day's agenda with a now line, day notes.
- Notes: one tree of notes and documents, a folder per project plus No project; the folder+ writes a new note.

Built earlier: the task drawer (properties, steps, money, comments, activity).

Not yet:
- Pasted list ("Add N tasks?", `POST /api/tasks/parse-many`).
- Handing a task to a bot from the quick line (the app says to use the web).
- Repeat, reminder and estimate editing in the drawer; tags and the Keep button for web-marked tasks.
- Comments on one step (the API supports `step_id`).
