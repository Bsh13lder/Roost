# Self-healing: a browser that stops answering heals itself, and failures are never silent

**Owner request, 2026-11-10, after a real incident.** Bot 1016fb46's Linux computer's Chromium tab froze: `Page.enable`
timed out after 30 s (`roost/desk/browser.py`), every `open_page` then raised `DeskUnavailable`, `web_search` quietly
returned its "desk unavailable" text, and a 5-minute page watch failed silently for 30+ minutes (a warning in the
log, "failed" returned, nothing in the run log or the chat). The hung-browser restart of 2026-11-06
(`roost/desk/page_keeping.py`, `COMPUTER_HUNG_RESTART_COOLDOWN_S`) never fired, because it only fires when
`Browser.getVersion` fails, and here the browser-level target still answered. A manual `docker restart` fixed it.

## 1. The desk heals itself (`roost/desk/page_keeping.py`, `client.py`)

- **A "didn't answer" streak per desk.** Every page call that fails with a CDP reply error or timeout, a page that
  keeps crashing, or a `DeskUnavailable` from the page path is noted with its monotonic time (`_answer_fails`).
  `DESK_UNANSWERED_STREAK` (3) failures within `DESK_UNANSWERED_WINDOW_S` (600 s) count as a hung browser, exactly
  like a failed probe: `_restart_hung` stops the Linux computer (the profile stays), the call runs once more on the
  fresh browser, and its result carries `BROWSER_RESTARTED_TEXT`. The existing rules hold: never on Mac Brave, a
  retired desk or while you hold the computer, and at most once per `COMPUTER_HUNG_RESTART_COOLDOWN_S`, so it can
  never loop. A call that completes resets the streak; a restart resets it too.
- **One quiet chat line.** `KeeperDesk(on_healed=…)` is told once per successful restart. `DeskFactory` routes it
  through `RoomHooks.on_healed` to `TurnRunner._say_restarted`, which posts `COMPUTER_RESTARTED_LINE` ("My computer
  stopped answering, so I restarted it.") in the bot's main chat as a `computer_restart` message (role `system`,
  plain words on web and phone; registered in `roost/talk/store.py` and `web/src/api/types.ts`). A watch check
  notes its run user too, so a restart during a check still gets its line. A hook that fails never breaks the call.

## 2. The page watch is never silent (`roost/routines/watch.py`, `watch_fails.py`)

- **Folded failure line.** A check that can't read the page (`failed`) or finds no free computer (`no_room`) goes
  through `WatchFailures.note`. Failures in a row fold into one run-log row in state `error`:
  "Couldn't check: the computer didn't answer · 3 times" / "Couldn't check: no free computer · 2 times"
  (`watch_texts.couldnt_check_note`), like the "No change" fold: never a row per failure. One skip for room stays
  quiet as before; from `WATCH_NO_ROOM_NOTE_AFTER` (2) in a row it is a line. The fold lives in schema v47's
  `routine_watches.fail_count` / `fail_run_id`.
- **One chat line at three.** At `WATCH_FAILS_STUCK` (3) failures in a row `RoutineHooks.watch_failing` posts one
  `routine_note` in the bot's main chat: "I can't check <host> for "<name>": the computer didn't answer 3 times in
  a row. I'll keep trying every 5 min." Said once per streak.
- **A good read clears it.** The store's `save`, `checked` and `set_blocked` reset the fold (`_CLEAR_FAILS`), and
  `WatchFailures.clear` drops the routine's last error.
- **Stale trigger guard.** `queue_check` used to refuse while any `trigger` item sat open, so one item leased by a
  drain that died blocked every later check for `WORK_LEASE_SECONDS`. Now `WorkQueue.oldest_open` gives the item, and
  one older than `WATCH_STALE_TRIGGER_INTERVALS` (2) × `every_min` is dropped (`drop_items`) and a new check queued.

## 3. Last error per routine (schema v47)

`routines.last_error_kind` (a fixed word: `ROUTINE_ERROR_NO_ANSWER` "no_answer", `ROUTINE_ERROR_NO_ROOM` "no_room",
`ROUTINE_ERROR_RUN` "run_error"; plaintext, no user content) and `last_error_at` (UTC). The watch sets the first two;
`RoutineHooks.finish` sets `run_error` when a run ends in `error` and clears it when one ends `done`. `routine_out`
adds `"last_error": {"kind", "at"} | null`. The web's History sheet leads with it
(`web/src/components/routines/lastError.ts`: "Couldn't check (computer didn't answer) · 12:40", `zoneClock` on the
account's clock) and the phone's run log shows the same line (`lastErrorLine` in `mobile/lib/routines/routines_repo.dart`,
`appClockOrShort`). Migration 47 is in `roost/db/migrations.py` and `SUPPORTED_SCHEMA_VERSIONS`.

## 4. Constants (`roost/constants.py`)

`DESK_UNANSWERED_STREAK = 3`, `DESK_UNANSWERED_WINDOW_S = 600.0`, `COMPUTER_RESTARTED_LINE`, `WATCH_FAILS_STUCK = 3`,
`WATCH_NO_ROOM_NOTE_AFTER = 2`, `WATCH_STALE_TRIGGER_INTERVALS = 2`, `ROUTINE_ERROR_NO_ANSWER`, `ROUTINE_ERROR_NO_ROOM`,
`ROUTINE_ERROR_RUN`.

## 5. Tests

`tests/test_desk_unanswered_streak.py`, `tests/test_computer_restart_line.py`, `tests/test_routine_watch_failures.py`,
`tests/test_migrations_v47.py`; `web/tests/routineLastError.test.ts` and the new cases in `RoutinesCard.test.tsx` and
`MessageRow.test.tsx`; `mobile/test/routines/last_error_test.dart`.

Not done here: `web_search`'s "desk unavailable" text is unchanged (the desk now heals under it, and the streak
counts those failures).
