"""The fixed values of lessons (docs/plans/2026-10-31-roost-lessons.md): one place, no magic numbers elsewhere."""

from __future__ import annotations

LESSON_SIGNALS_PER_RUN_MAX = 10      # distinct signals one run keeps
LESSON_SIGNAL_RUNS_KEPT = 64         # runs whose signals wait in memory for their end
LESSON_AGENT = "lesson"              # the worker request's agent name (scripted mode answers it too)
LESSONS_PER_DAY_PER_BOT = 3          # lesson cards one bot may post per local day
LESSON_TIMEOUT_S = 30.0
LESSON_STEP_LINES_MAX = 40           # the run's own step lines the worker reads
LESSON_OWNER_CHARS_MAX = 2000        # your words from this run the worker reads
LESSON_SKILLS_MAX = 40               # clean skills on for the bot whose name and Use when the worker reads
LESSON_LESSON_STEPS_MAX = 12         # steps one lesson's skill may hold (as a list from the worker)
LESSON_DECLINED_CARDS_MAX = 5        # declined cards of one run read for signals
# Owner, 2026-11-07: in your own chat a bot does everything itself and only paying asks, so a lesson whose words
# teach it to stop and ask you is dropped (lower-case phrases, matched in the name, Use when and steps).
LESSON_ASKING_PHRASES = (
    "ask the user", "ask the owner", "ask them", "ask you", "ask how to proceed", "ask for next steps",
    "wait for the user", "wait for their answer", "wait for the owner", "ask before",
)
