# The computer card (web + phone)

Owner request, 2026-10-23: while a bot works on its computer, the chat shows a good-looking live card; a tap shows
what it is doing and where. No schema change.

## Server

- After each screen tool in a live run (`look`, `wait_ready`, `scroll`, `click`, `type`, `press_key`, `open_app`,
  `list_tabs` / `switch_tab` / `close_tab`, and `open_page` on a Linux computer) the runner publishes:

  ```json
  {"type": "computer_step", "bot_id": "…", "thread_id": "…", "run_id": "…", "step": 4,
   "kind": "look|wait|scroll|click|type|key|open_page|open_app|tab",
   "line": "Clicked 'Messages'", "host": "www.upwork.com", "at": "2026-10-23T14:05:00+00:00"}
  ```

  `step` counts from 1 per run. `line` is the chat's own activity line (`roost/computer_use/lines.py`), cut to
  `COMPUTER_STEP_LINE_MAX`. It never holds typed text: a typing line says only how many characters. `host` is the
  host name alone (`steps.step_host`: http/https only, no path or query), or null on the desktop or another app.
  There is never a picture.
- `roost/computer_use/steps.py` builds the frames. `ComputerUse._say` wraps the run's announce, so every activity
  line of a call that `handle` runs is also a step. A card's approved re-run has no live run and publishes none.
- `computer_step` is live only (`LIVE_ONLY_TYPES` in `roost/events/hub.py`): it is never stored, and the events
  socket forwards it like `text_delta`.
- `ComputerSteps`, an `EventHub` listener on `app.state.computer_steps`, keeps each bot's current run's newest
  `COMPUTER_STEPS_KEPT` (40) steps in memory. A new `run_id` starts a new ring, and a `bot_status` other than
  `on_it` drops it. The `snapshot` frame carries them as `computer_steps: {bot_id: [step, …]}`, so a page opened
  mid-run shows the card.
- Leftovers L3 (2026-10-25): a run that ends (a `bot_status` other than `on_it`, or a new `run_id`) is not lost
  but kept as its chat's finished run, in memory only, `COMPUTER_KEPT_RUNS_PER_BOT` (5) chats per bot, dropped by
  `bot_removed`. The `snapshot` carries them as `computer_kept: {bot_id: [[step, …], …]}` (oldest run first), so a
  restarted phone still shows the newest run's kept card. Still no picture and no typed text.

## Web

- `web/src/store/computerRuns.ts` keeps runs by run id. Each run is anchored to the bot's open reply (its seq 0
  placeholder) when its first step arrives. `placeRuns` draws a run inside its reply while that reply is listed. If
  the reply is gone (a run that parks on an Ask card drops its empty placeholder) or unknown (a reload), the run
  goes just above the bot's next message, or at the end.
- `ComputerCard` (`web/src/components/chat/`), while live (the bot is On it and this is its newest run):
  - a 16:10 view-only live screen (`ComputerThumb`) with the pointer ring, a soft placeholder while it connects,
    and noVNC loaded only while the card is on screen (`useInView`);
  - a frosted chip with "Live" and the host;
  - the newest step line with a shimmer, and "Step N".
- After the run, the card folds into "Used its computer · host · N steps".
- A tap on either opens `ComputerSheet`, a lazy chunk with:
  - the bot, the host and the status;
  - the big view, or a calm box if the computer sleeps;
  - the steps, newest first, with Madrid times ("Now" while live);
  - Take control, which takes the lock and opens the Computer panel, as the Stuck card does, and Close.
- Only one live screen per card: the card's own socket closes while the sheet is open.

## Phone

The phone app builds the same card against this contract (a separate fork).

## Owner, 2026-10-26: no screen in the chat

"Showing screen is little bit too much ... if I want see screen will go in computer tab." Both clients now:

- While a run works, the chat shows one compact line in the activity pill's capsule: the step's icon, the site, the
  step now in words and "Step N"; a tap opens the steps sheet. No thumbnail, and the chat opens no live-screen socket
  (web `useLiveScreen`, phone `liveScreenProvider`).
- After a run, every run (the newest too) is the quiet folded line that opens the steps sheet. The kept card (screen,
  Wake, Open screen) is gone: web `ComputerKeptCard.tsx`, `ComputerThumb.tsx`, `newestRunIn`; phone
  `computer_kept_card.dart`, `computer_thumb.dart`, `newestComputerRun`, the Live pill, skeleton and glass tokens.
- The steps sheet (and the activity sheet of a run that used the computer) has no screen either; its **Open computer**
  goes to the bot's Computer tab (web `/bots/{id}?panel=computer`) or computer screen (phone `/computer/{id}`), where
  the live view and Take control stay. Take control stays in the sheet.
- The server is unchanged: `computer_kept` in the snapshot still restores finished runs, now drawn as their lines.
