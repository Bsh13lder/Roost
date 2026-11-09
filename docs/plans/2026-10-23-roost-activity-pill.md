# The activity pill (owner request, 2026-10-23)

The owner, looking at Gela's chat full of "Yes: Run a program: curl -sI … | head -n 1", "Ran: curl … · exit 0" and
an Output fold: "that mess text I didn't ask for. I asked for features showing what it's doing … nice loading
things; if I click there it shows me steps, not code."

## Decisions

- **P1. Every run says what it is doing in plain words.** Thinking, each tool's start and end, and Writing the
  reply. One table (`roost/talk/plain_steps.py`) gives each tool a kind and its words. Only three arguments ever
  reach a line: a web search's query, a new task's title and the teammate an `ask_bot` goes to. A page or a fetch
  adds its host name alone. Never a command, typed text, a file's contents, a path or a URL's path or query
  (`tests/test_plain_steps.py` feeds every tool secrets and paths in every argument).
- **P2. The chat shows one pill per run**, at the run's spot (the reply it writes, like the computer card), with a
  calm moving mark per kind and the current step in words ("Browsing web.whatsapp.com…", "Thinking…"). The same
  run's live computer card sits under it: never two live pictures. When the run ends it folds into one quiet line
  ("Worked for 42 s · 6 steps", "Thought for 4 s"). A tap opens every step as a timeline with its Madrid time; the
  raw step lines wait under a closed "Technical details".
- **P3. The machine's words leave the chat flow.** In a chat (not a room), program rows (`program_activity`) and the
  raw step lines (`toolLines`) are not drawn. An answered yes/no card is one line, "You said yes: Run a program"
  (the title stops at its first colon), and the "Yes: …" bubble under it is not drawn. Nothing is deleted on the
  server; only the chat's drawing changes. Cards that wait for the owner still show as cards.

## Contract

`run_step` (live only, like `text_delta` and `computer_step`):
`{"type":"run_step","bot_id","thread_id","run_id","step","kind","line","host","at","state"}` with `kind` one of
think, search, read, computer, program, file, tasks, notes, money, calendar, bots, memory, message, other, and
`state` start, done or failed (one step number from start to end). The live snapshot carries `run_steps`: each
working bot's current run's steps, the newest state of each, the newest 60 (`RUN_STEPS_KEPT`). A screen run's
computer card and its pill share the run id.

## Files

- Server: `roost/talk/plain_steps.py`, `roost/talk/run_steps.py` (`RunSteps`, `RunStepsLog`), the hooks in
  `roost/talk/tool_runner.py` and `roost/talk/turn.py`, `app.state.run_steps`, the snapshot in
  `roost/gateway/routes/events.py`.
- Web: `web/src/store/activityRuns.ts`, `web/src/components/chat/ActivityPill.tsx`, `ActivitySheet.tsx` (lazy),
  `ActivityMark.tsx`, `web/src/styles/activity.css`, the list and row in `MessageList.tsx` / `MessageRow.tsx`, and
  `closedLine` / `hiddenAnswerIds` in `web/src/lib/approvals.ts`. E2E: `web/e2e/activity-pill.spec.ts` (the
  events socket passed through with frames added; `PILL_SHOTS=<dir>` saves screenshots).
- Phone: built in parallel against the same contract.

## Progress lines (owner, 2026-11-01, "make it smooth like Grok")

Before, the words a bot wrote before a later step's tool calls were fed back to the model and then dropped: only
the first step's "On it: …" line and the final answer reached the chat, and the steps showed only in the pill. Now,
in a run of your own chat (your messages and continue items, outside rooms: `_progress_lines_allowed`, the same
runs that may open Stuck cards), each such line posts at once as its own bot `text` message
(`roost/talk/progress_lines.py`, `ProgressLines`, hooked into `step_loop` as `on_progress`): sealed like any body,
published as an ordinary `message` frame (the web and the phone draw it with no change), tainted by the run's
taint at the moment it posts (the final reply's rule). The step loop never adds these words to the reply, so the
reply never repeats them. At most `PROGRESS_LINES_PER_RUN_MAX` (6) per run; blank words and the same words twice
in a row are skipped. Handoffs, rooms, routines and runs outside the queue keep today's behaviour. The prompt's
`PROGRESS_RULE` (`roost/talk/chat_feel.py`) asks for one short line before each new stage. On the phone each line is
a reply alert like any bot message. Tests: `tests/test_progress_lines.py`.

**Owner, 2026-11-04 ("message spam looks bad … the steps belong inside that card"), replacing the above:** these
lines no longer post as chat messages (`ProgressLines` and `PROGRESS_LINES_PER_RUN_MAX` are gone). Each one is a
note in the run's steps: `RunSteps.note` sends a live `run_step` frame of kind `note`, state `done`, one line of
at most `RUN_NOTE_MAX_CHARS` without its "On it: …" lead, and `tainted` (the run's taint at that moment, so the
clients wear the Web mark); blank words and the same words twice add nothing, and only your own chat's runs send
them. The live pill says the newest note (the reply being written still reads "Writing the reply…") while the robot
acts out the running step; the steps sheet lists notes between the tool steps as quiet sentences (web
`timelineSteps`, `.as-step--note`; phone `RunStep.isNote`, `run-note`), and the "Worked for … · N steps" count
counts tool steps only. Notes are live like every frame, so a reload keeps the folded line but not the notes. Tests:
`tests/test_run_steps.py`, `tests/test_progress_lines.py`, `web/tests/activityRuns.test.ts`,
`web/tests/ActivityPill.test.tsx`, `mobile/test/activity/`.
