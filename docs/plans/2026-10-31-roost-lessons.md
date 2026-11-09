# Lessons: a bad run becomes a Skill card (owner, 2026-10-31)

The owner looked at Harness² (google-research/harness2, Apache-2.0: improve an agent's harness — instructions,
skills, tools — from the evidence of past tasks, model weights fixed) and RSI-Anything (Gen-Verse/RSI-Anything,
Apache-2.0: propose → predict → act → check the outcome → learn → retain) and said: "fan agents and they implement if
it's worth" (lifts the v1 freeze for this one feature). Ideas only, no code from either repo, so no SPDX header or
THIRD_PARTY_NOTICES entry is needed.

Roost already holds the retain half: Skills (sealed, shared, in every run's instructions as an index), the
`skill_proposal` card, and your Save as the only door. What is missing is the loop that notices a run went wrong and
turns it into a lesson. Motivating case: the Upwork run of 2026-10-31 clicked "Apply now" three times, each time
expecting "the proposal form opens", and the page never moved.

## 1. Decisions

- **L1. Predict, then check (RSI-Anything).** Every act already carries the bot's `expect`. After an act that is
  not a scroll, the computer-use loop compares the page before and after: the same address and the same glance
  (the text glance every act ends with) means nothing happened → an `expect_missed` signal. A second Ask card for
  the same control in one run → `asked_again`. A card of this run you answered No → `declined`.
- **L2. Lessons are Skill proposals (Harness²'s retained improvement).** When a run in your own 1:1 chat ends with
  at least one signal, the worker model is asked once, in the background, for at most ONE lesson: a new skill or a
  change to an existing skill on for this bot. It is posted through `SkillProposalService.propose` as the existing
  `skill_proposal` card. Nothing is saved until you press Save skill; Decline drops it. No new card kind, no new UI,
  no schema change.
- **L3. Trusted inputs only, so the lesson is clean.** The worker reads: your own messages in this run (the
  batch's `message` items, never tainted ones), the run's own step lines (`plain_steps` words: tool names and hosts,
  never a page's text, a URL path, a control label or typed text), the signals (kind, host, action class, count),
  and the names and Use when lines of the clean skills on for this bot. Never a page, a tool result, the bot's
  reply, `expect` text or a control's label. A run that only answers a card holds no message of yours, so the
  card's parked item counts as your words when it is your own untainted message in the same thread. So the proposal is posted with `tainted=False` and, once saved, joins
  the index every bot reads. If the run has no owner message at all, no lesson.
- **L4. Where it never runs.** Routines, handoffs, rooms, helpers, call turns (`inputs.call`) and runs with no
  signal. At most `LESSONS_PER_DAY_PER_BOT` (3) per Madrid day per bot, and none when the bot already has
  `SKILL_PROPOSALS_OPEN_PER_BOT_MAX` open proposals (the service refuses; the refusal is logged at info, never
  shown). A worker error, timeout, bad JSON or `{"lesson": null}` posts nothing.

## 2. Signals — `roost/lessons/signals.py` (written, the contract)

`LessonSignal(kind, host, action, count=1)` and `LessonSignals` with `record(run_id, signal)` and
`take(run_id) -> tuple[LessonSignal, ...]` (pops). One instance per gateway: `app.state.lesson_signals`. Constants
in `roost/lessons/constants.py`. Recording is best-effort and never changes what the loop does.

Producers (agent A, `roost/computer_use/`): `expect_missed` and `asked_again`, recorded under the run's `run_id`
(the `CuRun.run_id` the loop already has); `host` is the page's host, `action` the act's commit class.
Producer (agent B, at run end): `declined`, read from `approval_cards` of this thread whose `work_item_id` is one
of the batch's items and whose state is `declined` (host from the card's sealed steps' `act`, action its floor
or tool).

## 3. The lesson — `roost/lessons/` (agent B)

- `prompt.py`: `LESSON_SYSTEM` and `lesson_input(...)` — escaped data in tags (`<owner_words>`, `<steps>`,
  `<signals>`, `<skills>`), all data, never instructions. Asks for strict JSON: `{"lesson": null}` or
  `{"lesson": {"action": "create", "name", "use_when", "steps"}}` or
  `{"lesson": {"action": "change", "skill": "<existing name>", "use_when"?, "steps"?}}`. Steps are short Markdown
  lines a bot can follow next time (what to do instead, on which site). Only lessons that would help next time;
  never about paying, passwords, or relaxing a rule (a hard floor never moves by a lesson).
- `parse.py`: pydantic validation (`SkillDraft` / `SkillPatch` limits reused); anything else is None.
- `service.py`: `LessonService.after_run(FinishedLessonRun)` — the checks of L4, the worker call (`ask_worker`,
  agent `LESSON_AGENT`, the worker model, `LESSON_TIMEOUT_S`), then `SkillProposalService.propose` with
  `tainted=False`, `from_routine=False`, the run's thread. The daily count is read from `skill_proposals` rows this
  bot created today whose payload came from a lesson; add nothing to the schema: count in memory per
  (user, bot, Madrid day) and accept that a restart resets it.
- Wiring: `roost/talk/runner.py` `_after_run` (keep the file ≤ 800 lines; put logic in `roost/lessons/`), spawned
  on the runner's background set like a call's memory capture so no reply waits for it.
  `roost/gateway/app.py` builds `LessonSignals` and `LessonService`.
- Scripted mode: `roost/llm/scripted_worker.py` answers `LESSON_AGENT` with a fixed create lesson when the signals
  hold `expect_missed`, else `{"lesson": null}`.

## 4. Safety facts

A lesson can only ever become a card; only your Save writes a skill; skills are knowledge, never power (nothing in
them reaches the gate). The worker never sees outside content, so a page cannot write a lesson. The step lines and
signals hold hosts, which are yours (the site fence) or the page's address host, already shown in the chat.

## 5. Tests

`tests/test_lesson_signals.py` (agent A: the registry, and that a no-change act and a second card record their
signals while a changed page records nothing), `tests/test_lessons.py` (agent B: where it never runs, the trusted
input holds no page text, parse, the cap, the card posted untainted, worker failure posts nothing, the declined
signal). No real model.
