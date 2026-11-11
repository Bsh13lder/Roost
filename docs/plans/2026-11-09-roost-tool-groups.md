# Tool groups and the routine model (owner, 2026-11-09)

Owner: "why don't we have a tool selector? How does Claude Code do it? All tools and skills in one turn is too much."
Then: "Yes, the Claude way, and if you think routines still need a model selector, do that too … maybe Opus will set
up a routine's model as it wants; if I change something, is that fragile?"

## 1. Tool groups (`roost/talk/tool_groups.py`, `roost/talk/run_groups.py`)

Every model step carried the whole catalog: 114 tools, about 67k characters of schema. Claude Code's own tool
search (`ENABLE_TOOL_SEARCH` in the bundled CLI) does not fit Roost: Roost runs its own step loop with `max_turns=1`
and no built-in tools, so the CLI's ToolSearch can neither run nor carry a found tool into the next step. Roost does
the same idea in its own loop:

- **Core tools** are always offered (`CORE_TOOLS`: time, memory, chat search, options and help cards, the question
  book, web search and pages, skills, helpers, teammates, `load_tools`).
- **Eleven groups** (`TOOL_GROUPS`): tasks, money, projects, notes, routines, plan, computer, mac, programs,
  connectors, bots. A test keeps every catalog tool either core or in exactly one group.
- **Start groups**: the claimed items' text and the chat's last 6 messages are matched against each group's words
  (English and Spanish) and against tool names; a card answer or a Stuck reply also loads the computer group.
- **`load_tools(groups)`** (gate kind `read`, never a helper's) loads more; a loaded group stays for the rest of the
  run, from the next step. `open_page` loads the computer group (looking and clicking come next).
- The instructions end with an index of the groups not loaded at the start, each with its tools' names.
- Only what the model is shown changes. The run's allowlist, the gate and every tool's rules stay the same.
- `ROOST_TOOL_GROUPS=off` offers the whole catalog again (and hides `load_tools`).

Sizes (characters of schema): everything 67,091; a plain message 9,623 (core and index); the computer group
13,979, tasks 6,873, notes 6,170, routines 6,915, bots 7,841, money 4,744.

A group loaded in the middle of a run changes the tool list, so that one step reads no prompt cache; the start
groups exist so most runs never need it.

## 2. A routine's model (schema v46)

- `routines.model` (a model id, plaintext: a setting; NULL is "Same as the bot") and `routines.model_failures`.
- `resolve_routine_model` (`roost/llm/registry.py`): the routine's own model if pickable, else the bot's. A routine
  run carries it on `RoutineSection.model`; your own chat always uses the bot's model.
- Set on the routine editor's Model row (web and phone: Same as the bot · Fable · Sonnet · Opus · Haiku), on
  `POST /api/bots/{id}/routines` and `PATCH /api/routines/{id}` as `model` (an id, a short name, or null), and by the
  bot's `create_routine` / `update_routine` (`model`: same · haiku · sonnet · opus · fable; the spec tells it to pick a
  cheaper one only for a simple repeated check and to say why). An Ask card for it shows "Runs on Haiku 5.5."
- The safety net (`RoutineHooks._model_outcome`): a run on the routine's own model that ends done starts the count
  over; one that errors or is capped adds one (a Stuck run is not counted). At `ROUTINE_MODEL_FAILURES_MAX` (2) the
  routine goes back to the bot's model and the bot's chat gets a `routine_note` (`model_fallback`). Any change of
  the model starts the count over.

## 3. The page watch never compares the whole page by mistake

Live data (2026-11-09): a 5-minute watch made 186 runs in 3 days. Its named part was not on the page, so
`pick_part` fell back to the whole page (a WhatsApp chat list), and any chat's news started a model run.

