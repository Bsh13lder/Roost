# Roost: the Grok feel for Reports, reminders and routines (2026-10-26)

Owner request, 2026-10-26: make a bot's chat feel like Grok's, which the owner finds "pretty cool". A reminder
arrives as an ordinary friendly bubble ("Quick reminder: your reply to JIN HU is due today."), later ones worded
differently ("Gentle nudge: … is still due today."), the owner answers "Yeah I texted him" and the bot ticks the
task off. Bot actions are quiet centred lines, replies are short, and the automations list says "Next run: in 10 hr.".

No schema change. `ReportBody` gains two optional fields, so older bodies still read.

## What changed

1. **A Report is the bot's own bubble.** A `report` message (a routine's result or a task reminder) draws as a normal
   bot message: its text as markdown, no bold "Report: …" headline, no card, no big "Open run log" button. Under it a
   quiet grey footer: `↻ <routine name> · Run log ›` for a routine (the link goes where Open run log went), and
   `🔔 Reminder` for a reminder. The Web mark stays when it is tainted. A Report with no text shows its headline.
   Web: `web/src/components/chat/ReportMessage.tsx`, `ReportFoot.tsx`. Phone: `mobile/lib/chat/cards/report_bubble.dart`,
   `report_foot.dart`, and `mobile/lib/chat/bot_markdown.dart` (the one markdown look a reply and a Report share).
2. **A reminder's buttons are small chips.** Done · Failed · Reschedule · Skip stay (the owner asked for them) as small
   quiet chips under the bubble; the kept answer (`ReportBody.answer`, `roost/routines/reminder_answers.py`) shows as
   one quiet line ("✓ Done", "Skipped", "Moved to …"). The footer's "Open task" opens the task drawer. Web:
   `ReminderChips` in `web/src/components/chat/ReminderCard.tsx`; phone: `ReminderChips` in `reminder_card.dart`.
3. **Friendly, deterministic reminder words** (`roost/routines/reminder_words.py`, no model run, no randomness; the
   words depend only on which reminder it is):
   - an advance reminder: "Heads-up: <title> is in 2 h." / "… is tomorrow at 10:00 Madrid." / "… is on Friday 23 October at 10:00 Madrid.";
   - the reminder itself with a later due: "Quick reminder: <title> is due today at 18:00 Madrid.";
   - the reminder itself at the due time, or with no due: "It's time: <title> (10:00 Madrid).";
   - after the reminder time or past the due: "Gentle nudge: <title> is still open."
   The body carries `task_title`. When the model reads the chat back (`roost/talk/turn.py` `_report_text`) a task
   reminder is "Reminder for task <title> (id <task id>): <text>", plus "You already answered it: done." once answered,
   so "done" from the owner reaches `complete_task` on the right task.
4. **No "On it" line in a routine Report.** `report_body` drops the first-line rule's leading "On it: …" line from
   the text (`without_on_it`), as `headline_of` already did for the headline. Reports the server writes itself (a
   failure, a missed or held slot, the day summary) put their headline as the text's first line (`with_headline`),
   since the chat now shows only the text. Every routine Report carries `routine_name` for the footer.
5. **Next run in words.** The API already gives the next time (`next_run_at` on a bot's routines, `next_run_madrid`
   on `/api/routines`), so no server change: the web's routine rows (the Info fold and the `/routines` page) and the
   phone's routines screens say "Next run: in 3 h" / "tomorrow 09:00 Madrid" / "Sat 09:00 Madrid" / the date
   (`nextRunWords` in `web/src/components/routines/madrid.ts` and `mobile/lib/routines/next_run.dart`); the web row
   keeps the full Madrid time as its tooltip.

## Tests

- pytest: `tests/test_reminder_words.py` (every wording), `tests/test_reminder_job.py` (the words through the job),
  `tests/test_routine_reports.py` (the On it line), `tests/test_routine_launcher.py` (the model reads a reminder as
  its task's title and id, and its answer).
- vitest: `web/tests/ReportMessage.test.tsx`, `web/tests/chatTasks.test.tsx`, `web/tests/nextRunWords.test.ts`,
  `web/tests/RoutinesCard.test.tsx`.
- flutter: `mobile/test/report_bubble_test.dart`, `mobile/test/chat_tasks_test.dart`.
