# Routine watch: "Only run when the page changes"

**Owner decision, 2026-11-04.** Gela's routine "Watch physio chat" ran the full model every 30 minutes to open
WhatsApp Web and read one chat: 48 runs a day, most of them to say "nothing new", and once it read the owner's own
sent message as the physio's. Now a routine can watch a page instead. Roost reads that page itself, with no model,
every few minutes, and the routine runs only when the watched part changed. The run is told exactly what is new.

## 1. What the owner sets

A routine's **watch** has three parts:

- **Page address.** It must pass the same rule as an Open card's address (`askable_url`: http(s), no credentials,
  no port, the URL policy's local and private host refusals), so a watch never opens anything `open_page` could not.
- **What part to watch**, in plain words ("the physio chat", "the price box"). Empty means the whole page.
- **Check every N minutes.** At least `WATCH_EVERY_MIN_MINUTES` (5) and at most `WATCH_EVERY_MAX_MINUTES` (a day).

The owner sets it in the routine editor (web: Info → Routines → Edit; phone: the routine sheet) with the switch
**Only run when the page changes**. While the switch is on, the editor hides the schedule, because a watching
routine runs only when its page changes. The routine row reads
"Watching web.whatsapp.com · every 5 min · last change 14:50", and its next line is "Next check: in 4 min".
Watching routines are left off the calendars, since no run time is known ahead.

A bot sets a watch only through the existing routine tools (`watch` on `create_routine`, `update_routine`,
`propose_routine` and `propose_routine_change`; `{"off": true}` stops it):

- the direct tools keep their rules (a clean run that your own 1:1 message started, under the approval mode),
  **and** the address must be one that your own messages in that chat name: its address, a bare domain, or a
  well-known site by name ("WhatsApp"), read as `open_page`'s link scope reads them. A page's link never counts
  (`WATCH_NOT_NAMED_TEXT`). This holds even in your own chat after it read pages, where the direct routine tools
  run as in a clean run (`roost/talk/owner_chat.py`);
- a tainted run, a routine's own run, a handoff or a room proposes. The card shows the address, the part and the
  interval ("Runs when" on a change card), and only your Approve writes it.

## 2. Schema (v40, one additive step)

- `routines.watch_url` (`enc:v2`, `routines:watch_url`), `routines.watch_part` (`enc:v2`, `routines:watch_part`),
  `routines.watch_every_min` (INTEGER; NULL means no watch).
- `routine_watches`, one row per watching routine (`ON DELETE CASCADE` with its routine): `snapshot` (the watched
  part as last read, `enc:v2` under `routine_watches:snapshot`), `fingerprint` (an HMAC of the normalised part under
  a key derived from the user's DEK, never the text), `change_text` (`enc:v2`, what the change run is told) with
  `change_run_id`, `blocked`, `quiet_run_id` and `quiet_count` (the folded "No change" line), `checked_at`,
  `changed_at`. Every query names `user_id`. A new address or part drops the row, so the next check is a baseline.

## 3. How a check runs

The scheduler still only queues (`roost/routines/scheduler.py`, every 30 s). For a watching routine,
`next_run_at` is its next check: when due, the scheduler claims the slot with the same compare-and-swap, plans
the next check `every_min` from now (a sleep never builds a backlog), and `WatchChecker.queue_check`
(`roost/routines/watch.py`) queues **one** `trigger` work item in the routine's run-log thread. It queues nothing
when the bot is gone or off duty, or when a check is already waiting.

The bot's own drain loop (`roost/talk/runner.py`) claims a `trigger` item **alone**. It is never batched with your
messages or a routine item (`roost/work/queue.py`), so a check never overlaps the bot's runs. It is not counted
as a run of the day and calls no model. A message you send while a check reads the page is answered right after
it, not "Queued". The check (`WatchChecker.check`):

1. **Room.** `Desk.wake_if_room()` starts or wakes the Linux computer only when the keeper has room right now
   (`COMPUTERS_MAX_RUNNING`, the memory check). With no room the check is skipped quietly, with no run-log line,
   and the next one comes at the next interval. It never waits and never says "Waiting for a free computer".
2. **Open.** `open_page(url)` in the bot's browser. On the Linux computer, a tab already showing that site's
   front page is reused without a reload (WhatsApp Web stays live); any other address is loaded again.
3. **Wall.** If `detect_block` sees a sign-in, a challenge or a refusal, the routine runs as usual **once**, with
   the run-log note "The page needs a sign-in, so the routine ran as usual once". The model meets the Sign-in or
   Stuck flow as before. Later checks stay quiet until the page reads again.
4. **Read.** The tab is brought up and given time to settle (`wait_ready`, `WATCH_READY_TIMEOUT_S`). Then its
   readable areas and whole text are read from Chromium's accessibility tree (`roost/desk/page_text.py`, the
   `read_text` path). A Mac Brave bot reads the page text alone.
