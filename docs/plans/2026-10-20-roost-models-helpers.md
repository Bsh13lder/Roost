# Roost Models & Helpers, Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. The SDD workspace is `.superpowers/sdd/2026-10-20-roost-models-helpers/` (`contract.md`, one `task-N-brief.md` per task, `progress.md`).

**Goal:** Each bot runs on the model and effort you pick in its Info (Fable 5.1, Sonnet 5.5 or Opus 5.5; Sonnet 5.5 by default); the main bot proposes a change with an Ask card or makes it when you ask; a daily check of Anthropic's public models page shows a banner for a new model and switches nothing; and a bot can send up to three read-only helpers inside one run and get their summaries back.

**Architecture:**
- **`roost/llm/registry.py`** (the only file with model ids): `ModelChoice`, `BOT_MODELS`, `DEFAULT_BOT_MODEL`, `WORKER`, `HELPER_MODELS`, `EFFORTS`, `KNOWN_MODEL_IDS`, `resolve_bot_model`. `ModelRequest.effort`; `ClaudeSdkModel` obeys `request.model` and `request.effort`; `build_options` shuts the SDK's own subagents.
- **Schema (next free version, v18 expected, "models"):** `bots.effort`, `seen_models`, `model_notice_dismissals`.
- **Routes:** `PUT /api/bots/{bot_id}/model`, `GET /api/models`, `POST /api/models/notice/{model_id}/dismiss`.
- **Main bot:** `suggest_model` (an Ask card, kind `model_suggestion`) and `set_bot_model` (write_change, clean 1:1 runs only).
- **`roost/models_check/`:** the page fetcher, parser, `SeenModelStore` and the daily scheduler.
- **`roost/helpers/`:** the helper step loop and `send_helpers` (`HelperTools`), sharing one step loop extracted to `roost/talk/steps.py`.
- **Web:** the Model and Effort rows in Info, the model card in the chat, the new-model banner on Home, the "Sent 3 helpers" step line.

**Tech Stack:** no new dependency (`httpx` is already a dependency): Python 3.12 (uv), FastAPI, pydantic 2, aiosqlite, pytest; Vite, React 19, TypeScript, vitest + Testing Library, Playwright; the `web/src/ui/` kit and `tokens.css`.

**Spec:** `docs/plans/2026-10-20-roost-models-helpers-design.md` (binding; its §2 lists the verified SDK facts). Runs after R1's batch C (the Info tab sits in the bot's side panel).

> **Status (2026-10-20): ready to execute.** Written against `night-1` at `697a26c`. Code is not pre-written: each task gives files, test names, shapes and the commit; the implementer writes it test-first.

## Global Constraints