- Words found nowhere are now `missing` (`watch_part.pick_part`): no compare and no model run. The first miss
  forgets the old snapshot, writes one run-log line (`MISSING_NOTE`) and one chat line (`watch_missing`) asking to
  name the part the way the page shows it; later misses are only counted. A found part starts a fresh baseline.
  A name in quotes is looked for on its own, and request words ("new messages from") are not (owner, 2026-11-10).
  A chat list row ends before the next row (a line followed by a time or day), and a change run that finds no news
  about the watched part replies `[nothing new]`, so another chat never pings you. A part that names every chat
  ("all chats", "chat list", "todos los chats", or chats in the plural with no name, `WATCH_CHATS_PLURAL`) watches
  the whole chat list (`WATCH_ALL_CHATS`), and a bracket is a
  name only when a word in it starts with a capital or a digit ("(not groups)" is a remark; owner, 2026-11-11).
  A routine with no words still watches the main text or the whole page.
- The fingerprint is made of the normalised lines in sorted order (`compared`): rows that only move are no change.
- Counters with thousands separators ("1,234 unread messages") are noise.

## 4. Keeping the cache warm (2026-11-10)

A review of the live runs: the prompt cache's prefix is tools → system → messages, and Roost's own step loop sends
all three on every step. Three things broke the prefix or made it grow without end.

- **The tool list only grows.** `load_tools` used to disappear once no group was left to load, and that change
  alone broke the cache for a step. `visible_specs` now keeps it to the end of the run; the list's tail never
  changes (`tests/test_tool_groups.py`, `test_tool_groups_run.py`).
- **A thread's recent groups start loaded** (`roost/talk/recent_groups.py`, `RECENT_GROUP_RUNS` = 3). A group
  loaded in the middle of a run changes the tool list, so the groups a thread's last runs actually called tools from
  (`ToolRunner.used_groups`, carried on `TurnResult.used_groups`) are added to the next run's start groups
  (`start_groups(recent_groups=…)`, `RunInputs.recent_groups`). A bot that browsed has the computer group from step
  1 of its next run; a group only loaded but never used is not carried. Nothing is stored and no migration was
  needed: `RecentGroups` is a frozen map on the runner, keyed by thread, at most `RECENT_GROUP_THREADS` (500)
  threads with the oldest touched dropped first, empty at boot.
- **Old tool results fold in batches** (`roost/talk/compact.py`). A long browsing run carried every 12k-character
  page (`PAGE_TEXT_LIMIT`) to its last step. A result with `COMPACT_AFTER_STEPS` (12) results after it now reaches
  the model as `[no longer shown; read it again if you need it]`, and the fold moves in whole batches of
  `COMPACT_BATCH_STEPS` (10) so the cache breaks once per batch, not once per step. The newest
  `COMPACT_KEEP_RESULTS` (3) always stay whole, as do results under `COMPACT_MIN_CHARS` (400), a `Refused`, `Not
  performed`, `Not shown`, `Blocked:`, `Stuck:`, `Asked:` or `Error` result, the newest look (its picture rides
  after it) and every user turn (a card answer, an `approval_result`, a steered message). Only the request is
  folded (`roost/talk/run_request.py` `request_turns`); the stored turns never change and the run's taint was
  recorded when each result arrived.
- **The screen prose only when it is relevant** (`SCREEN_PROSE` in `roost/talk/instructions.py`: the screen
  rules, `FINISH_WEB_TASK_TEXT`, the stuck and handed-back words; 6,106 characters). It went into every run of a
  Linux bot, "move the task to Friday" included. `build_instructions(screen_prose=…)` now puts it in the system
  prompt only while the computer group is loaded: from step 1 when the start groups hold it (or groups are off),
  and from the step after `open_page` or `load_tools(computer)` loads it mid-run (`_Prepared.screen_system`,
  `system_for`). That step's tool list changes anyway, so the swap costs no extra cache break; the words and their
  order are unchanged (`tests/test_instructions_screen_prose.py`). A Mac Brave bot keeps the stuck and handed-back
  words in every run as before. Measured: a Linux bot's plain-run instructions went from 13,063 to 6,949
  characters.

The step's request is built in `roost/talk/run_request.py` (`offered_specs`, `system_for`, `request_turns`), moved
out of `roost/talk/turn.py` to keep it under its size.
