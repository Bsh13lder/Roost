# A routine ends when its job is done

**Owner request, 2026-11-11.** Bot Gela had a page-watch routine, "Watch physio's WhatsApp reply". Once the
appointment was booked, the routine run could only post a `propose_routine_pause` card the owner had to approve:
noise for a job that was plainly over. The owner wants the bot to end a routine when it judges the job finished, so
it goes away by itself, with the owner always able to undo. Not built (owner rule 2026-10-21, "If I ask, I ask"):
weekly "suggest deleting" messages, an "ends on" date, or anything else.

## 1. `finish_routine` (`roost/routines/finish.py`, `tool_specs.py`)

- Offered to a routine's own run from the start: `start_groups` (`roost/talk/run_groups.py`) loads the one-tool
  group `routine_run` (`ROUTINE_RUN_GROUP`, `roost/talk/tool_groups.py`) when every claimed item is a routine
  item. No words load it anywhere else; its description says it works only there.
- It names no routine. The handler (`RoutineFinish`) reads the routine from the run's own run-log thread
  (`RoutineStore.for_thread`) and finishes it only when `ctx.from_routine` is set, the thread is that routine's
  and the routine is this bot's; anything else is `NOT_ROUTINE_RUN_TEXT`, which points at `pause_routine` /
  `delete_routine` in the owner's own chat.
- Finishing only reduces what runs, so its `ToolDef` is `write_change` with `allowed_when_tainted=True` (a
  page-watch change run is tainted) and `no_ask=True` (no Ask card that would wait for the next run).
- `reason` is one line, `ROUTINE_FINISHED_REASON_MAX` (200) characters, cleaned by `clean_reason`.

## 2. What finishing does (schema v48, `RoutineService.finish`)

- Migration 48 adds `routines.finished_at` (plaintext UTC) and `routines.finished_reason` (sealed, AAD
  `routines:finished_reason`). `RoutineStore.finish` sets `enabled = 0`, `next_run_at = NULL` and both columns.
- One `routine_finished` line (role `activity`, `roost/routines/finished.py`) in the bot's main chat: "Finished
  routine · <name>: <reason>. I'll delete it in 7 days." with **Resume** and **Delete now**. Its body is
  `{routine_id, name, reason, delete_at, text}`. A tainted run's line is stored tainted and wears the existing
  "from web content" mark on web and phone. The built-in day summary can't be finished (422).
- `routine_out` carries `finished: {at, reason, delete_at} | null`; the History sheet (web) and the run log
  (phone) show "Finished: <reason> · deleted <date>".

## 3. Resume, Delete now and the sweep

- `POST /api/routines/{id}/resume` → `RoutineService.resume_finished`: a watch's baseline is reset
  (`WatchStore.reset`, so it compares from a new first look), then `set_enabled(True)`, which clears both finished
  columns and plans `next_run_at` from now. Switching a finished routine on with `PATCH enabled=true` does the
  same, since `set_enabled` is the one place. Another user's routine is 404.
- Delete now is the plain `DELETE /api/routines/{id}`.
- `RoutineService.sweep_finished(user_id, now)` deletes every routine still finished `ROUTINE_FINISHED_KEEP_DAYS`
  (7) after `finished_at`, through the same `delete` the owner's Delete uses (its "Deleted routine · …" line
  included). The scheduler calls it once per user per tick (`RoutineScheduler(finished=…)`, wired in
  `roost/routines/start.py`).

## 4. The prompt

`ROUTINE_FINISH_TEXT` follows `ROUTINE_NOBODY_WATCHING` in every routine run's section (`roost/talk/instructions.py`),
and the page watch's `CHANGE_LEAD` (`roost/routines/watch_texts.py`) ends with the same instruction: when the
routine's purpose is clearly complete, call `finish_routine` with a short reason instead of proposing a pause;
never finish it just because one run found nothing new.

## 5. Constants, kinds and tests

- `ROUTINE_FINISHED_KEEP_DAYS = 7`, `ROUTINE_FINISHED_REASON_MAX = 200` (`roost/constants.py`).
- Message kind `routine_finished` (`roost/talk/store.py`, `web/src/api/types.ts`); plain step "Finished this
  routine" (`roost/talk/plain_steps.py`).
- Web: `web/src/components/chat/RoutineFinishedRow.tsx`, `parseFinished` in `lib/routineMessages.ts`,
  `resumeRoutine` in `api/routines.ts`, `finishedLine` in `components/routines/lastError.ts`.
- Phone: `mobile/lib/chat/cards/routine_finished_line.dart`, `RoutinesRepo.resume`, `finishedLine` in
  `routines_repo.dart`.
- Tests: `tests/test_routine_finish.py`, `tests/test_migrations_v48.py`, `web/tests/RoutineFinishedRow.test.tsx`,
  `mobile/test/routine_finished_test.dart`.