- **Path guard, first in every task:** `git -C /Users/blckit/Desktop/Code_Projects/roost rev-parse --show-toplevel` prints `/Users/blckit/Desktop/Code_Projects/roost` and `git -C … branch --show-current` prints `night-1`; otherwise stop.
- **Where you may edit:** only under `/Users/blckit/Desktop/Code_Projects/roost`, never `roost-ui/`. Never touch `lazyclaw` (its data, containers or `make` targets).
- **The live Roost is never touched:** not `roost-gateway-1` (18800), the keeper (18801) or `~/Roost/data`. Anything importing `roost` runs with `ROOST_DATA_DIR` and `ROOST_DESKS_DIR` set to a fresh `mktemp -d`; Playwright as `ROOST_DESKS_DIR=$(mktemp -d) make e2e`.
- **Clean room (spec §10.3):** never open, fetch or search for the open-dot repos, `~/Roost-review/` or `~/.claude/projects/**`. No browser MCP tools.
- **No network and no LLM in tests:** `ScriptedModel` / `ScriptedTeamModel` / `ScriptedWorker` only; the models page fetcher is injected (a fake in tests, a fixture file in the E2E).
- **Model ids live only in `roost/llm/registry.py`** (Task 1 adds the guard test). Tests import the constants.
- **The SDK env never carries `ANTHROPIC_API_KEY`** (unchanged).
- **Disk guard:** before `make e2e` or `npm install`, `df -g /System/Volumes/Data | awk 'NR==2{print $4}'`; under 8 GB free: stop and report.
- **Data rules:** `model_override`, `effort`, `seen_models` and the dismissals are plaintext (settings and public facts, not user content). Every query on user data has `user_id` in its `WHERE`; another user's bot is 404, a body bot id is 422 "No such bot.".
- **Tests:** red first, then green; ≥80% line coverage on new code (`uv run pytest --cov=roost --cov-fail-under=80`); web tests in jsdom.
- **Code rules:** files ≤800 lines, functions <50 lines, frozen dataclasses and tuples, pydantic at every boundary (`extra="forbid"` on HTTP bodies, `extra="ignore"` on tool arguments), plain-sentence refusals, numbers in `roost/constants.py` / `web/src/lib/models.ts`.
- **Tokens and bundle:** no colour or font size outside `tokens.css`; `npm run size` stays within `web/bundle-budget.json`. Dark only. Vocabulary: Ask card, main bot, Info, Chat, Board; a helper is a "helper", never another product's word.
- **Git:** commit after each task's green tests; stage files **by name**; conventional messages; **no Co-Authored-By or any AI attribution line**. Other agents commit on this branch too: never amend, reset or rebase.
- **Commands:** `cd /Users/blckit/Desktop/Code_Projects/roost && ROOST_DATA_DIR=$(mktemp -d) ROOST_DESKS_DIR=$(mktemp -d) uv run pytest tests/<file>.py -q`; web: `cd web && npx vitest run tests/<file>`, `npm test`, `npm run build && npm run size`.

## Design meets code

1. **`request.model` was ignored** (design F3): `ClaudeSdkModel.stream` built options from `self.model_id`. Task 1 makes `request.model or self.model_id` win, so one `ClaudeSdkModel` serves every bot.
2. **`BRAIN` goes.** `turn.py` imports `resolve_bot_model` and `DEFAULT_BOT_MODEL`; `make_model` builds `ClaudeSdkModel(DEFAULT_BOT_MODEL)`. `tests/test_claude_sdk_options.py` stops spelling `"claude-sonnet-5"`.
3. **Schema number:** Task 2 reads `latest_version()`; if it is 17 the migration is v18 and `tests/fixtures/schema_v17.sql` is frozen first; if another step already took 18, take the next and freeze its predecessor. The design calls it "v18".
4. **The pickable set** is `BOT_MODELS` ids plus `seen_models` ids. `resolve_bot_model(override, extra_ids)` falls back to `DEFAULT_BOT_MODEL` for anything else (a retired id, a Haiku id).
5. **Where the card lives:** the Ask card is a chat message (`role="bot"`, `kind="model_suggestion"`), like `suggest_bot`'s card. It never reaches the model (`_MODEL_KINDS` unchanged).
6. **Helpers and the inflight note:** the parent's `ToolRunner.run` already records `send_helpers(…)` as in flight; helper runners get `record_inflight=None`.
7. **Helpers and `runs`:** `RunLog.start(user_id, bot_id, thread_id, run_id=f"{parent_run}-h{n}")` and `finish(…)` with the same outcomes a run uses. `count_today` needs no change.
8. **The desk lock:** `roost/helpers/desk_lock.py` wraps a `Desk` so `open_page` holds a per-bot `asyncio.Lock`; only helper runners get the wrapped desk (the parent is waiting on `send_helpers` meanwhile).
9. **Announcements:** a helper runner announces on the parent's `bot_id` with the suffix ` (helper {n})`; `toolLines.ts` gains `sending: "sent"`.

## Review Focus

