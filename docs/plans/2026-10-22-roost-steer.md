# Steer: a busy bot reads your new message mid-work

Owner decision (handoff questions/05, accepted by the chief). Today a message sent to a bot that is On it waits
("Queued, I'll pick it up next") until the run ends. Now it is read inside the running run.

## What

- **Steer by default.** A message you send while the bot's run for THAT chat is in progress is taken at the
  run's next step boundary: before the next model call, never in the middle of a tool call. The model sees it as
  a new user turn (marked as sent while it worked) and adjusts; the one reply covers both. A message that lands
  while the final answer streams is taken too: the run goes on one more step instead of ending.
- **Restart only while nothing happened.** At a boundary after a tool step, if the run has completed no
  write or act call yet (only reads), the run is restarted instead: its partial reply is dropped, and the SAME
  run id runs again with every unanswered message (one run id per turn; the daily cap counts it once). At most
  `STEER_MAX_RESTARTS` restarts, then it steers.
- **Burst debounce.** Before a NEW run starts on your messages, the drain loop waits until the newest queued
  message is `STEER_DEBOUNCE_SECONDS` (1.5 s) old (at most `STEER_DEBOUNCE_MAX_SECONDS`), so quick messages are one
  turn. Tests set `ROOST_STEER_DEBOUNCE_SECONDS=0` (read only in scripted mode).
- **Stop.** `POST /api/bots/{id}/stop` (existing) now ends the run at the next boundary: a streaming model step is
  cut at once (no side effects), a running tool finishes, calls left in that step are not run. Waiting messages are
  dropped as before and handed-out work is stopped first (so an `ask_bot` wait ends). If the run has not ended
  after `STOP_GRACE_SECONDS`, it is cancelled as before ("Interrupted, outcome unknown"). The chat's line lists
  what the run did: "Stopped. Done so far: Added a task, Saved a note." Existing Undo lines stay where they are.
  The web shows a small Stop button by the composer while the bot is On it.

## Durability

No schema change. A steered message is still a durable `work_items` row: the boundary claims it under the
running run's id (`WorkQueue.claim_thread_messages`), so `complete()` marks it done with the run and it is
never answered twice. After a gateway restart, claimed items go back to queued (as today) and the next run
answers them once.

## Routes and fields

- `POST /api/threads/{id}/messages` returns `status`: `"steered"` (the bot's run for this chat will read it),
  `"queued"` (the bot is busy elsewhere, or with a run that is not steerable), or `"started"`; `queued` stays as
  `status == "queued"`. The web shows no Queued line for `steered`.
- `POST /api/bots/{id}/stop` keeps its body (`dropped`, `interrupted`) and adds `done` (the lines listed).

## Risk rules

- Only runs made of your own messages (and Stuck-card continue items) in a 1:1 chat steer. Routine runs,
  handoffs and room posts never do; a message for them waits in the queue as today.
- A new message never answers an open Ask card, options card or Proposal card: cards close only through their
  own buttons, and the message is only context for the run.
- Injecting your clean message never clears taint: the run keeps its taint and link guard.
- No restart after any completed write or act call.

## Files

`roost/talk/steer.py` (the per-run `RunSteer`, `RunRestart`, the past-tense done lines),
`roost/talk/steps.py` (the boundaries), `roost/talk/tool_runner.py` (reports completed writes),
`roost/talk/runner.py` + `roost/talk/stop_flow.py` (registry, restart loop, debounce, graceful Stop),
`roost/work/queue.py`, `roost/gateway/routes/threads.py`, `web/src/pages/Chat.tsx` and a small `StopButton`.
