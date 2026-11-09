# Roost Memory and Endless Chat — Design

**Status:** approved by the user in conversation on 2026-10-20 (the three choices in §1). The plan
comes next. This is spec step 15 (`docs/specs/2026-10-12-roost-design.md`, lines ~1281–1290, §6.1,
§7.1, §8), built small.

**Why:**
- Today a bot has no memory. It replays only the newest 200 messages of a thread (`roost/talk/turn.py`
  `_history`), with no summary, so a long chat forgets its beginning and keeps getting more expensive.
- There is no remember or recall tool, and the worker model is unused.

**Sources:**
- A survey of LazyClaw's memory (LazyBrain, `auto_capture.py`, `context_builder.py`, `compressor.py`).
- **Kept from it:**
  - closed memory kinds;
  - cheap capture with dedupe and an hourly cap;
  - a small fixed prompt budget that mixes importance and relevance;
  - recent messages verbatim plus a summary of older ones.
- **Avoided:**
  - two parallel stores;
  - auto-capture noise (93% of its notes);
  - plaintext search copies.

## 1. Decisions (from the user)

- **M1. Scope:** one shared **About you** memory, plus each bot's own memory.
  - Facts about the user (name, family, likes) are known by every bot.
  - Everything else belongs to one bot, so "I prefer short answers" said to one bot doesn't change
    the others.
- **M2. Capture:** automatic, and **shown in the chat**. A small "Remembered: …" line with **Undo**
  appears when a bot saves something.
- **M3. One endless chat per bot** (like Grok).
  - The web shows one chat per bot, and it never ends.
  - The old separate conversations stay readable under **Earlier conversations**, read-only.

## 2. Storage (schema v15, one migration "memory")

**`memories`:**
- **Columns:**
  - `id`, `user_id`;
  - `bot_id`: NULL means About you, shared by every bot;
  - `kind`: `about_you` | `preference` | `fact` | `project` | `lesson`;
  - `text`: `enc:v2`, AAD `memories:text`;
  - `source`: `user` (the user said it, or added it in the web) | `bot` (captured or saved by a bot);
  - `importance`: 1–5;
  - `pinned`, `tainted`;
  - `fingerprint`;
  - `created_at`, `updated_at`, `last_recalled_at`, `archived_at`.
- **Kind and scope:** `about_you` is always stored with `bot_id` NULL; the other kinds always carry a
  bot id.
- **The fingerprint** is an HMAC-SHA256 of the normalised kind and text, keyed with a key derived from
  the user's DEK.
  - Being keyed, it never exposes guessable text.
  - Unique per (user, scope, fingerprint). Use a non-null scope column or expression so the shared
    scope is unique too, because SQLite allows repeated NULLs.
  - Saving the same thing again updates the row (its importance and `updated_at`) instead of adding one.

**`chat_summaries`:**
- **Columns:**
  - `id`, `user_id`, `thread_id` (cascade);
  - `upto_message_id`, `upto_created_at`;
  - `text`: `enc:v2`, AAD `chat_summaries:text`;
  - `created_at`.
- The newest row per thread is the one in use.

**Rules for both tables:**
- Every query has `user_id` in its WHERE. Another user's ids give 404.

## 3. Writing memories

### The bot's tools

**`remember(text, kind, importance?)`:**
- Gate kind: `write_create`.
- It refuses secrets: passwords, tokens and keys, card or IBAN-like numbers, one-time codes. The refusal
  is a plain sentence.
- In a tainted run it is refused with "Ask the user first", following spec §8. Web content never becomes
  a memory on its own.
- `about_you` goes to the shared scope; any other kind goes to the bot's own scope.

**`recall(query)`:**
- Gate kind: `read`.
- It searches the shared memories and the bot's own: decrypt, then a word match ranked by overlap and
  importance, the same approach as `roost/notes/search.py`.
- Results are quoted as data.

**`forget(memory_id)`:**
- Gate kind: `write_change`.
- A bot may forget only its own memories or shared ones that the bot itself saved (`source = bot`).
  It may never forget another bot's.

### Automatic capture (M2)

**When it runs:** after a run that answered the user's own chat messages, but only when all of these
hold:
- the run is not tainted;
- the run is not a handoff, a room or a routine;
- the user's text is at least `MEMORY_CAPTURE_MIN_CHARS` long, or matches a cue: "remember", "my … is",
  "I prefer", "always", "never", a date, a name.

**What it does:**
- It makes one **worker** model call (`WORKER` in `roost/llm/registry.py`).
- The call reads only the **user's own messages** from that run and asks for strict JSON: at most
  `MEMORY_CAPTURE_MAX_ITEMS` items, each `{kind, text, importance}`.
- Only lasting things count: people, preferences, decisions, deadlines, and facts about the user's life
  or work. Small talk and one-off requests never count.
- The result is validated with pydantic. The secret filter applies.
- Each user gets at most `MEMORY_CAPTURE_PER_HOUR` items.

**What the user sees:** each item that is saved, or updated through its fingerprint, posts a
`kind="memory_note"` message in the thread. The web draws it as a quiet line, "Remembered: {text}",
with **Undo**, which forgets that memory.

**Failure:** a capture failure is logged (ids only, never text) and never fails the run.

**Tests:** they use the scripted model. Tests never call a real LLM.

### Fading