1. **No SDK built-in or native subagent can run** (Task 1): `tools=[]`, `disallowed_tools` holds `Agent` and `Task`, the env disables built-in agents and caps spawn depth, `agents` is unset, `can_use_tool` denies `Agent`, `Task`, `Bash`, `Edit`. Test: `test_the_sdk_can_start_no_subagent_and_no_builtin`.
2. **A helper never has more than its parent** (Task 7): read-kind tools only, minus `HELPER_DENIED`, intersected with the parent's allowlist; same gate, `bot_id`, taint, link scope and guard; no cards. Tests: `test_a_helper_gets_only_read_tools_its_parent_has`, `test_a_helper_cannot_send_helpers`, `test_a_helper_inherits_the_parents_taint_and_link_guard`.
3. **Taint flows up** (Task 7): a helper that opened a page taints the parent; its report is escaped and marked. Test: `test_a_helpers_page_taints_the_parent_and_its_report_is_escaped`.
4. **Model changes stay yours** (Tasks 3–4): `set_bot_model` refused in a tainted run, in a room, in a handoff and when not the main bot; the route is 404 for another user's bot and 422 for an id outside the pickable set or a Haiku id. Tests: `test_set_bot_model_is_refused_after_web_content`, `test_another_users_bot_is_404_and_a_bad_model_is_422`.
5. **The models page check leaks nothing** (Task 5): one fixed host, no cookie or auth header, no user data in the request, size and time caps. Test: `test_the_check_sends_a_bare_request_to_one_host`.

## Shared Contract (every task uses these exact names)

**Registry (`roost/llm/registry.py`):**
```python
@dataclass(frozen=True)
class ModelChoice:
    key: str      # "fable" | "opus" | "sonnet" | "haiku"
    id: str       # "claude-fable-5-1" …
    label: str    # "Fable 5.1" …
    line: str     # "fable" | "opus" | "sonnet" | "haiku"

FABLE, OPUS, SONNET, HAIKU  # the four ModelChoice values (ids per design U1)
BOT_MODELS = (FABLE, SONNET, OPUS)
DEFAULT_BOT_MODEL = SONNET.id
WORKER = HAIKU.id
HELPER_MODELS = {"haiku": HAIKU.id, "sonnet": SONNET.id}; DEFAULT_HELPER_MODEL = "haiku"
EFFORTS = ("low", "medium", "high", "max")
DEFAULT_EFFORT = {FABLE.id: "high", OPUS.id: "medium", SONNET.id: "high", HAIKU.id: "medium"}  # display only
KNOWN_MODEL_IDS = frozenset({*four ids, "claude-sonnet-5", "claude-haiku-4-5-20251001"})
def resolve_bot_model(override: str | None, extra_ids: frozenset[str] = frozenset()) -> str
def model_label(model_id: str, seen_labels: Mapping[str, str] = {}) -> str
def make_model(config) -> Model; def make_worker_model(config) -> Model   # unchanged names
```

**Types:** `ModelRequest.effort: str | None = None`. `Bot.effort: str | None = None`. `BotOut` adds `model: str`, `model_label: str`, `effort: str | None`.

**Constants (`roost/constants.py`):** `MODEL_CHECK_URL = "https://platform.claude.com/docs/en/models/overview"`, `MODEL_CHECK_HOST = "platform.claude.com"`, `MODEL_CHECK_INTERVAL_S = 86_400`, `MODEL_CHECK_FIRST_DELAY_S = 600`, `MODEL_CHECK_TIMEOUT_S = 10`, `MODEL_CHECK_MAX_BYTES = 2 * 1024 * 1024`, `MAX_HELPERS_AT_ONCE = 3`, `MAX_HELPERS_PER_RUN = 6`, `HELPER_MAX_STEPS = 12`, `HELPER_MAX_SECONDS = 300`, `HELPER_TASK_MAX_CHARS = 4000`, `HELPER_REPORT_MAX_CHARS = 4000`, `MODEL_REASON_MAX_CHARS = 200`.

**Config:** `RoostConfig.model_check: str = "on"` (env `ROOST_MODEL_CHECK`: `on` | `off`), `model_check_file: Path | None` (env `ROOST_MODEL_CHECK_FILE`, honoured only when `model_mode == "scripted"`).

