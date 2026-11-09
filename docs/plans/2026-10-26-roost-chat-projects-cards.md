# Chat: #project, task cards, reminder cards and a quieter web mark (2026-10-26)

Owner, 2026-10-26: "when I ask tasks projects even in chat # is project name and when I tape comes out project if I
text something about it means that project when I ask task for it showed me beautiful and lets upgrade little the
quality of that web content mark. Up is ugly". Added the same day: "card was ugly ... should be card Done failed
reschedule Skip" (a task reminder in the chat).

No schema change (the reminder answer lives in the Report's sealed JSON body, §3). One new message kind (`task_cards`, the `messages.kind` column has no CHECK) and one optional field
on `ReportBody` (`task_id`).

## 1. #project in a bot's chat

- **Typing.** In a bot's chat composer (web `Composer` with `projects`, phone `chat_screen.dart`), `#` at the start of
  a word opens a list of your projects (General never listed), filtered as you type; Enter/Tab/tap inserts
  `#Project Name `. `@` keeps listing your other bots. Shared code: web `lib/mentions.ts` and
  `components/chat/useMentionPicker.ts`, phone `lib/chat/mentions.dart` (both now take a trigger).
- **In the message.** The message stays plain text: no sealed field, no migration. Your bubble draws each known
  `#Name` as a chip that opens the project (web `ProjectText.tsx` + `lib/projectTokens.ts`, phone `ProjectText` in
  `message_view.dart` + `lib/chat/project_tokens.dart`); an unknown `#word` stays text.
- **The server.** `roost/projects/chat_refs.py`: `chat_projects(text, projects)` reads `#Name` exactly against the
  user's own projects (any case, longest name first, never inside a word, General ignored, each once, at most
  `CHAT_PROJECTS_PER_MESSAGE_MAX`). `turn._prepare` reads the user's fresh messages (their own texts since anything
  else was said) and `build_instructions` gets one trusted line per project: "The user means the project “Name” (id
  …) when they write #Name …". The name is escaped; it is the same text the user typed, so it adds no taint.
  `RunInputs.projects` is filled by `TurnRunner._inputs` with `ProjectStore(config).list` (user-scoped).
- The quick-add grammar is unchanged: there `/Project` is a project and `#tag` a tag. The chat is a different place,
  and the owner asked for `#`.

## 2. Tasks shown as cards in the chat

- `roost/tasks/cards.py` `TaskCards`: `TaskTools` notes the tasks `add_task` added and `list_tasks` showed. Only a run
  of your own 1:1 chat (`RecordContext.user_started`, not a routine, with a thread) collects them: never a handoff,
  room, helper or an approved step. After the run, `DomainTools.finish_run` (now also calling every handler that has
  `finish_run`) posts one quiet line under the bot's reply: role `activity`, kind `task_cards`, body
  `{"task_ids": [...], "verb": "added"|"listed"|"tasks", "more": n}` (ids only, at most `TASK_CARDS_MAX`).
  Never replayed to a model (`_MODEL_KINDS` excludes it), and the chat list previews it in words ("Added a task",
  "Showed 6 tasks").
- `GET /api/tasks?ids=a,b` answers those of the user's tasks (any status, the order asked; unknown or another user's
  ids are left out; more than `TASK_IDS_QUERY_MAX` is a 422).
- Web `components/chat/TaskCards.tsx` (+ `TaskCardParts.tsx`, `useCardTasks.ts`, reloaded on `tasks_changed`): rows
  with a round tick (complete / reopen), the title (opens the task drawer, mounted on the Chat page at `?task=`), due
  in Madrid's words with tone, priority, project and the web mark; "and N more on the Board". Phone
  `lib/chat/cards/task_cards.dart`: the same rows; tapping opens `openTaskDrawer`. The bot keeps its own short reply.

## 3. The reminder card

- `ReportBody.task_id` (set by `system_reports._reminder`; the "missed reminders" summary has none and stays a plain
  Report).
- Web `ReminderCard.tsx` / phone `reminder_card.dart`: "Reminder · 09:00 Madrid", the bot's name, the task title (opens
  the drawer), its facts, and **Done** (`POST /api/tasks/{id}/complete`) · **Failed** (`POST …/fail`) ·
  **Reschedule** (web `ReschedulePopover`, phone `showRescheduleSheet`; keeps the task's own time when the pick has
  none; `PATCH due_date`) · **Skip** (changes no task). After an action one quiet line says what happened ("✓ Done",
  "Marked failed", "Moved to Thu 29 Oct 10:00", "Skipped"). A 404, or a task that is gone, shows "This task is gone."
- **The answer is kept on the server** (fix, 2026-10-26: a Skip on the phone came back after a restart). Every answer
  is stored on the Report itself: `ReportBody` gained `answer` (`done` · `failed` · `rescheduled` · `skipped`,
  `REMINDER_ANSWERS`), `answer_due` (a Reschedule's new due, `YYYY-MM-DD[THH:MM]`, or null for no date) and
  `answered_at`, inside the already-sealed body, so no migration. After Done, Failed or Reschedule changed the task, and
  for Skip alone, the client calls `PUT /api/threads/{id}/messages/{message_id}/reminder-answer` `{answer, due}`
  (`roost/routines/reminder_answers.py`): only the user's own reminder Report (kind `report`, source `reminder`, a
  `task_id`) in that thread takes one, anything else (another user's, a plain Report, another thread) is a 404; a
  later answer replaces an earlier one; the updated message is published as a `message` frame (same id), so every open
  screen folds the card. Web `ReminderCard` and phone `reminder_card.dart` draw the stored answer
  (`answerWords`) instead of the buttons; a refused Skip keeps the buttons and says why. The web still reads an older
  Skip kept in this browser's storage. A done or failed task with no stored answer still says so.

## 4. A quieter web-content mark

- Web `components/chat/WebMark.tsx`: a small outlined chip, a globe and "Web", named "From web content" for screen
  readers; a click/tap opens a popover ("Part of this came from a web page. Roost limits what the bot can do after
  reading it, so check it before you act on it."), and the hover title says the same. Used under bot replies, memory
  offers, reports, reply quotes and task cards in the chat. Tokens only (`styles/chat-tasks.css`); faint text on
  panel keeps 4.5:1.
- Phone `lib/chat/web_mark.dart`: the same chip under the reply (it was an orange line above it), a tap shows the
  explanation; every chat card's `from web content` badge (`CardFrame`) and the reply quote use it.
- The Board, Plan, Memory and other places outside the chat keep their marks for now.

## Tests

`tests/test_chat_projects.py`, `tests/test_task_cards.py`, `tests/test_reminder_job.py` (task_id),
`tests/test_reminder_answer.py` (the kept answer); web
`tests/chatProjects.test.tsx`, `tests/chatTasks.test.tsx` (and the mark queries in three older tests); phone
`test/chat_tasks_test.dart`.
