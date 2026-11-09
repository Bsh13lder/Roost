# Token usage (owner, 2026-11-04)

> "Token usage is important and I want to track it somehow."

Roost had no usage record (`NoUsageSource`: the usage *limit* still cannot be read, so the full-limit switch stays
off). This adds a record of what each model call cost, summed per bot and per day, and shows it on the web and the
phone. Nothing changes how a run behaves: no usage, no record.

## Capture

- `roost/llm/types.py`: `Usage(input, output, cache_read, cache_write)` and `TurnDone.usage` (default `None`).
- `ClaudeSdkModel` reads the SDK's `ResultMessage.usage` (claude-agent-sdk 0.2.170: `input_tokens`,
  `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`) through `usage_from_sdk`
  (`roost/usage/counts.py`). It is external data: a count that is not a non-negative int up to `USAGE_COUNT_MAX`
  reads as 0, and a dict with no count is `None`. `total_cost_usd` is not kept (a subscription has no bill).
- The scripted models (`ScriptedModel`, `ScriptedTeamModel`, `ScriptedWorker`) report `SCRIPTED_USAGE` on every
  call, so tests and the scripted E2E see numbers. A test's own hand-written `TurnDone("end_turn")` reports none.
- Attribution is a context variable (`roost/usage/scope.py`): `TurnRunner._run_batch` (and `run_turn`) opens a
  `UsageScope(recorder, user_id, bot_id, kind)` with the kind from the batch's first item (message, card answer
  and trigger → `chat`; `routine`, `handoff`, `room`). `run_helper` narrows it to `helper`. `ask_worker` records
  as `background` with the run's bot. Background tasks spawned from a run copy its context, so a memory capture,
  summary, lesson, gate check (owner words, auto-review, create check, standing check) counts for that bot. Outside
  a run, the English fix (`EnglishCorrector`) and the teach draft (`TeachService`) open a `background_scope` with
  their bot. A call with no scope is not recorded (no user to give it to).
- The two places that read a model's stream call `note_usage` on `TurnDone`: `roost/talk/steps.py` (every run and
  helper step) and `roost/memory/worker.py` (`ask_worker`). A failing recorder is logged and never breaks a call.

## Store (schema v39, `token_usage`)

One row per user, bot (`NULL` for a job with no bot), Madrid day, kind and model, with the four counts and `calls`
(the number of model calls). `TokenUsageStore.add` is one upsert on the unique index
`(user_id, IFNULL(bot_id, ''), day, kind, model)`, so two runs at once never lose a count. Every query names
`user_id`. Counts, kinds and model ids are metadata, not user content, so they are plain columns (like ids,
timestamps and status). There is no FK on `bot_id`: a retired bot's history stays and reads as "Retired bot".
The migration is self-contained in one step, so it can be renumbered on merge.

## API

- `GET /api/usage?days=N` (default 7, 1 to 90, else 422): the old `readable` / `remaining_fraction` /
  `resets_at`, plus `days`, `today`, `total`, `today_total`, `per_day` (dense, oldest first), `bots` (each with
  `name`, `total`, `today_total`, `per_day`, busiest first), `background` and `busiest` (`null` with none).
- `GET /api/bots/{id}/usage?days=N`: one bot's `total`, `today_total` and `per_day`; another user's bot is 404.
- A counts object is `input`, `output`, `cache_read`, `cache_write`, `calls`, and the server-reckoned `tokens_in`
  (input + cache read + cache write), `tokens_out` (output) and `tokens` (both).

## Web and phone

- Web: the bot's Settings page (the old Info rows) has a lazy Usage fold (`web/src/components/usage/`): Today,
  Last 7 days, in · out, and seven bars from tokens.css values. Home shows one quiet line,
  "Tokens today: N · this week: M · busiest: <bot>" (`TokensLine.tsx`), hidden if the call fails.
- Phone: the same fold on the bot's Settings page (`mobile/lib/profile/folds/usage_fold.dart`) and the line in
  Settings (`mobile/lib/features/settings/usage_line.dart`). The app version is not bumped here.
