# Offline tasks on the phone (owner, 2026-11-08)

> "I want app worked without tail scale too basics add tasks see tasks and etc when it connects to tailscale after
> syncs to computer"

The phone app reaches Roost only through the gateway on the Mac (over Tailscale). Without it, today the whole app
is covered by the offline screen. This plan keeps the basics working with no connection: **see your tasks, add a
task, tick one done**, and sends what you did to the Mac the next time it answers.

Decisions made overnight by Claude Code (the owner may change them; each is small to undo):

- **O1. Only tasks work offline.** Chat, bots, money and notes still need the Mac; their screens keep the offline
  screen. The offline screen gains **Open my tasks**, which opens the offline tasks screen.
- **O2. What the phone keeps:** the last open-task list it saw (the same `sort=due` list the Tasks tab shows) and a
  queue of changes made offline. Both live in `flutter_secure_storage` (already a dependency; encrypted on the
  phone), never in a plain file. Signing out clears both.
- **O3. Adding offline:** you type a line as usual. It is queued as the raw line with the moment you typed it and a
  new client id. The list shows it at once, in a "Waiting to sync" group with the raw line as its title.
- **O4. Syncing an added line:** `POST /api/tasks/offline` `{client_id, text, typed_at}`. The server reads the line
  with `now = typed_at` (so "tomorrow" means the day after you typed it), never hands it to a bot (handing needs your
  confirm), and when a part would need a question (an unknown `#project`, a slice it can't use, a repeat it can't
  say) that part stays as plain words in the title. It never guesses. A line with no title words is created from
  the whole line as typed.
- **O5. No duplicates:** `tasks.client_id` (schema v43, a plain id, unique per user). Sending the same client id
  again returns the task it already made (200, `created: false`), so a sync cut off half-way is safe to repeat.
- **O6. Done offline:** a tick is queued as `complete <task id>` and the row shows as done. On sync it is
  `POST /api/tasks/{id}/complete`; a 404 (already done or deleted on the Mac) counts as synced. A tick on a task
  added offline waits for that task's add first.
- **O7. When it syncs:** the moment the app reaches the gateway again (the reachability hooks), on pull to
  refresh, and once at app start when signed in. Changes go one at a time, oldest first. A network miss, a 401,
  403 or 429, or any 5xx (`tailscale serve` answers 502 while the gateway is down or restarting) stops the round
  and keeps the queue. Any other 4xx (but the 404 above) drops that one change and lists it once as "Couldn't sync:
  <line>", so one bad line never blocks the rest.
- **O8. After a sync** the list is loaded again from the server, which replaces the kept copy.

## Server (Python)

- Schema v43: `ALTER TABLE tasks ADD COLUMN client_id TEXT` and a unique index on `(user_id, client_id)` where it is
  not null. Additive, as every migration.
- `POST /api/tasks/offline`: body `OfflineTaskIn {client_id: uuid str, text: 1..QUICK_LINE_MAX, typed_at: ISO
  datetime, not more than OFFLINE_TYPED_AT_MAX_AGE_DAYS old and not in the future past OFFLINE_CLOCK_SKEW_S}`
  (pydantic, `extra="forbid"`). Reply: the task (`task_out`) plus `created`.
- `TaskStore.find_by_client_id(user_id, client_id)`; `TaskService.create(..., client_id=None)`.
- Tests: the read uses `typed_at`; no bot is assigned; an unknown project stays in the title; the same client id
  twice makes one task; another user's client id makes a new task for you (ids are per user); bad bodies are 422.

## Phone (Flutter)

- `lib/board/tasks/offline/`: `offline_store.dart` (the kept list and the queue, JSON in secure storage, immutable
  lists), `offline_queue.dart` (models: `QueuedAdd`, `QueuedDone`), `offline_sync.dart` (`OfflineSync.run`, one
  change at a time per O7), `offline_tasks_screen.dart` (the list, the add line, the tick, the "Waiting to sync"
  group and the "Couldn't sync" line).
- The Tasks tab saves each list it loads to the store (O2), and the offline screen's **Open my tasks** opens the
  offline screen, which needs no connection.
- `TaskItem.toJson` for the kept copy.
- Tests with `FakeAdapter`: a queued add syncs with its typed time and client id; a network miss keeps the queue; a
  4xx drops one change and keeps the rest; a done on an offline add waits for it; a 404 on complete counts as synced;
  sign out clears the store.
</content>
</invoke>