**Schema (v18 expected):**
```sql
ALTER TABLE bots ADD COLUMN effort TEXT;
CREATE TABLE IF NOT EXISTS seen_models (model_id TEXT PRIMARY KEY, label TEXT NOT NULL, first_seen_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS model_notice_dismissals (
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE, model_id TEXT NOT NULL,
  dismissed_at TEXT NOT NULL, PRIMARY KEY (user_id, model_id));
```

**Routes:** `PUT /api/bots/{bot_id}/model` body `ModelIn{model: str | None, effort: Literal[*EFFORTS] | None}` → `BotOut`. `GET /api/models` → `{choices: [{id, label, line, new}], efforts, default_model, default_effort: {id: level}, notice: {id, label} | null}`. `POST /api/models/notice/{model_id}/dismiss` → 204. All mutating routes carry `RequireOrigin`.

**Tools:**
- `suggest_model{bot: str, model: str, effort?: str, reason: str 1..MODEL_REASON_MAX_CHARS}`: kind `read`, in `LEAD_TOOLS`.
- `set_bot_model{bot: str, model: str, effort?: str}`: kind `write_change`, in `CREATOR_TOOLS` (main bot, outside rooms, user-started).
- `send_helpers{helpers: [{task: str 1..HELPER_TASK_MAX_CHARS, model?: "haiku"|"sonnet"}] 1..MAX_HELPERS_AT_ONCE}`: kind `read`, in `EVERY_BOT_TOOLS`; `HELPER_DENIED = frozenset({"send_helpers", "ask_bot", "list_bots", "suggest_bot", "suggest_model", "create_bot", "set_bot_model", "ask_for_help", "read_page"})`.

**Texts:** card title `"Switch {bot} to {label}?"`; `MODEL_SWITCHED_TEXT = "Switched {bot} to {label}"` (+ `" at {effort} effort"`); `MODEL_UNAVAILABLE_TEXT = "That model isn't available."`; `HELPERS_CAP_TEXT = "Refused: that would pass today's limit for this bot."`; `HELPERS_RUN_CAP_TEXT = f"Refused: at most {MAX_HELPERS_PER_RUN} helpers in one run."`; `NO_NESTED_HELPERS_TEXT = "Refused: a helper can't send helpers."`; banner `"New model: {label} — try it on a bot?"`; activity `"sending {n} helpers to {first task, ≤60 chars}"`, `"switching {bot} to {label}"`.

## Batches

- **Batch A (Tasks 1–3):** registry, SDK effort and subagent shutdown; schema and store; route, BotOut and runs on the chosen model.
- **Batch B (Tasks 4–5):** the main bot's two tools; the new-model check.
- **Batch C (Tasks 6–7):** the shared step loop and one helper; `send_helpers`. **Security review after Batch C** (Tasks 1, 6, 7: tool restriction, taint, depth).
- **Batch D (Tasks 8–9):** the web: Model and Effort in Info; the model card, the banner, the helper step line.
- **Batch E (Tasks 10–11):** E2E; CLAUDE.md, the docs test and the final checks.

### Task 1: One registry, effort on every request, no SDK subagents

**Files:** Modify `roost/llm/registry.py`, `roost/llm/types.py`, `roost/llm/claude_sdk.py`, `roost/talk/turn.py` (`resolve_bot_model` replaces `BRAIN`), `tests/test_claude_sdk_options.py`. Create `tests/test_model_registry.py`, `tests/test_model_ids_live_in_registry.py`.