5. **Find the part** (`roost/routines/watch_part.py`, no model). The meaningful words of the part (stop words such
   as "the" and "chat" are dropped) are looked for in this order:
   1. an area whose name holds them all ("Price box");
   2. an **open chat**: the words stand in a line outside every area (the chat's header) while a message pane
      (`log`, `feed`, `application`) is on the page. The part is the pane's newest `WATCH_TAIL_LINES` lines;
   3. the lines that hold the words, each with the `WATCH_CONTEXT_LINES` after it (a chat list's row: name, time
      and preview);
   4. else the page's main area, or the whole page.
6. **Compare.** The part is normalised. Times like "14:50", "5 min ago" and "hace 3 min" are dropped, and so are
   unread counters, "online", "typing…", "last seen …", spacing and case. Prices stay. The normalised part is then
   fingerprinted. The first snapshot is the **baseline** ("Started watching: saved the page to compare with"). The
   same fingerprint adds to **one** quiet run-log line, "No change · checked 12 times", with no model run and no
   Report. A new fingerprint stores the new snapshot and queues the routine's normal run ("The page changed").

The computer sleeps again on its own, through the keeper's idle pause.

## 4. What a change run is told

`RoutineHooks.prompt_section` adds one trusted line to the routine's usual "nobody is watching" section. The line
says that Roost's page watch read the page itself and the watched part changed, and that lines the user sent
themselves are not news. After it comes **only what is new**: the lines whose normalised form the old snapshot
did not hold, or the whole part when lines only moved, at most `WATCH_CHANGE_MAX_CHARS`. That text is escaped in
one `<untrusted_page>` wrapper, like `read_text`'s, and the section **taints the run** as page content does. The
run's link scope and its browser fence both hold the watched address: the scope through the routine item's
`link_scope`, the fence through `routine_watch_hosts` in `roost/computer_use/run_fence.py`. So the model can open
the page again even though its run log holds no message of yours.

## 5. Wire

- `POST /api/bots/{id}/routines` and `PATCH /api/routines/{id}` take `watch: {url, part, every_min}`. On a PATCH,
  `null` stops watching and a missing key keeps it. A bad watch is a 422 with a plain sentence.
- Every routine out (bot list, hub, create, patch) carries `watch: {url, part, every_min, host, last_checked_at,
  last_changed_at}` or `null`. A watching routine's `words` is "Watching <host> · every N min", and its
  `next_run_at` is its next check.
- A routine proposal's payload may carry `watch`. Its `words` then says "Only when <url> changes (<part>),
  checked every N min", `next` is empty, and a change card's `diff` may hold a `watch` row.

## 6. Tests

`tests/test_watch_part.py` (finding, normalising, fingerprints, what changed), `tests/test_routine_watch_store.py`
(parsing, the sealed columns, v40, the snapshot), `tests/test_routine_watch.py` (on the fake Linux computer with
`roost/desk/fake_chats.py`'s WhatsApp-like page: baseline, no change folded, a change runs once with escaped new
text and taint, a sign-in page runs once then stays quiet, no room skips, no daily-run count, never batched with
your message, the scheduler's cadence), `tests/test_routine_watch_api.py`, `tests/test_routine_watch_tools.py`,
`tests/test_routine_fence.py`, `tests/test_keeper_desk_computer.py` (`wake_if_room` never waits), and on the web
`web/tests/RoutineWatch.test.tsx` and the phone `mobile/test/routines/watch_test.dart`. No test calls a model.
