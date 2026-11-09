# Token savings (owner, 2026-11-06/07)

The owner asked where the bots' tokens go and for a little economy. A read-only study (2026-11-06) measured the
live `token_usage` rows and the prompt pieces: about 40k tokens of context per model call, and a third of the cached
volume written again on every call. Cache writes cost about 25 times a read, so the writes were 85–90% of a step's
cost.

## Why

Each model step is a fresh SDK `query()` with `max_turns=1`, and the whole transcript (the chat, then every tool
result of the run) went as ONE text block. The prompt cache matches whole blocks, so a step that added one tool
result changed that block and wrote all of it again. Tools and the system prompt stayed cache reads.

## What was built

1. **One block per turn** (`roost/llm/claude_sdk.py` `_content`): every step is one streamed user message with a
   text block per turn, so a step that only adds turns reads everything before them (the API looks back about 20
   blocks for an earlier cache entry). An image rides right after its own turn (`ImagePart.after_turn`): the
   newest look's screenshot after that look's result (`roost/talk/steps.py` `with_screen`), your chat pictures
   after the chat's turns (`roost/talk/turn.py`). A new look still turns the previous look's mark into "not shown",
   which rewrites only the steps since that look.
2. **A routine run replays only the line that launched it** (`_first_claimed_handoff_line` in
   `roost/talk/turn.py`, now for `ROUTINE` items as well as handoffs): the run log held every earlier launch and
   reply (about 6k tokens per step, growing daily). The routine section already carries the slot, the earlier
   answers and a watch's change. A run with a card answer in it still loads the whole page.
3. **A shorter glance** (`CU_GLANCE_TARGETS_MAX = 30`): an act's text-only glance lists the first 30 controls
   ("Controls (30 of 57; look lists them all)") and numbers only those; a look still lists `CU_LOOK_TARGETS_MAX`.

## Checking it live

After the deploy, two consecutive steps of one browser run should show `cache_write` near the size of the newest
result (1–3k) and `cache_read` near everything else. If the CLI merged the blocks, `cache_write` per call stays
near 13k and this needs another look.

## Not done (the owner's call)

A smaller tool set per run (113 tools, ~22k tokens, read from cache), a cheaper model per routine, and shorter fixed
instructions.