- [ ] Tests (red): `test_bots_choose_fable_sonnet_or_opus_and_default_to_sonnet`, `test_haiku_is_the_worker_and_never_a_bot_model`, `test_resolve_falls_back_to_the_default_for_unknown_or_haiku`, `test_resolve_accepts_a_seen_model`, `test_no_model_id_outside_the_registry` (scans `roost/**/*.py` and `web/src/**/*.{ts,tsx}` for `claude-(fable|opus|sonnet|haiku|mythos)-\d`; only `registry.py` may match), `test_the_request_model_and_effort_reach_the_options` (patch `claude_sdk.query` to capture options: `model == request.model`, `effort == "max"`; `effort is None` when unset), `test_the_sdk_can_start_no_subagent_and_no_builtin` (`tools == []`, `"Agent" in disallowed_tools and "Task" in disallowed_tools`, env `CLAUDE_AGENT_SDK_DISABLE_BUILTIN_AGENTS == "1"`, `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH == "1"`, `agents is None`, `can_use_tool` denies `Agent`, `Task`, `Bash`, `Edit`).
- [ ] Implement; `build_options(system, tools, model, effort=None)`.
- [ ] Green: `… uv run pytest tests/test_model_registry.py tests/test_model_ids_live_in_registry.py tests/test_claude_sdk_options.py tests/test_memory_worker.py tests/test_turn*.py -q`.
- [ ] Commit: `git add roost/llm/registry.py roost/llm/types.py roost/llm/claude_sdk.py roost/talk/turn.py tests/test_claude_sdk_options.py tests/test_model_registry.py tests/test_model_ids_live_in_registry.py && git commit -m "feat: the Claude 5.5 family in one registry, effort on every request, no SDK subagents"`

### Task 2: Schema v18 and the bot's model and effort in the store

**Files:** Create `tests/fixtures/schema_v17.sql` (frozen first, from a fresh v17 database), `tests/test_migration_v18.py`, `roost/models_check/__init__.py`, `roost/models_check/store.py` (`SeenModelStore`: `add_new`, `ids`, `labels`, `newest_undismissed(user_id)`, `dismiss(user_id, model_id)`), `tests/test_seen_model_store.py`. Modify `roost/db/migrations.py`, `roost/bots/models.py` (`Bot.effort`), `roost/bots/store.py` (`set_model(user_id, bot_id, model, effort) -> Bot | None`), `tests/test_bot_store.py`.

- [ ] Tests: `test_v18_adds_effort_and_the_model_tables` (v17 fixture → migrate → columns and tables; twice is a no-op), `test_set_model_stores_and_clears_the_choice`, `test_set_model_on_another_users_bot_changes_nothing`, `test_seen_models_add_only_new_ids`, `test_a_dismissal_hides_the_notice_for_that_user_only`.
- [ ] Commit: `git add tests/fixtures/schema_v17.sql tests/test_migration_v18.py roost/db/migrations.py roost/bots/models.py roost/bots/store.py roost/models_check/__init__.py roost/models_check/store.py tests/test_seen_model_store.py tests/test_bot_store.py && git commit -m "feat: schema v18, a bot's model and effort, seen models and dismissals"`

### Task 3: The model route, BotOut, and runs on the chosen model

**Files:** Create `roost/gateway/routes/models.py` (`GET /api/models`, the dismiss route), `tests/test_models_api.py`, `tests/test_turn_model_choice.py`. Modify `roost/gateway/routes/bots.py` (`ModelIn`, `PUT /{bot_id}/model`), `roost/bots/service.py` (`bot_out` adds `model`, `model_label`, `effort`), `roost/gateway/app.py` (router, `app.state.seen_models`), `roost/talk/turn.py` (`ModelRequest(model=resolve_bot_model(bot.model_override, seen), effort=bot.effort)`), `web/src/api/types.ts` (`BotOut` fields).

- [ ] Tests: `test_put_model_saves_and_publishes_bot_updated`, `test_another_users_bot_is_404_and_a_bad_model_is_422` (Haiku id, unknown id, effort `"xhigh"`), `test_put_model_needs_the_origin`, `test_models_lists_bot_choices_then_seen_ones_marked_new`, `test_a_run_uses_the_bots_model_and_effort` (a recording `ScriptedModel`), `test_a_new_bot_runs_on_sonnet_5_5`.
- [ ] Commit: `git add roost/gateway/routes/models.py roost/gateway/routes/bots.py roost/bots/service.py roost/gateway/app.py roost/talk/turn.py web/src/api/types.ts tests/test_models_api.py tests/test_turn_model_choice.py && git commit -m "feat: pick a bot's model and effort, and its runs use them"`

### Task 4: The main bot proposes with an Ask card, or switches when you ask