When capture runs, it archives `source = bot` memories that meet all of these:
- importance ≤ 2;
- not pinned;
- not recalled for `MEMORY_FADE_DAYS` days.

Archived memories are hidden, not deleted, and the web can restore them.

## 4. Recall in every run

`build_instructions` gains a last section, **"What I remember"**. It is quoted as data, never as
instructions, following spec §6.1. It holds:
- up to `MEMORY_PINNED_MAX` pinned memories;
- then, alternating, the most important memories and the ones whose words overlap most with this run's
  newest user message.

Its rules:
- **Scope:** only the shared scope plus this bot's own scope.
- **Budget:** `MEMORY_PROMPT_BUDGET_CHARS` in total and `MEMORY_ITEM_MAX_CHARS` per item.
- **Each line** is `- [kind · date · source] text`, and a tainted memory is marked "from web content".
- **Recall stamp:** the memories it injects get `last_recalled_at` updated in one statement.

Building the prompt makes no model call. The prompt text also tells the bot to use `recall` before it
says it doesn't know something about the user.

## 5. Endless chat (M3)

**One chat:**
- Each bot has one main chat thread: its newest `kind="chat"` thread, or a new one if it has none.
- Chat opens the main thread. "New conversation" leaves the web menus.
- **Earlier conversations** lists the other chat threads read-only, and the composer is hidden there.
- The API keeps its routes for compatibility.
- Rooms and handoff threads are unchanged.

**History:**
- `_history` loads the newest summary for the thread, then the messages after `upto_created_at` (still
  capped at the page limit).
- The model sees the summary first as one quoted "Earlier in this chat (summary)" turn, then the recent
  turns.
- Taint scanning uses the loaded messages, as today.

**Summarising:**
- **Trigger:** after a run, when more than `CHAT_SUMMARY_TRIGGER` messages follow the last summary,
  one worker call summarises everything except the newest `CHAT_KEEP_RECENT` messages, together with
  the previous summary. The result is a new `chat_summaries` row.
- **Only trusted text goes in:** the user's messages and the bot's replies from runs that were not
  tainted. A tainted row is reduced to "(a step that read web content was here)", with no content.
  So the summary itself is never tainted and can't carry web text forward forever.
- **Failure** is logged and skipped. The next run tries again.

**`search_chat(query)`:**
- Gate kind: `read`.
- Searches the current thread's older messages (decrypt and scan) and returns short snippets with their
  dates. Tainted snippets are marked.

## 6. The web

- **Chat:**
  - opens the bot's one chat;
  - the + menu loses New conversation, and Past conversations becomes **Earlier conversations**
    (read-only);
  - a `memory_note` message renders as a compact line with **Undo**.
- **Profile, Info tab:** a **What I remember** section (it moves into the side panel in polish R1) that
  shows:
  - **About you** (shared) and **This bot's**;
  - each memory's text, kind, date and source;
  - **Edit**, **Pin** and **Forget** on each one, and **Add**.
  - Archived memories sit behind "Show faded".
- **Routes**, all with `CurrentUser`, and `RequireOrigin` on writes:
  - `GET /api/memories?bot_id=` (shared plus that bot's);
  - `POST /api/memories`;
  - `PATCH /api/memories/{id}` (text, kind, importance, pinned, restore);
  - `DELETE /api/memories/{id}`.
  - Another user's id gives 404.
- **Look:** built from the `web/src/ui/` kit and `tokens.css`.

## 7. Constants (`roost/constants.py`)

| Constant | Value |
|---|---|
| `MEMORY_PROMPT_BUDGET_CHARS` | 1500 |
| `MEMORY_ITEM_MAX_CHARS` | 240 |
| `MEMORY_PINNED_MAX` | 5 |
| `MEMORY_TEXT_MAX_CHARS` | 500 |
| `MEMORY_CAPTURE_MIN_CHARS` | 40 |
| `MEMORY_CAPTURE_MAX_ITEMS` | 3 |
| `MEMORY_CAPTURE_PER_HOUR` | 6 |
| `MEMORY_FADE_DAYS` | 60 |
| `CHAT_SUMMARY_TRIGGER` | 80 |
| `CHAT_KEEP_RECENT` | 40 |
| `CHAT_SUMMARY_MAX_CHARS` | 4000 |

## 8. Testing

**pytest:**
- the store: encryption, the fingerprint upsert, scope, 404 for another user;
- the secret filter;
- the tools' gate kinds and the tainted refusal;
- capture with the scripted worker: the cap, dedupe, skip rules, and the posted `memory_note`;
- fading;
- the prompt section: budget, order, and quoting as data;
- the summary trigger, and that tainted rows never reach a summary;
- `search_chat`;
- the routes.
- One E2E-style test follows spec step 15: "Ana's birthday is in May and she loves orchids" is captured
  in one chat and recalled in a later run. A preference told to one bot doesn't reach another.

**vitest:** the memory list (edit, pin, forget, add, show faded), the Remembered line with Undo, and
Earlier conversations being read-only.

**Playwright:** the scripted gateway captures a memory, the line shows, Undo removes it, and the panel
lists it.

## Out of scope (later)

- Vectors and semantic search (with the PKM step).
- Lessons learned from corrections.
- Contradiction hints.
- Moving the memory list into the R1 side panel. That move happens in R1 itself.
