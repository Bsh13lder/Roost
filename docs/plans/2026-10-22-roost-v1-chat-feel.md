# Roost v1 Chat Feel, Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. The SDD workspace is `.superpowers/sdd/2026-10-22-roost-chat-feel/` (`contract.md`, one `task-N-brief.md` per task, `progress.md`).

**Goal:** The last items before the v1 feature freeze, from Roost Lead's advice (`/Users/blckit/roost-handoff/notes/2026-10-21-roost-lead-view.md` §1.2, §1.3, §1.7, §1.9 and §2, approved by the user; read it, never edit it). Every run shows words within about a second; the chat never blocks; Ask cards offer real options; the bot's Info tab lists your decisions; Stuck always says why and what next; links, times, "done" and tapbacks get their small fixes.

**Architecture:**
- **No migration.** The latest schema stays **v25** (routines and plan). Options cards are `approval_cards` rows of kind `ask` whose one step is the `ask_choice` tool (the steps are already sealed `enc:v2`). Decisions are `memories` rows of kind `decision` (`memories.kind` has no CHECK). Tapbacks are `messages` rows of kind `reaction` (`messages.kind` has no CHECK). If a task finds it truly needs a column, it stops, and the controller assigns **v26** (the next free number after the routines plan's v25), freezing `tests/fixtures/schema_v25.sql` first.
- **`roost/talk/chat_feel.py`** (new): the prompt rules (a first line before any tool, "done" only once checked, times as "12:16 Madrid", say what a link is). `build_instructions` adds them to every run.
- **`roost/talk/turn.py`:** a run publishes On it with words and its placeholder bubble **before** it loads history, memory or the roster.
- **`roost/choices/`** (new): `models.py` (`ChoiceArgs`, `CHOICE_TOOL`), `decisions.py` (`DecisionBook` over `MemoryService`), `tool.py` (parking an `ask_choice` call), `texts.py`.
- **`roost/approvals/service.py`:** an options card takes `pick`, `own` and `no` (dismiss), builds your line from the **stored** option, records the decision, and queues a `card_answer` item. The executor never runs `ask_choice`.
- **`roost/stuck/texts.py`:** one `stuck_status_line(card)`, a reason plus a next step, on every Stuck frame and in `GET /api/bots`.
- **The web:** words in the placeholder bubble (`FirstLine`), a "Queued, I'll pick it up next" mark, `ChoiceCard`, the Info tab's **Decisions** card, Madrid labels on times, and tapbacks.

**Tech Stack:** as the approvals plan; no new dependency. Python 3.12 (uv), FastAPI, pydantic 2, aiosqlite, pytest; Vite, React 19, TypeScript, vitest + Testing Library, Playwright; the `web/src/ui/` kit and `tokens.css`.

> **Status (2026-10-22): ready to execute.** Written against `night-1` at `8482c7c` (latest migration v25, routines Tasks 1–3 landed). It can run before or after the rest of the routines plan; the one shared seam (the question book) is named in Design meets code 5.

## Global Constraints

- **Path guard, first in every task:** `git -C /Users/blckit/Desktop/Code_Projects/roost rev-parse --show-toplevel` prints `/Users/blckit/Desktop/Code_Projects/roost`, and `git -C /Users/blckit/Desktop/Code_Projects/roost branch --show-current` prints `night-1`. Otherwise stop.
- **Where you may edit:** only under `/Users/blckit/Desktop/Code_Projects/roost`, never its `roost-ui/` folder (the user's). `/Users/blckit/Desktop/Code_Projects/lazyclaw`, `~/Roost/data` and `~/.claude/projects/**` are never opened. `/Users/blckit/roost-handoff/notes/2026-10-21-roost-lead-view.md` is read-only.
- **The live Roost is never touched:** never stop, restart, rebuild or call `roost-gateway-1` (`127.0.0.1:18800`) or the keeper (`127.0.0.1:18801`). Any script that imports `roost` runs with `ROOST_DATA_DIR` and `ROOST_DESKS_DIR` set to fresh `mktemp -d` folders. Run Playwright as `ROOST_DESKS_DIR=$(mktemp -d) make e2e`.
- **Clean room (spec §10.3):** never open, fetch or search for the open-dot repos or `~/Roost-review/`. No browser MCP tools.
- **Licences:** no new dependency; `web/tests/licenseGate.test.ts` stays green.
- **Disk guard:** before `make e2e`, `df -g /System/Volumes/Data | awk 'NR==2{print $4}'`; fewer than 8 GB free: stop and report.
- **Schema:** no migration (see Architecture). `latest_version()` stays 25.
- **Data rules (CLAUDE.md):** every user-content value is `enc:v2` with `user_aad(user_id, "<table>:<column>")`: options and the question live in `approval_cards:steps`, decisions in `memories:text`, reactions in `messages:body`. Every query on user data names `user_id` in its `WHERE`; another user's card, memory, message or bot is **404**.
- **No LLM in tests:** `ScriptedModel`, `ScriptedTeamModel` and `ScriptedWorker` only; `tests/conftest.py` forces `ROOST_MODEL=scripted` and `ROOST_DESK=fake`.
- **Tests:** tests first (red, then green); ≥80% line coverage on new code (`uv run pytest --cov=roost --cov-fail-under=80`); web tests in jsdom.
- **Code rules:** files ≤800 lines (`roost/talk/tool_runner.py` and `turn.py` must not grow past 500: new logic goes in `roost/choices/` and `roost/talk/chat_feel.py`), functions <50 lines; frozen dataclasses and tuples, new objects in React state; pydantic at every boundary (`extra="forbid"` on HTTP bodies, `extra="ignore"` on tool arguments); plain-sentence refusals (422), "Already answered." for a lost race (409); no magic values (server numbers in `roost/constants.py`, web numbers in `web/src/components/chat/constants.ts` and `web/src/components/approvals/constants.ts`).
- **Tokens and bundle:** no colour or font size outside `web/src/styles/tokens.css` (`web/tests/tokens.test.ts`); the entry stays within `web/bundle-budget.json` (`npm run size`).
- **Dark only (V4)**, and the vocabulary (CLAUDE.md table, `tests/test_vocabulary.py`): Ask cards, Stuck, Take control / Give it back, On it, main bot; a bot is a bot.
- **Git:** commit after each task's green tests; stage files **by name** (never `git add -A`, `-a` or `.`); conventional messages with **no Co-Authored-By or any AI attribution line**.
- **Commands:** prefix with `cd /Users/blckit/Desktop/Code_Projects/roost &&`. One file: `ROOST_DATA_DIR=$(mktemp -d) ROOST_DESKS_DIR=$(mktemp -d) uv run pytest tests/<file>.py -q` (written `… uv run pytest` below). Web: `cd web && npx vitest run tests/<file>`, `npm test`, `npm run build && npm run size`.

## Design meets code (what exists today, and the choices this plan makes)

1. **First line: both, the prompt and the runner.** Today `run_turn` publishes On it with `activity.get(bot.id)` (usually `None`), then loads the roster, history, the memory section (recall can be slow) and only then publishes the placeholder bubble. The model may call a tool before it says anything, and the web shows typing dots with no words. This plan:
   - sets the activity to `FIRST_LINE_ACTIVITY` ("reading your message") and publishes On it **and** the placeholder bubble before anything is loaded (the placeholder closes on every path, a failed load included);
   - asks the model, in `chat_feel.py`, to start every reply with one short line saying what it is starting on ("On it: checking your Upwork inbox.") before any tool;
   - the web shows streamed text the moment it arrives, and if none has arrived after `FIRST_LINE_FALLBACK_MS` (700 ms) the bubble shows "On it: {activity}" in words (the tool lines already turn activities into words as they change). Typing dots never show alone.
   The fallback is UI only and never stored; the model's own first line is part of its stored reply.
2. **The chat already doesn't block, but never says so.** `Composer` disables only while its own POST is pending, and `TurnRunner.submit` queues a work item a busy bot picks up after its run. Missing: any sign that the message waits. `POST /api/threads/{id}/messages` returns `queued: true` when the bot was On it at submit (`bot_id in turns.busy_ids()`), and the web marks that message "Queued, I'll pick it up next" until a bot message appears after it. A test pins that the composer stays usable while the bot is On it.
3. **Options cards reuse the Ask card, with no new kind.** `approval_cards.kind` has a CHECK of `('ask','plan')`, so an options card is kind `ask` with one step whose `tool` is `ask_choice`. Its `arguments` hold `question`, `options` (2–4), `safe` (the index of the safe option, highlighted), `own` (whether "type your own" shows) and `why`; `rows` show them all (what shows is what is stored). `ApprovalCardOut` gains `choice: ChoiceOut | None`, filled from that step. Yes / Yes for this session are refused on it (422); its answers are `pick` (with `choice`), `own` (with `text`) and `no` (Dismiss). Approval-mode Ask cards are unchanged.
4. **Dismiss is No, and the same question is never asked again.** Every answer, a dismiss included, is saved as a `decision` memory of that bot ("{question}\nDecision: {answer}"; a dismiss is "No (dismissed)"). Before parking, `ask_choice` looks the question up in the bot's decisions (case, whitespace and closing punctuation folded): a match returns `ALREADY_DECIDED_TEXT` with the date and the answer, and no card opens. Forgetting the decision (Info → Decisions → Forget) lets the bot ask again.
5. **The question book is not duplicated.** The routines plan's `note_question` (Task 10) is for questions the bot can carry on without: it already picked a default and you answer later. `ask_choice` is for a choice the run waits on, and only in your own chat (`_may_open_cards`). Anywhere else (a handoff, a room, a routine) `ask_choice` returns `CHOICE_NOT_HERE_TEXT`: "Not asked: nobody can choose here. Go on with the safe option ({safe}) and say so", plus "or note it with note_question" when that tool is in the run. When the question book exists, its `answer` also calls `DecisionBook.record` (Task 5 adds that one line if `roost/questions/service.py` is present, else skips it and notes it in `progress.md`).
6. **Decisions reuse the memory store.** `MemoryKind` gains `"decision"` (no SQL change). It is in `BOT_KINDS` (a bot may `remember` a decision you stated in chat), not in `CAPTURE_KINDS` (the worker's auto-capture stays as it is). `GET /api/memories` gains an optional `kind` filter. Forget is the existing `DELETE /api/memories/{id}`.
7. **Stuck: where it turns Stuck, and what is missing.** A bot is Stuck only through `TurnRunner._idle_status` (an open Stuck card); every card has a reason (`REASON_WORDS`, or the bot's `ask_for_help` note). Gaps found:
   - `_status_frame` carries words only when a stay begins; a settle of a bot already Stuck, and every reload (`GET /api/bots` reads the empty `ActivityBoard`), shows "Stuck" with no reason;
   - `stuck_activity("")` is "Needs your help", with no reason;
   - `blocked_line` (rung 4) names no next step;
   - the restart path (`restore_stuck_on_boot`) publishes nothing when the database already says Stuck.
   One pure `stuck_status_line(card)` ("Stuck on upwork.com: a sign-in page. Take control to clear it.") fills every Stuck frame and `bot_out`'s activity for a Stuck bot; `blocked_line` ends with "Take control and do it yourself, or tell me another way." The routines plan's "retry once, then Stuck with a one-line reason" (Amendment R1) goes through the same card, so it inherits this.
8. **Links are already labelled by their real host, and stay so.** `linkHost` (M1's link-safety rule) shows the hostname, never a bare URL and never text a bot chose. That is the safe label and is kept. This plan adds tests that a bare URL in plain text and in markdown both render as the host, and a prompt rule: say what the link is in the sentence ("the invoice on stripe.com"), never paste a long address.
9. **Times.** The chat's clock is already Madrid's, but unlabelled; `components/board/taskChips.ts` and `components/notes/noteHelpers.ts` use the browser's zone. This plan labels the message time ("14:19 Madrid" in its `title` and accessible name), moves those two to Madrid, and adds a guard test refusing `toLocaleTimeString` / `toLocaleDateString` / `Intl.DateTimeFormat` without a `timeZone` anywhere in `web/src`. The prompt rule asks the bot to write times as "12:16 Madrid".
10. **Tapbacks don't exist.** The smallest version: a `reaction` message (role `user`, body JSON `{"target_id", "key"}`, `key` one of `REACTION_KEYS` or `null` to clear), posted by `PUT /api/threads/{thread_id}/messages/{message_id}/reaction`. It is never replayed to the model, queues no work, never makes a chat unread and never shows as a chat-list preview. The web folds them (newest per target wins) into a small chip under the message, with a picker in the message's hover actions.
11. **"Done" only once checked** is a prompt rule, plus one scripted test that the rule text reaches every run's instructions. No runtime check.

## Review Focus

**SECURITY REVIEW: the options card's stored-answer integrity** (after Task 5, before Batch C). As for Ask cards:
1. The question and options are sealed in `approval_cards:steps`; the wire card never carries `request` or `user_id`.
2. `pick` takes an index only. It is checked against the **stored** options (out of range: 422), and your line and the decision are built from the stored option text, never from text the client sends.
3. `own` is accepted only when the stored step allows it, 1–`CHOICE_OWN_ANSWER_MAX_CHARS` characters; `yes` and `yes_session` on an options card are 422.
4. One press wins (`store.close` guarded `UPDATE … RETURNING`); a second is 409; another user's card is 404; every answer needs `RequireOrigin`.
5. `ApprovedCalls.run` refuses `ask_choice` (nothing ever executes from an options card).
6. Taint: a card from a tainted run is marked, its `card_answer` item and its decision memory are tainted, and a tainted decision reaches later prompts the way any tainted memory does.
7. Dismiss records the decision, so a bot can't re-ask by re-phrasing case or spacing; a forgotten decision may be asked again (intended).
8. `ask_choice` parks only in your own chat; elsewhere it opens nothing.
Tests: Task 4 `test_ask_choice_parks_only_in_your_own_chat`, `test_a_decided_question_is_not_asked_again`; Task 5 `test_pick_uses_the_stored_option_text`, `test_a_pick_out_of_range_is_422`, `test_own_text_only_when_allowed`, `test_yes_on_an_options_card_is_422`, `test_only_one_press_wins_on_an_options_card`, `test_another_users_options_card_is_404`, `test_the_executor_never_runs_ask_choice`, `test_a_tainted_choice_taints_the_item_and_the_decision`.
Files: `roost/choices/*`, `roost/approvals/service.py`, `roost/approvals/models.py`, `roost/approvals/executor.py`, `roost/gateway/routes/approvals.py`, `roost/talk/tool_runner.py`.
Fix any CRITICAL or HIGH before Batch C.

## Shared Contract

**Constants (`roost/constants.py`):** `FIRST_LINE_ACTIVITY = "reading your message"`; `CHOICE_OPTIONS_MIN = 2`; `CHOICE_OPTIONS_MAX = 4`; `CHOICE_QUESTION_MAX_CHARS = 300`; `CHOICE_OPTION_MAX_CHARS = 120`; `CHOICE_WHY_MAX_CHARS = 300`; `CHOICE_OWN_ANSWER_MAX_CHARS = 1000`; `DECISIONS_LIST_MAX = 200`; `REACTION_KEYS = ("thumbs_up", "heart", "laugh", "check", "question")`.

**Web constants:** `web/src/components/chat/constants.ts`: `FIRST_LINE_FALLBACK_MS = 700`, `QUEUED_LINE = "Queued, I'll pick it up next"`, `REACTION_GLYPHS` (key → glyph and label), `MADRID_LABEL = "Madrid"`. `web/src/components/approvals/constants.ts`: `TYPE_YOUR_OWN = "Type your own"`, `DISMISS = "Dismiss"`, `SAFE_MARK = "Safe choice"`, `CHOICE_SEND = "Send"`.

**Names:**
- `roost/choices/models.py`: `CHOICE_TOOL = "ask_choice"`; `ChoiceArgs` (pydantic, `extra="ignore"`: `question`, `options: list[str]`, `safe: int`, `own: bool = True`, `why: str = ""`, validated against the constants, `safe` within `options`); `choice_step(args) -> PendingCall`; `choice_of(card) -> ChoiceView | None` (frozen: `question`, `options`, `safe`, `own`, `why`).
- `roost/choices/decisions.py`: `DECISION_SEPARATOR = "\nDecision: "`; `decision_text(question, answer)`, `parse_decision(text) -> tuple[str, str] | None`, `same_question(a, b) -> bool`; `Decision` (frozen: `memory_id`, `question`, `answer`, `decided_at`, `tainted`); `DecisionBook(memory: MemoryService)`: `record(user_id, bot_id, question, answer, *, tainted) -> Decision`, `find(user_id, bot_id, question) -> Decision | None`, `list(user_id, bot_id) -> tuple[Decision, ...]`.
- `roost/choices/tool.py`: `async def park_choice(arguments, *, cards: bool, tainted: bool, decisions, user_id, bot_id, has_question_book: bool) -> PendingCall | str`.
- `roost/choices/texts.py`: `CHOICE_PARKED_TEXT`, `ALREADY_DECIDED_TEXT = "Already decided on {date}: {answer}. Go on with that."`, `CHOICE_NOT_HERE_TEXT`, `BAD_CHOICE_ARGS_TEXT`, `PICK_LINE = "{answer}"` (your line is the option itself), `OWN_LINE = "{answer}"`, `DISMISS_LINE = "No thanks: {question} Go on without it, and don't ask again."`, `DISMISSED_ANSWER = "No (dismissed)"`, `CHOICE_OUT_OF_RANGE_TEXT = "Pick one of the options shown."`, `OWN_NOT_OFFERED_TEXT = "This card has no field for your own answer."`, `OWN_NEEDS_TEXT = "Type your answer in 1 to 1000 characters."`.
- `roost/stuck/texts.py`: `stuck_status_line(card: StuckCard) -> str`; `NEXT_STEP_TAKE_CONTROL = "Take control to clear it."`, `NEXT_STEP_BLOCKED = "Take control and do it yourself, or tell me another way."`.
- `roost/talk/chat_feel.py`: `FIRST_LINE_RULE`, `DONE_RULE`, `TIME_RULE`, `LINK_RULE`, `chat_feel_section() -> str`.
- `roost/talk/reactions.py`: `ReactionIn` (pydantic, `extra="forbid"`: `key: Literal[*REACTION_KEYS] | None`), `reaction_body(target_id, key) -> str`.

**Wire:**
- `POST /api/threads/{id}/messages` → `{"message_id": str, "queued": bool}`.
- `POST /api/approvals/{id}/answer` body: `{"answer": "yes"|"yes_session"|"no"|"accept"|"decline"|"edit"|"pick"|"own", "text"?: str, "choice"?: int}` (`choice` 0 to `CHOICE_OPTIONS_MAX - 1`).
- `ApprovalCardOut.choice: ChoiceOut | None` (`question`, `options`, `safe`, `own`, `why`).
- `GET /api/memories?bot_id=&kind=decision` (optional `kind`, one of `MEMORY_KINDS`).
- `PUT /api/threads/{thread_id}/messages/{message_id}/reaction` `{"key": … | null}` → 200 the stored `MessageOut` (RequireOrigin; another user's thread or a message not in that thread: 404).
- Message kinds: `reaction` (role `user`; body JSON `{"target_id", "key"}`; never replayed; no work item).
- `bot_status` for Stuck always carries `stuck_status_line(card)` as `activity`; `GET /api/bots` and `bot_out` give a Stuck bot that same line.

## Batches

- **Batch A — words at once, never blocked:** 1 → 2.
- **Batch B — options and decisions on the server:** 3 → 4 → 5. **SECURITY REVIEW** after 5.
- **Batch C — the web for options and decisions:** 6.
- **Batch D — honest Stuck and small touches:** 7 → 8.
- **Batch E — finish:** 9 (E2E) → 10 (docs).

Every task touches `roost/constants.py` or a shared web file, so tasks run one at a time.

---

### Task 1: Words on the server within a second, and the chat-feel prompt rules

Design meets code 1, 8, 9, 11.

**Files:**
- Create: `roost/talk/chat_feel.py`, `tests/test_first_line.py`, `tests/test_chat_feel_rules.py`.
- Modify: `roost/talk/turn.py` (set the activity to `FIRST_LINE_ACTIVITY`, publish On it and the placeholder first; wrap everything after the placeholder so it closes on any failure), `roost/talk/instructions.py` (add `chat_feel_section()`; `_ANSWER_STYLE` becomes "Answer briefly, result first. Name the page you read and link it."), `roost/constants.py`.

**Shapes:** `chat_feel_section()` joins four rules:
- `FIRST_LINE_RULE`: "Start every reply with one short line that says what you are starting on, before any tool (for example: \"On it: checking your Upwork inbox.\"). Then give updates only at real milestones."
- `DONE_RULE`: "Say done only once you checked it worked (you read it back, or the tool said so). Otherwise say drafted, waiting or blocked."
- `TIME_RULE`: "Write times in Madrid time with the label, like 12:16 Madrid."
- `LINK_RULE`: "Say what a link is in your sentence, then give the link. Never paste a long address on its own."

**Tests:**
- `tests/test_first_line.py`: `test_on_it_with_words_goes_out_before_history_and_memory_load` (a memory hook whose `prompt_section` waits on an `asyncio.Event`: the `bot_status` frame with `activity == FIRST_LINE_ACTIVITY` and the placeholder `message` frame are already published while it waits); `test_the_placeholder_closes_when_loading_fails` (history load raises: a `message_done` for the placeholder is published, then the error notice); `test_streamed_text_still_replaces_the_placeholder` (Ruling 15 order unchanged).
- `tests/test_chat_feel_rules.py`: `test_every_run_gets_the_chat_feel_rules` (own chat, handoff, room: all four rules in `build_instructions`); `test_the_answer_style_no_longer_asks_for_raw_urls`.

- [ ] Red → green; the full suite stays green.
- [ ] **Commit:** `git add roost/talk/chat_feel.py roost/talk/turn.py roost/talk/instructions.py roost/constants.py tests/test_first_line.py tests/test_chat_feel_rules.py && git commit -m "feat: every run says On it with words before it loads anything, and the bot opens with one line"`

### Task 2: The chat never blocks, and never shows dots without words

Design meets code 1, 2.

**Files:**
- Create: `web/src/components/chat/FirstLine.tsx`, `web/src/lib/queued.ts`, `web/src/components/chat/QueuedMark.tsx`, `tests/test_send_queued.py`, `web/tests/FirstLine.test.tsx`, `web/tests/queued.test.ts`, `web/tests/ChatComposer.test.tsx`.
- Modify: `roost/gateway/routes/threads.py` (`queued = thread.bot_id in turns.busy_ids()`, read **before** `submit`), `web/src/api/threads.ts` (`sendMessage` returns `{message_id, queued}`), `web/src/api/types.ts`, `web/src/pages/Chat.tsx` (keeps a set of queued ids in state, new copies only), `web/src/components/MessageRow.tsx` (the empty placeholder renders `FirstLine`, a queued user message renders `QueuedMark`), `web/src/components/MessageList.tsx` (passes the queued set and the bot's activity), `web/src/components/chat/constants.ts`.

**Shapes:**
- `FirstLine({ text, activity, since })`: streamed text when there is any (with the caret, as today); before `FIRST_LINE_FALLBACK_MS`, the typing dots; after it, "On it: {activity}" in words, with the dots beside it. With no activity it says "On it: reading your message".
- `stillQueued(messages, queuedIds): ReadonlySet<string>`: a queued id stays only while no `role: "bot"` message (a placeholder included) comes after it in the thread.

**Tests:**
- `tests/test_send_queued.py`: `test_a_message_to_a_resting_bot_is_not_queued`; `test_a_message_to_a_bot_on_it_is_queued_and_runs_after` (a scripted model held on an event: the second send returns `queued: true`, and its run follows the first); `test_queued_is_still_404_for_another_users_thread`.
- `web/tests/FirstLine.test.tsx`: `shows streamed text at once`; `shows words after the fallback delay` (fake timers); `never shows dots alone after the delay`.
- `web/tests/queued.test.ts`: `a queued message stays queued until a bot message follows it`; `a new set each time` (no mutation).
- `web/tests/ChatComposer.test.tsx`: `the composer stays usable while the bot is On it`; `a queued send shows "Queued, I'll pick it up next"`.

- [ ] Red → green; `npm test` and `npm run build && npm run size` green.
- [ ] **Commit:** `git add roost/gateway/routes/threads.py web/src/components/chat/FirstLine.tsx web/src/lib/queued.ts web/src/components/chat/QueuedMark.tsx web/src/api/threads.ts web/src/api/types.ts web/src/pages/Chat.tsx web/src/components/MessageRow.tsx web/src/components/MessageList.tsx web/src/components/chat/constants.ts tests/test_send_queued.py web/tests/FirstLine.test.tsx web/tests/queued.test.ts web/tests/ChatComposer.test.tsx && git commit -m "feat: the chat says Queued while a bot works, and its bubble always has words"`

### Task 3: Decision memories

Design meets code 4, 6.

**Files:**
- Create: `roost/choices/__init__.py`, `roost/choices/decisions.py`, `tests/test_decisions.py`.
- Modify: `roost/memory/models.py` (`MemoryKind` gains `"decision"`; `CAPTURE_KINDS` excludes it), `roost/memory/tool_specs.py` (the `remember` description names decisions: "a choice the user made, as the question and their answer"), `roost/gateway/routes/memories.py` (optional `kind: Literal[...] | None` query), `roost/memory/service.py` (`list_for_bot(..., kind=None)`), `roost/constants.py`, `tests/test_memories_api.py` (the two route tests).

**Shapes:** see the Shared Contract. `record` saves `MemoryDraft(kind="decision", text=decision_text(q, a), bot_id=bot_id, source="user", created_by_bot=None, pinned=False, tainted=tainted)`; a save that hits the fingerprint of an identical decision returns the existing one. `find` compares `same_question` over `list` (at most `DECISIONS_LIST_MAX`, newest first). `same_question` folds case (`casefold`), whitespace runs and trailing `?.!` .

**Tests:**
- `test_decision_text_round_trips` and `test_parse_decision_refuses_other_text`;
- `test_same_question_folds_case_space_and_closing_marks`;
- `test_record_then_find_then_forget` (after `MemoryService.forget`, `find` is `None`);
- `test_decisions_are_per_bot_and_per_user` (another bot's or user's decision is never found);
- `test_a_decision_is_sealed_at_rest` (raw `memories.text` starts with `enc:v2`);
- `test_the_kind_filter_lists_only_decisions` and `test_an_unknown_kind_is_422` (route);
- `test_auto_capture_never_saves_a_decision`.

- [ ] Red → green.
- [ ] **Commit:** `git add roost/choices/__init__.py roost/choices/decisions.py roost/memory/models.py roost/memory/tool_specs.py roost/memory/service.py roost/gateway/routes/memories.py roost/constants.py tests/test_decisions.py tests/test_memories_api.py && git commit -m "feat: decisions are memories of their own kind, found again by their question"`

### Task 4: `ask_choice` parks the run on an options card

Design meets code 3, 4, 5; Review Focus items 1, 8.

**Files:**
- Create: `roost/choices/models.py`, `roost/choices/tool.py`, `roost/choices/texts.py`, `tests/test_ask_choice.py`.
- Modify: `roost/talk/tool_catalog.py` (`ask_choice`, kind `read`, every bot, its description: "Ask the user to choose when you truly need their choice to go on: one question, 2 to 4 short options, the safe one marked. Use it at most once per run; never for things you may just do."), `roost/talk/tool_runner.py` (dispatch `ask_choice` to `park_choice` before the gate's page logic, like `ask_for_help`; a `PendingCall` sets `self.parked`; ToolRunner takes `decisions: DecisionBook | None`), `roost/talk/turn.py` (pass `inputs.decisions`; `RunInputs` gains `decisions: DecisionBook | None = None`), `roost/talk/runner.py` (`_inputs` and `run_turn` pass the wired `DecisionBook`), `roost/approvals/models.py` (`ChoiceOut`, `ApprovalCardOut.choice`, filled in `approval_card_out` from `choice_of`), `roost/gateway/app.py` (build one `DecisionBook` and hand it to `TurnRunner`), `roost/constants.py`, `tests/test_every_bot_tools.py`.

**Shapes:**
- `park_choice`: bad arguments → `BAD_CHOICE_ARGS_TEXT` (no card); `cards` false → `CHOICE_NOT_HERE_TEXT.format(safe=options[safe])` (+ the note_question clause when `has_question_book`); a `find` match → `ALREADY_DECIDED_TEXT` with the Madrid date; else `choice_step(args)` with `title=question`, `topic=None`, rows Question / Option 1..n / Safe choice / Why.
- `TurnRunner._on_park` needs no change: the parked step becomes an `ask` card as today, and the bot shows Asking you.

**Tests:**
- `test_ask_choice_parks_only_in_your_own_chat` (own chat: a card with the stored options; handoff, room and a run outside the queue: the not-here text and no card);
- `test_a_decided_question_is_not_asked_again` (a decision for "Keep it as is?" exists: `ask_choice("keep it as is")` returns the already-decided text, no card);
- `test_bad_choice_arguments_are_refused` (1 option, 5 options, `safe` out of range, an option over `CHOICE_OPTION_MAX_CHARS`);
- `test_the_options_card_shows_every_stored_argument` (rows, and `ApprovalCardOut.choice`);
- `test_a_tainted_run_opens_a_marked_card`;
- `test_every_bot_has_ask_choice` (in `tests/test_every_bot_tools.py`).

- [ ] Red → green.
- [ ] **Commit:** `git add roost/choices/models.py roost/choices/tool.py roost/choices/texts.py roost/talk/tool_catalog.py roost/talk/tool_runner.py roost/talk/turn.py roost/talk/runner.py roost/approvals/models.py roost/gateway/app.py roost/constants.py tests/test_ask_choice.py tests/test_every_bot_tools.py && git commit -m "feat: ask_choice parks a run on an Ask card with 2 to 4 options, the safe one marked"`

### Task 5: Answering an options card, and the decision it leaves

Design meets code 3, 4, 5; Review Focus items 2–7.

**Files:**
- Create: `tests/test_choice_answers.py`.
- Modify: `roost/approvals/service.py` (`CHOICE_ANSWERS = {"pick", "own", "no"}`; `_check` picks the answer set by `choice_of(card)`; `_answer_choice` closes the card first, then posts your line from the stored option or your own text, records the decision, and queues a `card_answer` item carrying the card's taint), `roost/approvals/executor.py` (`run` returns a failed `StepOutcome` for `ask_choice` without calling anything), `roost/gateway/routes/approvals.py` (`AnswerIn` gains `"pick"`, `"own"` and `choice: int | None = Field(None, ge=0, le=CHOICE_OPTIONS_MAX - 1)`), `roost/gateway/app.py` (hand the `DecisionBook` to `ApprovalService`), and, only if `roost/questions/service.py` exists, `roost/questions/service.py` (`answer` also calls `DecisionBook.record`) with `tests/test_question_book.py` (one test, `test_an_answered_question_becomes_a_decision`).

**Shapes:** a `pick` posts the option text as your `card_answer` line (role `user`); `own` posts your text; `no` posts `DISMISS_LINE` and records `DISMISSED_ANSWER`. The card closes as `approved` for `pick`/`own` and `declined` for `no`. Nothing runs through `ApprovedCalls`.

**Tests:**
- `test_pick_uses_the_stored_option_text` (the client cannot send option text: `text` is ignored on `pick`);
- `test_a_pick_out_of_range_is_422` and `test_a_pick_without_a_choice_is_422`;
- `test_own_text_only_when_allowed` (card with `own: false`: 422) and `test_own_text_bounds`;
- `test_yes_on_an_options_card_is_422` (and `yes_session`, `accept`);
- `test_dismiss_is_no_and_records_the_decision` (then `ask_choice` on the same question returns the already-decided text);
- `test_only_one_press_wins_on_an_options_card`;
- `test_another_users_options_card_is_404` and `test_every_answer_needs_the_origin`;
- `test_the_executor_never_runs_ask_choice`;
- `test_a_tainted_choice_taints_the_item_and_the_decision`;
- `test_the_bot_carries_on_after_a_pick` (scripted: the next run's turns hold your pick as a user turn).

- [ ] Red → green; the full suite stays green.
- [ ] **Commit:** `git add roost/approvals/service.py roost/approvals/executor.py roost/gateway/routes/approvals.py roost/gateway/app.py tests/test_choice_answers.py && git commit -m "feat: an options card takes a pick, your own words or a dismiss, and remembers the decision"` (add `roost/questions/service.py tests/test_question_book.py` to the `git add` when they changed).

**SECURITY REVIEW: the options card's stored-answer integrity** (Review Focus), here at the end of Batch B. Fix any CRITICAL or HIGH before Batch C.

### Task 6: The options card and the Decisions list on the web

Design meets code 3, 4, 6.

**Files:**
- Create: `web/src/components/approvals/ChoiceCard.tsx`, `web/src/components/profile/DecisionsCard.tsx`, `web/src/lib/decisions.ts`, `web/tests/ChoiceCard.test.tsx`, `web/tests/DecisionsCard.test.tsx`, `web/tests/decisions.test.ts`.
- Modify: `web/src/components/approvals/ApprovalMessage.tsx` (a card with `choice` renders `ChoiceCard`), `web/src/components/approvals/useAnswer.ts` (`send(answer, { text?, choice? })`), `web/src/components/approvals/constants.ts`, `web/src/lib/approvals.ts` (`closedLine` for an options card: "You answered." / "Dismissed: counts as No."), `web/src/api/approvals.ts`, `web/src/api/memories.ts` (`listMemories(botId, { kind })`), `web/src/api/types.ts`, `web/src/components/profile/InfoTab.tsx` (Decisions under the memory panel), `web/src/styles/approvals.css` and `web/src/styles/profile.css` (the cards' classes, tokens only).

**Shapes:**
- `ChoiceCard`: the question; one button per option, the safe one `variant="primary"` with the `SAFE_MARK` badge (the word, never colour alone); a "Type your own" field and Send when `own`; a Dismiss icon button (label `DISMISS`); the "from web content" badge when tainted; the `why` line, quiet. Buttons disable after a press; errors show in an `ErrorNotice`.
- `DecisionsCard`: "Decisions" heading, each decision's question, answer and Madrid date ("22 Oct, 14:19 Madrid"), a Forget button (`DELETE /api/memories/{id}`), an empty line "No decisions yet." It reloads on `boardVersion.memories`.
- `parseDecision(text)` mirrors the server's `DECISION_SEPARATOR`.

**Tests:**
- `ChoiceCard`: `marks the safe option in words`; `a pick sends only the index`; `type your own sends the text`; `dismiss sends no`; `buttons lock after a press`; `an answered card is one quiet line`.
- `DecisionsCard`: `lists decisions with a Madrid date`; `forget removes it and calls the API`; `says when there are none`.
- `decisions.test.ts`: `parses a decision` and `ignores other memory text`.

- [ ] Red → green; `npm test`, `npm run build && npm run size` and `web/tests/tokens.test.ts` green.
- [ ] **Commit:** `git add web/src/components/approvals/ChoiceCard.tsx web/src/components/profile/DecisionsCard.tsx web/src/lib/decisions.ts web/src/components/approvals/ApprovalMessage.tsx web/src/components/approvals/useAnswer.ts web/src/components/approvals/constants.ts web/src/lib/approvals.ts web/src/api/approvals.ts web/src/api/memories.ts web/src/api/types.ts web/src/components/profile/InfoTab.tsx web/src/styles/approvals.css web/src/styles/profile.css web/tests/ChoiceCard.test.tsx web/tests/DecisionsCard.test.tsx web/tests/decisions.test.ts && git commit -m "feat: options cards with the safe choice marked and your own answer, and a Decisions list on Info"`

### Task 7: Stuck always says why and what next

Design meets code 7.

**Files:**
- Create: `tests/test_stuck_says_why.py`, `web/tests/StuckLine.test.tsx`.
- Modify: `roost/stuck/texts.py` (`stuck_status_line`; `stuck_activity` delegates to it; `blocked_line` ends with `NEXT_STEP_BLOCKED`; an empty host says "Needs your help: {note}. Take control to clear it."), `roost/talk/runner.py` (`_status_frame` carries `stuck_status_line(card)` on every Stuck frame it publishes; `restore_stuck_on_boot` publishes it even when the database already says Stuck), `roost/gateway/routes/bots.py` (a Stuck bot's `activity` in `GET /api/bots` and `GET /api/bots/{id}` is its open card's line), `web/src/components/StuckCard.tsx` (only if the audit finds a state, blocked included, that shows no next-step button).

**Audit (write it into the test file's docstring):** every place a status turns Stuck (`grep -rn "BotStatus.STUCK" roost`): today only `TurnRunner._idle_status`. Every card reason (`REASON_WORDS` keys) × host present / empty × `suggest_main_browser` × blocked.

**Tests:**
- `test_every_stuck_line_has_a_reason_and_a_next_step` (the table above; each line has a reason clause and one of the next-step sentences);
- `test_the_status_frame_always_carries_the_line` (stay begins, already Stuck before the run, a settle while Stuck);
- `test_a_reload_shows_the_reason` (`GET /api/bots` after the `ActivityBoard` is cleared);
- `test_a_restart_republishes_the_line`;
- `test_only_idle_status_sets_stuck` (a source scan of `roost/` for `BotStatus.STUCK` assignments outside `_idle_status` and the model/label tables);
- `web/tests/StuckLine.test.tsx`: `the header shows the Stuck reason`; `a blocked card still offers Take control`.

- [ ] Red → green.
- [ ] **Commit:** `git add roost/stuck/texts.py roost/talk/runner.py roost/gateway/routes/bots.py tests/test_stuck_says_why.py web/tests/StuckLine.test.tsx && git commit -m "fix: Stuck always shows a one-line reason and a next step, after a reload too"` (add `web/src/components/StuckCard.tsx` when it changed).

### Task 8: Small touches: Madrid labels, labelled links, tapbacks

Design meets code 8, 9, 10.

**Files:**
- Create: `roost/talk/reactions.py`, `tests/test_reactions.py`, `web/src/lib/reactions.ts`, `web/src/components/chat/Reactions.tsx`, `web/tests/reactions.test.ts`, `web/tests/Reactions.test.tsx`, `web/tests/madridTime.test.ts`, `web/tests/linkLabels.test.tsx`.
- Modify: `roost/talk/store.py` (`MessageKind` gains `"reaction"`), `roost/gateway/routes/threads.py` (the `PUT …/reaction` route), `roost/talk/chats.py` (a reaction is never a chat-list preview), `roost/constants.py`, `web/src/lib/chatTime.ts` (`formatClockLabel(iso)` → "14:19 Madrid"), `web/src/components/chat/MessageActions.tsx` (the time's `title` and `aria-label` use the label; the reaction picker sits beside Copy), `web/src/components/MessageList.tsx` (hides `reaction` rows, passes folded reactions to rows), `web/src/components/MessageRow.tsx`, `web/src/components/board/taskChips.ts` and `web/src/components/notes/noteHelpers.ts` (Madrid `timeZone`), `web/src/lib/unread.ts` (a reaction never makes a chat unread), `web/src/api/threads.ts`, `web/src/api/types.ts`, `web/src/components/chat/constants.ts`.

**Shapes:** see Design meets code 10 and the Shared Contract. `foldReactions(messages): ReadonlyMap<targetId, key>` (newest wins, `null` clears). The route checks the target is a message in that thread of that user, adds the `reaction` row and publishes it as a `message` frame. Glyphs live only in `REACTION_GLYPHS`, each with a text label for screen readers.

**Tests:**
- `tests/test_reactions.py`: `test_a_reaction_is_stored_sealed_and_published`; `test_a_reaction_never_reaches_the_model_or_queues_work`; `test_an_unknown_key_is_422`; `test_a_reaction_on_another_threads_message_is_404`; `test_another_users_thread_is_404`; `test_a_reaction_is_never_a_chat_preview`; `test_the_route_needs_the_origin`.
- `web/tests/reactions.test.ts`: `newest reaction wins`, `null clears`, `no mutation`.
- `web/tests/Reactions.test.tsx`: `pick a tapback and see it under the message`; `the chip has a text label`.
- `web/tests/madridTime.test.ts`: `no date or time formatting without a timeZone in web/src` (source scan); `the message time says Madrid`.
- `web/tests/linkLabels.test.tsx`: `a bare URL in plain text shows its host`; `a bare URL in markdown shows its host`; `a labelled markdown link shows the real host, not the label`.

- [ ] Red → green; `npm test`, `npm run build && npm run size` green.
- [ ] **Commit:** `git add roost/talk/reactions.py roost/talk/store.py roost/gateway/routes/threads.py roost/talk/chats.py roost/constants.py web/src/lib/reactions.ts web/src/components/chat/Reactions.tsx web/src/lib/chatTime.ts web/src/components/chat/MessageActions.tsx web/src/components/MessageList.tsx web/src/components/MessageRow.tsx web/src/components/board/taskChips.ts web/src/components/notes/noteHelpers.ts web/src/lib/unread.ts web/src/api/threads.ts web/src/api/types.ts web/src/components/chat/constants.ts tests/test_reactions.py web/tests/reactions.test.ts web/tests/Reactions.test.tsx web/tests/madridTime.test.ts web/tests/linkLabels.test.tsx && git commit -m "feat: tapbacks, times labelled Madrid everywhere, and tests that links show their real host"`

### Task 9: E2E: the chat feel

**Files:**
- Create: `web/e2e/chat-feel.spec.ts`.
- Modify: `web/e2e/fixtures/team-script.json` (add only new bot keys, `"Picker"` and `"Slowpoke"`). **First** run `git status --short web/e2e/fixtures/team-script.json`: if it shows uncommitted edits you did not make, stop and report to the controller instead of editing it.

**Scenarios** (scripted gateway, `ROOST_DESKS_DIR=$(mktemp -d) make e2e`, disk guard first):
- `a run shows words within a second`: send to Slowpoke (its first step waits); within 1000 ms the bubble shows "On it:" text, never dots alone.
- `the composer stays usable and says Queued`: while Slowpoke works, send a second message; the box is enabled, "Queued, I'll pick it up next" shows, and goes once its reply starts.
- `an options card`: Picker calls `ask_choice` with three options; the safe one is marked in words; pick one; your line shows; Info → Decisions lists it with a Madrid date; Forget removes it.
- `dismiss counts as No and is not asked again`: Picker asks the same question again in its next script step; the chat shows its already-decided line, no second card.
- `Stuck says why`: the fake desk's sign-in page; the header says "Stuck on …: a sign-in page. Take control to clear it." and keeps it after a reload.
- `a tapback`: hover a bot message, pick a tapback, reload, it is still there.

- [ ] Green, with the full Playwright suite green.
- [ ] **Commit:** `git add web/e2e/chat-feel.spec.ts web/e2e/fixtures/team-script.json && git commit -m "test: E2E for words within a second, Queued, options cards, Decisions, Stuck reasons and tapbacks"`

### Task 10: Docs

**Files:**
- Modify: `CLAUDE.md` (Documentation Map: this plan; Architecture: one short paragraph on the first line, Queued, options cards in `roost/choices/` reusing Ask cards, decisions as `decision` memories, `stuck_status_line`, tapbacks as `reaction` messages; the vocabulary table gains "Options card · Decisions · Tapback" only if `tests/test_vocabulary.py` needs them), `tests/test_docs.py` (`test_the_documentation_map_names_the_chat_feel_plan`; `test_the_architecture_section_says_where_choices_live`).

- [ ] `uv run pytest tests/test_docs.py tests/test_vocabulary.py -q` green; then the full suite with `--cov=roost --cov-fail-under=80`, `cd web && npm test && npm run build && npm run size`.
- [ ] **Commit:** `git add CLAUDE.md tests/test_docs.py && git commit -m "docs: the v1 chat feel in CLAUDE.md"`

## Out of scope

- A "type while it streams" stop/redirect of a running turn (the message queues; Stop exists).
- Tapbacks from bots, custom emoji, more than one reaction per message.
- Any change to approval modes' own Ask cards, the question book's UI, or routines.
- Record Undo, voice, files in the composer.