**Files:** Create `roost/talk/model_tools.py` (`ModelTools.suggest_model`, `ModelTools.set_bot_model`, args models), `tests/test_model_tools.py`. Modify `roost/talk/tool_catalog.py` (two specs), `roost/talk/tools.py` (`LEAD_TOOLS`, `CREATOR_TOOLS`), `roost/talk/tool_runner.py` (dispatch through `TeamTools` → `ModelTools`), `roost/talk/team_tools.py` (hold `ModelTools`), `roost/talk/instructions.py` (roster line "… · Opus 5.5, high effort"; the main bot's model paragraph), `roost/constants.py`, `tests/test_tool_lines.py`.

- [ ] Tests: `test_suggest_model_posts_an_ask_card_and_changes_nothing`, `test_suggest_model_refuses_an_unknown_bot_or_the_same_choice`, `test_a_card_from_a_tainted_run_is_stored_tainted`, `test_set_bot_model_switches_and_posts_a_quiet_line`, `test_set_bot_model_is_refused_after_web_content` (gate verdict `never`, audit row), `test_only_the_main_bot_in_your_own_chat_gets_set_bot_model` (rooms, handoffs, other bots), `test_the_main_bots_roster_shows_each_model_and_effort`.
- [ ] Commit: `git add roost/talk/model_tools.py roost/talk/tool_catalog.py roost/talk/tools.py roost/talk/tool_runner.py roost/talk/team_tools.py roost/talk/instructions.py roost/constants.py tests/test_model_tools.py tests/test_tool_lines.py && git commit -m "feat: the main bot proposes a model with an Ask card, or switches it when you ask"`

### Task 5: The daily new-model check

**Files:** Create `roost/models_check/page.py` (`parse_model_ids(html) -> tuple[str, ...]`, `label_for(model_id)`), `roost/models_check/fetch.py` (`PageFetcher` protocol; `HttpPageFetcher` with httpx: GET `MODEL_CHECK_URL`, no cookies or auth, same-host redirects only, timeout and byte cap; `FilePageFetcher` for the E2E), `roost/models_check/scheduler.py` (`ModelCheck.run_once()`, `ModelCheck.loop()`), `tests/test_models_check.py`, `tests/fixtures/models_page.html` (a trimmed copy of the table with one extra `claude-opus-6` row). Modify `roost/config.py`, `roost/constants.py`, `roost/gateway/app.py` (start the loop in lifespan unless `off`; cancel on shutdown).

- [ ] Tests: `test_parse_finds_the_api_ids_and_skips_bedrock_ids`, `test_a_known_id_is_never_new`, `test_run_once_stores_a_new_id_once`, `test_a_failed_or_empty_page_changes_nothing` (logs the exception type name only), `test_the_check_sends_a_bare_request_to_one_host` (`httpx.MockTransport`: one GET, host `platform.claude.com`, no `cookie`/`authorization`, a cross-host redirect not followed, an oversized body refused), `test_off_starts_no_loop`, `test_the_fixture_file_is_used_only_in_scripted_mode`, `test_the_notice_is_the_newest_undismissed`.
- [ ] Commit: `git add roost/models_check/page.py roost/models_check/fetch.py roost/models_check/scheduler.py roost/config.py roost/constants.py roost/gateway/app.py tests/test_models_check.py tests/fixtures/models_page.html && git commit -m "feat: a daily check of Anthropic's public models page for a new model"`

### Task 6: One step loop for runs and helpers, and a single helper

**Files:** Create `roost/talk/steps.py` (`step_loop(*, model, request_for, tool_runner, max_steps, deadline_s, on_delta) -> tuple[str, bool]`, moved from `turn._run_steps`/`_stream_step`/`_run_calls`), `roost/helpers/__init__.py`, `roost/helpers/prompt.py` (`helper_instructions(bot_name)`), `roost/helpers/desk_lock.py` (`LockedDesk`), `roost/helpers/run.py` (`HelperResult(text, tainted, link_scope, sees_records)`, `run_helper(...)`), `tests/test_helper_run.py`. Modify `roost/talk/turn.py` (uses `step_loop`; stays under 600 lines), `roost/talk/tool_runner.py` (expose a `snapshot()` of taint, scope, guard, records flag).

- [ ] Tests: `test_the_parents_turns_still_pass` (run the existing `tests/test_turn*.py` and `tests/test_runner*.py`), `test_a_helper_runs_its_task_and_returns_its_summary` (`ScriptedTeamModel` keyed `"Scout/helper-1"`), `test_a_helpers_text_never_reaches_the_chat` (no `text_delta` or message published), `test_a_helper_stops_at_its_step_and_time_limits`, `test_helpers_take_turns_on_the_one_computer` (two helpers' `open_page` never overlap), `test_a_helper_uses_the_model_it_was_given`.
- [ ] Commit: `git add roost/talk/steps.py roost/talk/turn.py roost/talk/tool_runner.py roost/helpers/__init__.py roost/helpers/prompt.py roost/helpers/desk_lock.py roost/helpers/run.py tests/test_helper_run.py && git commit -m "refactor: one step loop for runs and helpers, and a single read-only helper"`

### Task 7: send_helpers: up to three at once, never more than the parent (security review)

**Files:** Create `roost/helpers/tools.py` (`SendHelpersArgs`, `HelperTools.send`, the report block), `tests/test_send_helpers.py`. Modify `roost/talk/tool_catalog.py` (`SEND_HELPERS_SPEC`, kind `read`), `roost/talk/tools.py` (`HELPER_DENIED`, `helper_tool_names(parent_allowed)`), `roost/talk/tool_runner.py` (dispatch `send_helpers`; absorb helper results like `_absorb_answer`), `roost/talk/turn.py` (`RunInputs.helpers`), `roost/talk/runner.py` (build `HelperTools` with `RunLog`, the run id and `ActivityBoard`), `roost/constants.py`, `web/src/lib/toolLines.ts` (`sending: "sent"`), `tests/test_tool_lines.py`.

- [ ] Tests: `test_three_helpers_run_together_and_report_in_order`, `test_more_than_three_is_refused_by_the_args`, `test_a_helper_gets_only_read_tools_its_parent_has`, `test_a_helper_cannot_send_helpers` (not offered; a forged call gets `NO_NESTED_HELPERS_TEXT` and an audit `never`), `test_a_helper_inherits_the_parents_taint_and_link_guard` (a link outside the scope is refused for the helper too), `test_a_helpers_page_taints_the_parent_and_its_report_is_escaped` (`</helper_report>` in the page cannot close the block), `test_helpers_count_toward_the_daily_cap` (one `runs` row each; refused when it would pass `DAILY_RUN_CAP`), `test_at_most_six_helpers_in_one_run`, `test_stop_cancels_every_helper`, `test_a_helper_meeting_a_block_reports_it_and_opens_no_card`, `test_the_parent_announces_sending_helpers`.
- [ ] Commit: `git add roost/helpers/tools.py roost/talk/tool_catalog.py roost/talk/tools.py roost/talk/tool_runner.py roost/talk/turn.py roost/talk/runner.py roost/constants.py web/src/lib/toolLines.ts tests/test_send_helpers.py tests/test_tool_lines.py && git commit -m "feat: send_helpers, up to three read-only helpers that share the parent's gate and taint"`

### Task 8: Model and Effort in the bot's Info

**Files:** Create `web/src/lib/models.ts` (fetch/cache `GET /api/models`, `effortLabel`, `defaultEffortLabel`), `web/src/components/profile/ModelPicker.tsx`, `web/tests/modelPicker.test.tsx`, `web/tests/models.test.ts`. Modify `web/src/components/profile/InfoTab.tsx` (two rows after Instructions), `web/src/api/client.ts` (`setBotModel`), the panel's stylesheet only through tokens.

- [ ] Tests: `shows the model and "Default (high)" for a new bot`, `saving a model calls PUT and shows a toast`, `the effort list is Default, Low, Medium, High, Max`, `a new model from the check is listed with a New mark`, `?try=<id> opens the Model select`.
- [ ] Commit: `git add web/src/lib/models.ts web/src/components/profile/ModelPicker.tsx web/src/components/profile/InfoTab.tsx web/src/api/client.ts web/tests/modelPicker.test.tsx web/tests/models.test.ts && git commit -m "feat: a model and effort picker in each bot's Info"`

### Task 9: The model Ask card, the new-model banner and the helper line

**Files:** Create `web/src/components/ModelSuggestionCard.tsx`, `web/src/components/NewModelBanner.tsx`, `web/tests/modelSuggestionCard.test.tsx`, `web/tests/newModelBanner.test.tsx`. Modify `web/src/components/MessageRow.tsx` (kind `model_suggestion`), `web/src/api/types.ts` (the kind and card body), Home's page (the banner on top), `web/tests/toolLines.test.ts`.

- [ ] Tests: `the card asks "Switch Daily Tasks to Opus 5.5?" with the reason`, `Switch calls PUT and the card shows Switched`, `Not now hides it in this browser`, `a tainted card shows the outside-content mark`, `the banner names the model and Try it lists your bots`, `Dismiss calls the dismiss route and hides it`, `"sending 3 helpers to research x" reads "Sent 3 helpers to research x"`.
- [ ] Commit: `git add web/src/components/ModelSuggestionCard.tsx web/src/components/NewModelBanner.tsx web/src/components/MessageRow.tsx web/src/api/types.ts web/tests/modelSuggestionCard.test.tsx web/tests/newModelBanner.test.tsx web/tests/toolLines.test.ts <Home page file> && git commit -m "feat: the model Ask card, the new-model banner and the helper step line"`

### Task 10: E2E for models and helpers

**Files:** Create `web/e2e/models.spec.ts`, `web/e2e/fixtures/models-page.html`. Modify `web/e2e/fixtures/team-script.json` (a main-bot `suggest_model` step; a Scout `send_helpers` step with `"Scout/helper-1"` and `"Scout/helper-2"` scripts), the E2E gateway env in `Makefile`/`playwright.config.ts` (`ROOST_MODEL_CHECK_FILE`, first delay 0 in scripted mode).

- [ ] Specs: pick Opus 5.5 and High in Info and see it after a reload; the main bot's card → Switch → Info shows the new model; the banner → Try it → a bot's Info with the select open → Dismiss survives a reload; Scout sends two helpers and the reply shows "Sent 2 helpers to …" with no helper text in the chat. Existing specs stay green.
- [ ] Commit: `git add web/e2e/models.spec.ts web/e2e/fixtures/models-page.html web/e2e/fixtures/team-script.json <the env file> && git commit -m "test: E2E for the model picker, the model card, the banner and helpers"`

### Task 11: CLAUDE.md, the docs test and the final checks

**Files:** Modify `CLAUDE.md` (first run `git diff CLAUDE.md`: keep any other agent's unstaged lines out of this commit, or wait), `tests/test_docs.py`.

- [ ] CLAUDE.md: the Global Constraints line becomes "Model ids live only in `roost/llm/registry.py`: bots choose Fable 5.1 `claude-fable-5-1`, Sonnet 5.5 `claude-sonnet-5-5` (the default) or Opus 5.5 `claude-opus-5-5`; Haiku 5.5 `claude-haiku-5-5` is the worker for background jobs and helpers."; the Documentation Map names the design and this plan; the Architecture gets one paragraph (registry, the picker, the Ask card, the daily check of the public page, helpers as Roost's own read-only step loops with the SDK's subagents shut).
- [ ] Tests: `test_the_documentation_map_names_the_models_design_and_plan`, `test_the_constraints_name_the_current_model_ids`, `test_the_architecture_section_says_where_helpers_live`.
- [ ] Final: full `uv run pytest --cov=roost --cov-fail-under=80`, `cd web && npm test && npm run build && npm run size`, the disk guard, then `ROOST_DESKS_DIR=$(mktemp -d) make e2e`.
- [ ] Commit: `git add CLAUDE.md tests/test_docs.py && git commit -m "docs: models and helpers in CLAUDE.md"`
