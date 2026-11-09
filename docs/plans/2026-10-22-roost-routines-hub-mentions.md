# Routines in one place, and @bot in a chat (design note)

**What.** Two small tracks, functionality first.

1. **All routines.** One page lists every routine of every bot the user has (name, bot, schedule words, next run
   in Madrid time, last run's result), with the switch and Run now; the recent runs across bots; and a short list of
   built-in **routine templates** (Morning brief, Weekly money summary, Inbox tidy, Daily journal note, Price watch)
   with "Add to <bot>". A template only fills a new routine: it is created through `RoutineService.create`, the same
   path as `POST /api/bots/{id}/routines`, made by the user (`created_by="user"`, untainted).
2. **@bot in a bot's chat.** When your message in bot A's chat names another of your bots (`@Scout`, exact name,
   case-insensitive, unknown names ignored, A itself ignored), the server hands the message to Scout as a `handoff`
   work item (the `ask_bot` path: `TurnRunner.hand_off`, Scout's "From A" thread). The handoff line
   "You → Scout: …" shows in A's chat, and Scout's full answer comes back into A's chat as a bot message written by
   Scout (A reads it later as a teammate's words, never as yours). A message that **starts** with mentions is meant
   for those bots only, so A is not queued; a mention later in the text also goes to A as today. At most
   `MENTIONS_PER_MESSAGE_MAX` bots per message; an off-duty bot gets a notice instead. Only in a `chat` thread
   (rooms keep their own mentions).

**Schema.** None. Templates live in code (`roost/routines/templates.py`).

**Routes.**
- `GET /api/routines`: every routine of the user's bots, with `bot_id`, `bot_name`, `next_run_madrid`,
  `last_state`, `last_note`, `last_finished_at`.
- `GET /api/routines/runs?limit=` (1..`ROUTINE_RECENT_RUNS_MAX`): recent runs across bots, newest first, each with
  `routine_id`, `routine_name`, `bot_id`, `bot_name`.
- `GET /api/routine-templates`: `{templates: [{id, name, instructions, schedule, words}]}`.
- `POST /api/bots/{bot_id}/routines/from-template` `{template_id}`: 201 and the routine; unknown template 422,
  another user's bot 404.
- `POST /api/threads/{id}/messages` answers `mentioned: [bot ids]` as well.

**Code.** `RoutineStore.list_for_user`, `RoutineRunStore.list_recent_for_user`, `RoutineService.list_all` and
`recent_runs`; `roost/talk/mentions.py` (`chat_mentions`, `MentionRouter`). Web: `pages/Routines.tsx` (lazy, at
`/routines`, linked from the sidebar foot beside Board), and the chat composer's `@` list (reuses the room
composer's mention helpers).

**Risks.** A mention handoff is in memory like every handoff: a restart drops it (the usual "dropped" notice). The
mentioned bot waits behind its own queue and answers within `HANDOFF_TIMEOUT_S`, or A's chat says it did not
answer. A handoff run is never "your own" run, so it can't create bots or open Stuck cards (same as `ask_bot`).
