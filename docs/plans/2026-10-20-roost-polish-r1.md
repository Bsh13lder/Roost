# Roost Polish R1, "the Grok-feel shell", Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. The SDD workspace is `.superpowers/sdd/2026-10-20-roost-polish-r1/` (`contract.md`, one `task-N-brief.md` per task, `progress.md`).

**Goal:** Roost's web feels as easy as a modern chat app: one fixed sidebar (search and + on top, a row of bot robots, chats under group headings, your initials and Board at the bottom); the Profile as a panel beside the chat, opened from the name pill and kept in the URL; quiet centred activity lines, a NEW divider and one round composer pill; a sleeping robot when a bot's computer is asleep; and stylesheets split so none passes 800 lines.

**Architecture:**
- **Backend (small):** schema v16 adds `bots.group_label` (`enc:v2`, AAD `bots:group_label`). `Bot.group` and `BotPatch.group` carry it; `PATCH /api/bots/{id}` takes `group` (set, `""`/`null` clears, absent keeps); `BotOut` and the `bot_updated` frame carry `group`.
- **Sidebar:** `pages/Home.tsx` keeps the data hooks and renders `components/sidebar/` (`SidebarTop`, `AvatarRow`, `SidebarFoot`) around `ChatList`, which now draws sections. The pure sorting lives in `lib/sidebar.ts`.
- **Panel:** `components/panel/` (`BotPanel`, `PanelHero`, `GroupLabel`, `panelTabs.ts`) inside `pages/Chat.tsx`; `hooks/usePanelParam.ts` reads and writes `?panel=`; `hooks/useMediaQuery.ts` picks the desktop aside or the kit's `Sheet` (`size="full"`) on a phone. `pages/Profile.tsx` is deleted; `App.tsx` redirects the old addresses.
- **Chat:** `lib/chatMarks.ts` (day lines and the NEW line, pure), `hooks/useSeenAtOpen.ts`, `Composer`'s `leading` slot for the + inside the pill.
- **Computer:** `components/profile/ComputerAsleep.tsx`.
- **Styles:** `chat.css` and `profile.css` split by feature; `sidebar.css` replaces `home.css`; `panel.css` is new; `web/tests/stylesheets.test.ts` guards size and imports.

**Tech Stack:** as P3 and memory, no new dependency: Python 3.12 (uv), FastAPI, pydantic 2, aiosqlite, pytest; Vite, React 19, TypeScript, React Router, vitest + Testing Library, Playwright; the `web/src/ui/` kit and `tokens.css`.

**Design:** `docs/plans/2026-10-20-roost-polish-r1-design.md` (binding; decisions R1.1–R1.14).

> **Status (2026-10-20): ready to execute.** Written against `night-1` at `cef12ed` (latest migration v15, memory; memory's web Tasks 11–12 are in). Each task gives exact files, test names, the shapes that matter and the commit; the implementer writes the code test-first.

---

## Global Constraints

- **Path guard, first in every task:**
  - `git -C /Users/blckit/Desktop/Code_Projects/roost rev-parse --show-toplevel` must print `/Users/blckit/Desktop/Code_Projects/roost`.
  - `git -C /Users/blckit/Desktop/Code_Projects/roost branch --show-current` must print `night-1`.
  - If either check fails, stop.
- **Where you may edit:** only under `/Users/blckit/Desktop/Code_Projects/roost`, never its `roost-ui/` folder (the user's). `/Users/blckit/Desktop/Code_Projects/lazyclaw` is never touched.
- **The live Roost is never touched:** never stop, restart, rebuild or call the gateway on `127.0.0.1:18800`, the keeper (`18801`) or `~/Roost/data`. Any script that imports `roost` runs with `ROOST_DATA_DIR` and `ROOST_DESKS_DIR` set to a fresh `mktemp -d`. Playwright runs as `ROOST_DESKS_DIR=$(mktemp -d) make e2e` (its own throwaway gateway).
- **Clean room (spec §10.3):** never open, fetch or search for the open-dot repos, `~/Roost-review/` or `~/.claude/projects/**`. No browser MCP tools. Copy no other product's art, icons or wording: the user's screenshots set the *ease*, Roost's words and tokens set the look.
- **Licences:** no new dependency; `web/tests/licenseGate.test.ts` stays green.
- **Disk guard:** before `make e2e`, `df -g /System/Volumes/Data | awk 'NR==2{print $4}'`; fewer than 8 GB free: stop and report.
- **Data rules (CLAUDE.md):** the group label is user content: `enc:v2` with the per-user DEK and `user_aad(user_id, "bots:group_label")`. Every query names `user_id` in its `WHERE`; another user's bot is **404**.
- **No LLM in tests** (`tests/conftest.py` forces `ROOST_MODEL=scripted`).
- **Tests:** tests first (red, then green); ≥80% line coverage on new code (`uv run pytest --cov=roost --cov-fail-under=80`); web tests in jsdom.
- **Code rules:** files ≤800 lines (typically 200–400), functions <50 lines; frozen dataclasses, new objects in React state; pydantic at every boundary; plain-sentence refusals (422); no magic values (server numbers in `roost/constants.py`, web numbers in `web/src/components/sidebar/constants.ts`, `web/src/components/panel/panelTabs.ts` or `web/src/lib/botProfile.ts`).
- **Tokens, kit and bundle:** no colour or font size outside `web/src/styles/tokens.css` (`web/tests/tokens.test.ts`); controls come from `web/src/ui/` (Button, IconButton, Input, Menu, Popover, Sheet, Tabs, Chip, Tooltip); the entry stays within `web/bundle-budget.json` (`npm run size`).
- **Dark only (V4)**, and the vocabulary (CLAUDE.md table, `tests/test_vocabulary.py`): Chat, Profile, Board, Computer, main bot, My turn, Earlier conversations; a bot is a bot.
- **Memory is built; do not redo it:** the Info tab's `MemoryPanel`, the one endless chat (`threadsApi.openChat`), Earlier conversations read-only (`ThreadsSheet`, the `chat-readonly` dock) and `MemoryNoteRow` keep their behaviour and tests. R1 only moves or restyles them.
- **Git:** other agents commit at the same time. Commit after each task's green tests; stage files **by name** (never `git add -A`, `-a` or `.`); never amend, rebase or reset; conventional messages with **no Co-Authored-By or any AI attribution line**.
- **Commands:** prefix with `cd /Users/blckit/Desktop/Code_Projects/roost &&`. One file: `ROOST_DATA_DIR=$(mktemp -d) ROOST_DESKS_DIR=$(mktemp -d) uv run pytest tests/<file>.py -q`; the suite: the same with no path. Web: `cd web && npx vitest run tests/<file>`, `npm test`, `npm run build && npm run size`.

## Design meets code

1. **Schema number.** The latest migration is v15 (memory), so the label is **v16** (`Migration(16, "bot groups", …)`). Live control's `site_logins`, last planned as v16, takes **v17**; the migration's comment says so.
2. **`group` is an SQL keyword,** so the column is `group_label`; the Python field and the wire name are `group`.
3. **Keep, set, clear in one optional field.** `BotPatch.group: str | None = None`: `None` keeps the label, `""` clears it, any other string (stripped) sets it. The route maps the body: `group` absent → `None`; `null` or a blank string → `""`; otherwise the stripped text.
4. **Grouping is exact.** A section is the trimmed label as typed; sections sort case-insensitively with `localeCompare`. Two spellings are two sections; the label popover offers the labels already used, so a typo is rare.
5. **Which chat rows are grouped.** A bot row takes its bot's label; rooms are never grouped and sit in the first section with the ungrouped bots.
6. **The avatar row** is `[main bot, ...the other bots ordered by their chat row's last_at, newest first]`, capped at `SIDEBAR_AVATARS_MAX = 6`. A bot with no chat row yet comes after those with one, in creation order.
7. **The panel's URL.** `?panel=` takes `info | documents | computer | links`; an unknown value opens Info. Opening pushes a history entry, switching tabs and closing replace it. Other params (`thread`) are kept.
8. **Phone or desktop.** `PHONE_QUERY = "(max-width: 768px)"`, the breakpoint every stylesheet already uses. `useMediaQuery` reads `window.matchMedia` and follows its `change` event; jsdom tests stub `matchMedia`.
9. **The pill stays a link** named "Open {name}'s profile" (closed) or "Close {name}'s profile" (open), so the five E2E specs that click it keep working.
10. **No two `h1` with the bot's name.** The chat header keeps its `h1`; the hero's name is an `h2` (`NameJobCard` gets `nameLevel?: "h1" | "h2"`, default `"h1"`). An E2E that checks the name with the panel open scopes to the panel (`getByRole("complementary", { name: "Scout's profile" })`).
11. **The NEW divider's seen time.** `lib/unread.ts` keeps, per chat id, the newest `last_at` seen. `useSeenAtOpen(chatId)` reads it once while rendering a new chat id (before `useUnread`'s effect marks the chat read) and keeps it until the id changes. `Chat` passes it as `newAfter` only when the shown thread is the main chat.
12. **The + inside the pill.** `Composer` gains `leading?: ReactNode`, drawn inside `.composer` before the text box; Chat passes its existing + `Menu`. `.chat-composer` stops being a row of two.
13. **Asleep.** `ComputerAsleep` draws the bot's `Avatar` with `moment="off"` (the moon, glow, pixel or signal per the bot's screen style) and three `aria-hidden` "z" marks animated by CSS; `usePrefersReducedMotion` adds `computer-asleep--still`, which stops them.
14. **The stylesheet guard.** `web/tests/stylesheets.test.ts` reads `web/src/styles/*.css` with `node:fs` (as `tokenScan.ts` does): each ≤ 800 lines, and `web/src/styles.css` imports each exactly once.

## Review Focus

1. **Another user's bot at the PATCH:** `group` on another user's bot id is a 404 and changes nothing (Task 2, `test_another_users_bot_cannot_be_labelled`).
2. **The label is sealed:** the raw `bots.group_label` value is `enc:v2`, never the plain text (Task 1, `test_a_group_label_is_stored_sealed_and_read_back`).
3. **The label never reaches a model:** `build_instructions`, the roster and `list_bots` do not read `group` (Task 2, `test_the_group_never_reaches_a_prompt_or_the_roster`).
4. **Nothing of memory regresses:** `MemoryPanel.test.tsx`, `MemoryNoteRow.test.tsx`, `ChatThreads.test.tsx` and the memory E2E stay green (Tasks 6, 7, 11).
5. **No security review is needed:** no task touches auth, sessions or Origin checks; the PATCH field rides the existing `RequireOrigin` route.

---

## Shared Contract (every task uses these exact names)

### Schema v16 (Task 1)

```python
# Polish R1. Live control's site_logins, last planned as v16, takes v17.
Migration(16, "bot groups", (
    AddColumn("bots", "group_label", "TEXT"),   # enc:v2, AAD bots:group_label; NULL: no label
)),
```

`tests/fixtures/schema_v15.sql` is frozen **before** `roost/db/migrations.py` changes (Task 1, Step 2a).

### Constants

| Where | Name | Value |
|---|---|---|
| `roost/constants.py` (beside `MAX_BOT_JOB_LENGTH`) | `MAX_BOT_GROUP_LENGTH` | `30` |
| `web/src/lib/botProfile.ts` | `BOT_LIMITS.group` | `30` |
| `web/src/components/sidebar/constants.ts` | `SIDEBAR_AVATARS_MAX` | `6` |
| `web/src/components/panel/panelTabs.ts` | `PHONE_QUERY` | `"(max-width: 768px)"` |
| `web/src/styles/tokens.css` (Layout) | `--sidebar-width` / `--panel-width` | `300px` / `380px` |

### Python names

- `roost/bots/models.py`: `Bot.group: str | None = None`; `BotPatch.group: str | None = None` (Design meets code 3).
- `roost/bots/store.py`: `_GROUP_AAD = "bots:group_label"`; `group_label` in `_SELECT_COLUMNS`; `_row_to_bot` decrypts it when not NULL; `update` writes it.
- `roost/gateway/routes/bots.py`: `BotUpdate.group: str | None = Field(default=None, max_length=MAX_BOT_GROUP_LENGTH)`, one-line check like name and job; `_group_patch(body) -> str | None`.
- `roost/bots/service.py` `bot_out`: `"group": bot.group`.

### Wire

- `BotOut` gains `group: string | null` (TS) / `"group": str | None` (JSON).
- `PATCH /api/bots/{id}` body may hold `"group"`: a string sets it, `""` or `null` clears it, absent keeps it. Too long or two lines: 422.

### Web names

```ts
// web/src/lib/sidebar.ts
export interface ChatSection { label: string | null; rows: readonly ChatRowOut[] }
export function filterChats(rows: readonly ChatRowOut[], query: string): ChatRowOut[];          // moved from ChatList.tsx
export function mainFirst(rows: readonly ChatRowOut[], bots: Readonly<Record<string, BotOut>>): ChatRowOut[]; // moved
export function withLiveNames(rows: readonly ChatRowOut[], bots: Readonly<Record<string, BotOut>>): ChatRowOut[]; // moved
export function groupOf(row: ChatRowOut, bots: Readonly<Record<string, BotOut>>): string | null;
export function chatSections(rows: readonly ChatRowOut[], bots: Readonly<Record<string, BotOut>>, query: string): ChatSection[];
export function avatarRow(bots: readonly BotOut[], rows: readonly ChatRowOut[], max?: number): BotOut[];
export function usedLabels(bots: readonly BotOut[], exceptBotId?: string): string[];

// web/src/components/panel/panelTabs.ts
export type PanelTab = "info" | "documents" | "computer" | "links";
export const PANEL_TABS: ReadonlyArray<{ id: PanelTab; label: string }>; // Info · Documents · Computer · Links
export const PHONE_QUERY = "(max-width: 768px)";
export function panelTab(value: string | null): PanelTab | null;        // null → null (closed); unknown → "info"

// web/src/hooks/usePanelParam.ts
export function usePanelParam(): {
  tab: PanelTab | null;
  open: (tab?: PanelTab) => void;    // push, default "info"
  select: (tab: PanelTab) => void;   // replace
  close: () => void;                 // replace, panel param removed
  hrefFor: (tab: PanelTab | null) => string; // the chat's URL with ?panel= set or removed, other params kept
};

// web/src/hooks/useMediaQuery.ts
export function useMediaQuery(query: string): boolean;

// web/src/hooks/useSeenAtOpen.ts
export function useSeenAtOpen(chatId: string): string | null;

// web/src/lib/chatMarks.ts
export type ChatItem =
  | { kind: "day"; id: string; label: string }
  | { kind: "new"; id: string }
  | { kind: "message"; message: MessageOut; index: number; dayStart: boolean };
export function firstUnreadId(messages: readonly MessageOut[], newAfter: string | null): string | null;
export function chatMarks(messages: readonly MessageOut[], newAfter: string | null, now?: Date): ChatItem[];
```

Components: `SidebarTop`, `AvatarRow`, `SidebarFoot` (`web/src/components/sidebar/`); `BotPanel`, `PanelHero`, `GroupLabel` (`web/src/components/panel/`); `ComputerAsleep` (`web/src/components/profile/`). `Sheet` gains `size?: "default" | "full"`. `Composer` gains `leading?: ReactNode`. `MessageList` gains `newAfter?: string | null`. `NameJobCard` gains `nameLevel?: "h1" | "h2"`.

### Texts (exact)

| Where | Text |
|---|---|
| Sidebar search | `aria-label="Search chats"`, placeholder `Search` |
| Avatar row | list `aria-label="Your bots"`; each link named by the bot's name (`, your main bot` for the main bot) |
| Chat sections | `<nav aria-label="Chats">`; a group's heading is its label; the first section has no heading |
| Sidebar foot | the `Account` menu (initials), a `Board` link |
| Name pill | `Open {name}'s profile` / `Close {name}'s profile` |
| Panel | `aria-label="{name}'s profile"`; Close button `Close profile` |
| Group label | `Add a label`; popover `aria-label="Label"`; input label `Label`; `Save`; `Remove label`; client refusals `A label fits on one line.` / `A label is at most 30 characters.` |
| NEW divider | visible `New`, `role="separator"`, `aria-label="New messages"` |
| Asleep | heading `Computer is asleep`; line `{name}'s computer wakes when it needs it.`; button `Open it` |

---

## File map

| Files | Task |
|---|---|
| `tests/fixtures/schema_v15.sql`, `tests/test_migrations_v15.py`, `roost/db/migrations.py`, `roost/constants.py`, `roost/bots/{models,store}.py`, `tests/test_bot_store.py` | 1 |
| `roost/gateway/routes/bots.py`, `roost/bots/service.py`, `tests/test_bots_api.py` | 2 |
| `web/src/styles/{chat,chat-dock,chat-cards,chat-sheet,profile,instructions,avatar-studio}.css`, `web/src/styles.css`, `web/tests/stylesheets.test.ts` | 3 |
| `web/src/lib/sidebar.ts`, `web/src/components/sidebar/constants.ts`, `web/src/api/{types,bots}.ts`, `web/src/lib/botProfile.ts`, `web/src/components/ChatList.tsx`, `web/tests/{sidebar.test.ts,ChatList.test.tsx,fixtures.ts}` | 4 |
| `web/src/components/sidebar/{SidebarTop,AvatarRow,SidebarFoot}.tsx`, `web/src/components/ChatList.tsx`, `web/src/pages/Home.tsx`, `web/src/styles/{sidebar,layout,tokens}.css` (`home.css` deleted), `web/src/styles.css`, `web/tests/{Sidebar,Home,ChatList,Layout}.test.tsx` | 5 |
| `web/src/components/panel/{BotPanel,PanelHero}.tsx`, `web/src/components/panel/panelTabs.ts`, `web/src/hooks/{usePanelParam,useMediaQuery}.ts`, `web/src/pages/Chat.tsx`, `web/src/ui/Sheet.tsx`, `web/src/components/profile/NameJobCard.tsx`, `web/src/styles/{panel,ui-overlays}.css`, `web/src/styles.css`, `web/tests/{BotPanel,usePanelParam,Chat,sheetFocus}.test.tsx` | 6 |
| `web/src/App.tsx`, `web/src/pages/Profile.tsx` (deleted), `web/src/components/StuckCard.tsx`, `web/src/pages/Instructions.tsx`, `web/src/styles/profile.css`, `web/tests/{routes,StuckCard,Instructions,BotPanel}.test.tsx`, `web/tests/Profile.test.tsx` (deleted) | 7 |
| `web/src/components/panel/{GroupLabel,PanelHero}.tsx`, `web/src/lib/botFields.ts`, `web/src/styles/panel.css`, `web/tests/{GroupLabel.test.tsx,botFields.test.ts,Home.test.tsx}` | 8 |
| `web/src/lib/chatMarks.ts`, `web/src/hooks/{useSeenAtOpen,useAutoGrow}.ts`, `web/src/components/{MessageList,MessageRow,Composer}.tsx`, `web/src/pages/Chat.tsx`, `web/src/styles/{chat,chat-dock,memory}.css`, `web/tests/{chatMarks.test.ts,MessageList,Composer,Chat}.test.tsx` | 9 |
| `web/src/components/profile/{ComputerAsleep,ComputerTab}.tsx`, `web/src/styles/computer.css`, `web/tests/{ComputerAsleep,ComputerTab}.test.tsx` | 10 |
| `web/e2e/shell.spec.ts`, `web/e2e/{helpers,computer,memory,profile,look,every-bot,main-bot}.spec.ts` as needed | 11 |
| `CLAUDE.md`, `tests/test_docs.py` | 12 |

---

## Batches

- **Batch A (Tasks 1–3):** the backend label (1, 2) and the stylesheet split (3). Independent of each other.
- **Batch B (Tasks 4–5):** the sidebar.
- **Batch C (Tasks 6–8):** the panel, the old addresses, the group label.
- **Batch D (Tasks 9–10):** chat polish and the sleeping computer.
- **Batch E (Tasks 11–12):** E2E, the docs, the final checks.
- **No security review:** no task touches auth (Review Focus 5). Each batch ends with its green commands.

---

### Task 1: Schema v16 `bots.group_label`, v15 frozen first, the store reads and writes it sealed

Design R1.4; Design meets code 1–3.

**Files:**
- Create: `tests/fixtures/schema_v15.sql` (Step 2a, before any other change), `tests/test_migrations_v15.py`
- Modify: `roost/db/migrations.py`, `roost/constants.py` (`MAX_BOT_GROUP_LENGTH = 30` after `MAX_BOT_JOB_LENGTH`), `roost/bots/models.py`, `roost/bots/store.py`, `tests/test_bot_store.py`

- [ ] **Step 1: Path guard and starting point**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && test ! -e tests/fixtures/schema_v15.sql && grep -n "Migration(1[56]," roost/db/migrations.py && grep -rn "latest_version() == 1[56]" tests/ ; echo end`
Expected: only `    Migration(15, "memory", (`, then `end`. Otherwise stop: this task already ran, or another plan took v16 (then take the next free number and say so in the commit body).

- [ ] **Step 2: Freeze v15, then the failing tests**

**2a. Freeze schema v15**, in a throwaway `mktemp -d`, never in `~/Roost/data`:

```bash
cd /Users/blckit/Desktop/Code_Projects/roost && ROOST_DATA_DIR=$(mktemp -d) ROOST_DESKS_DIR=$(mktemp -d) uv run python - <<'EOF'
import asyncio, os, sqlite3
from pathlib import Path
import aiosqlite
from roost.db.migrations import apply_migrations, latest_version

assert latest_version() == 15, f"expected schema v15 before polish R1, got {latest_version()}"

async def build(path: Path) -> None:
    async with aiosqlite.connect(path) as db:
        await db.executescript(Path("roost/db/schema.sql").read_text())
        await db.commit()
        await apply_migrations(db)

path = Path(os.environ["ROOST_DATA_DIR"]) / "v15.db"
asyncio.run(build(path))
con = sqlite3.connect(path)
rows = con.execute(
    "SELECT sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%' ORDER BY rowid"
).fetchall()
con.close()
header = ("-- Roost schema version 15, frozen by polish R1 Task 1 (schema.sql + migrations 1-15).\n"
          "-- The live ~/Roost/data/roost.db runs this schema at the start of polish R1. Never edit.\n\n")
Path("tests/fixtures/schema_v15.sql").write_text(header + ";\n\n".join(r[0] for r in rows) + ";\n")
print("tables/indexes:", len(rows))
EOF
grep -c "CREATE" tests/fixtures/schema_v15.sql        # 52
grep -c "group_label" tests/fixtures/schema_v15.sql   # 0
diff <(sed 1,3d tests/fixtures/schema_v14.sql) <(sed 1,3d tests/fixtures/schema_v15.sql)
```

Expected: `tables/indexes: 52`, the greps `52` and `0`, and the `diff` shows only `memories`, `chat_summaries` and their three indexes (it exits 1; that is expected).

**2b.** `tests/test_migrations_v15.py`, modelled on `tests/test_migrations_v14.py`: `_ROWS = (*_V14_ROWS, <one memories row with scope '*'>, <one chat_summaries row>)`, `_EXPECTED = {**_V14_EXPECTED, "memories": 1, "chat_summaries": 1}`, fixture `seeded_v15` (`PRAGMA user_version = 15`). Tests:
- `test_v16_adds_bots_group_label_and_keeps_every_row`: `init_db` → `latest_version() == 16`, `_counts == _EXPECTED`, `group_label` is in `PRAGMA table_info(bots)`.
- `test_an_old_bot_has_no_group`: every seeded bot's `group_label` is NULL.
- `test_migration_16_is_idempotent`: `apply_migrations` twice leaves version 16 and the same `sqlite_master`.

**2c.** `tests/test_bot_store.py` (existing fixtures `store`, `user`, `other_user`):
- `test_a_group_label_is_stored_sealed_and_read_back`: `update(..., BotPatch(group="Home"))` → `get` returns `group == "Home"`; the raw column (read with `sqlite3`) starts with `enc:` and does not contain `Home`.
- `test_update_leaves_the_group_alone_when_not_given`: a label set, then `BotPatch(name="Other")` → the label stays.
- `test_an_empty_group_clears_it`: `BotPatch(group="")` and `BotPatch(group="   ")` → `group is None` and the column is NULL.
- `test_another_user_cannot_set_a_group`: `update(other_user.id, bot.id, BotPatch(group="X"))` is `None`; the owner's bot is unchanged.
- `test_a_new_bot_has_no_group`.

- [ ] **Step 3: Red.** `… uv run pytest tests/test_migrations_v15.py tests/test_bot_store.py -q` fails (version 15, no `group`).

- [ ] **Step 4: Implement.**
  - `roost/db/migrations.py`: the Shared Contract's `Migration(16, …)` with its comment.
  - `roost/bots/models.py`: `Bot.group: str | None = None` (last field, after `notify`); `BotPatch.group: str | None = None`.
  - `roost/bots/store.py`: `_GROUP_AAD = "bots:group_label"`; `group_label` appended to `_SELECT_COLUMNS`; in `_row_to_bot`, `group=None if row["group_label"] is None else decrypt_field(row["group_label"], dek, user_aad(user_id, _GROUP_AAD))`; in `update`, a helper `_next_group(current: str | None, wanted: str | None) -> str | None` (`None` → current; else `wanted.strip() or None`), the `UPDATE` sets `group_label = ?` (sealed, or `None`), and the returned `Bot` carries it.
  - `roost/constants.py`: `MAX_BOT_GROUP_LENGTH = 30` with a one-line comment.

- [ ] **Step 5: Green.** `… uv run pytest tests/test_migrations_v15.py tests/test_migrations_v14.py tests/test_migrations.py tests/test_bot_store.py -q` passes.

- [ ] **Step 6: Commit**

```bash
cd /Users/blckit/Desktop/Code_Projects/roost && git add tests/fixtures/schema_v15.sql tests/test_migrations_v15.py roost/db/migrations.py roost/constants.py roost/bots/models.py roost/bots/store.py tests/test_bot_store.py && git commit -m "feat: schema v16 gives each bot an optional group label, sealed, v15 frozen first"
```

---

### Task 2: `PATCH /api/bots/{id}` takes `group`; `BotOut` carries it

Design R1.4; Design meets code 3. Depends on Task 1.

**Files:**
- Modify: `roost/gateway/routes/bots.py`, `roost/bots/service.py`, `tests/test_bots_api.py`

**Shapes:**

```python
class BotUpdate(BaseModel):
    ...
    group: str | None = Field(default=None, max_length=MAX_BOT_GROUP_LENGTH)

    @field_validator("name", "job", "group")   # the existing one-line check, now on group too

def _group_patch(body: BotUpdate) -> str | None:
    """Absent keeps the label (None); null or blank clears it (""); text sets it, stripped."""
    if "group" not in body.model_fields_set:
        return None
    return (body.group or "").strip()
```

`update_bot` passes `group=_group_patch(body)` into `BotPatch`. `bot_out` adds `"group": bot.group`.

**Tests (`tests/test_bots_api.py`):**
- `test_patch_sets_keeps_and_clears_a_group`: `{"group": "Home"}` → `body["group"] == "Home"`; `{"name": "Scout2"}` → still `"Home"`; `{"group": ""}` → `None`; set again, then `{"group": None}` → `None`.
- `test_a_group_must_fit_on_one_line_and_be_short`: `"a\nb"` → 422; 31 characters → 422; 30 → 200.
- `test_another_users_bot_cannot_be_labelled` (async, like `test_other_users_bot_id_is_404_for_get_patch_delete`): 404, and the owner's `GET` shows `group` unchanged.
- `test_patching_a_group_publishes_bot_updated_with_it`: the `bot_updated` frame's `bot["group"] == "Home"`.
- `test_the_group_never_reaches_a_prompt_or_the_roster`: a bot labelled `"Secret label"` → `build_instructions(...)` for a run and the `list_bots` tool's result contain no `"Secret label"` (reuse the rig of `tests/test_list_bots.py`).
- Update `test_create_bot_201_with_expected_shape`: the key set gains `"group"`, and `body["group"] is None`.

- [ ] **Step 1: Path guard.**
- [ ] **Step 2: Red.** `… uv run pytest tests/test_bots_api.py -q` fails on the new cases.
- [ ] **Step 3: Implement** the shapes above.
- [ ] **Step 4: Green.** `… uv run pytest tests/test_bots_api.py tests/test_list_bots.py tests/test_bot_store.py -q`, then the whole suite, pass.
- [ ] **Step 5: Commit**

```bash
cd /Users/blckit/Desktop/Code_Projects/roost && git add roost/gateway/routes/bots.py roost/bots/service.py tests/test_bots_api.py && git commit -m "feat: set, keep or clear a bot's group label through PATCH, shown in BotOut"
```

---

### Task 3: Split `chat.css` and `profile.css` by feature, guarded by a test

Design R1.14; Design meets code 14. A pure move: no rule's text changes.

**Files:**
- Create: `web/src/styles/chat-dock.css`, `web/src/styles/chat-cards.css`, `web/src/styles/chat-sheet.css`, `web/src/styles/instructions.css`, `web/tests/stylesheets.test.ts`
- Modify: `web/src/styles/chat.css`, `web/src/styles/profile.css`, `web/src/styles/avatar-studio.css`, `web/src/styles.css`

**Where each block goes:**
- `chat.css` keeps: `.chat-page`, the message list and messages, activity rows, the empty thread, **Date separators**.
- `chat-dock.css`: **Composer**, **Chat header**, **Dock: the round + beside the pill input**.
- `chat-cards.css`: **Fold cards** and **The Stuck card**.
- `chat-sheet.css`: **Past conversations** sheet (its comment says "Earlier conversations"), its phone `@media` block, `.sheet__empty`, `.chat-readonly*`.
- `profile.css` keeps: name/job editing, the tabs (Documents, Links, Info, switches), the share sheet.
- `instructions.css`: `.instructions-page*`, `.instructions-count*` and the `@media` block that holds them.
- `avatar-studio.css`: gains `.avatar-editor*` and `.avatar-picker*` (appended).
- `web/src/styles.css`: `chat.css`, `chat-dock.css`, `chat-cards.css`, `chat-sheet.css`, `chat-steps.css` in that order; `instructions.css` right after `profile.css`.

**Tests (`web/tests/stylesheets.test.ts`):**
- `it("keeps every stylesheet within 800 lines")`.
- `it("imports every stylesheet in styles/ exactly once")`.
- `it("keeps the chat and profile stylesheets focused")`: `chat.css` and `profile.css` are each ≤ 450 lines, and the four new files exist (red before the split).

- [ ] **Step 1: Path guard.**
- [ ] **Step 2: Red.** `cd web && npx vitest run tests/stylesheets.test.ts` fails on "focused".
- [ ] **Step 3: Move** the blocks with their comments; nothing else changes. Check: the total line count of the moved files equals the old total (± the new header comments).
- [ ] **Step 4: Green.** `cd web && npx vitest run tests/stylesheets.test.ts tests/tokens.test.ts tests/chatLook.test.ts tests/markdownCss.test.ts && npm run build && npm run size` passes.
- [ ] **Step 5: Commit**

```bash
cd /Users/blckit/Desktop/Code_Projects/roost && git add web/src/styles/chat.css web/src/styles/chat-dock.css web/src/styles/chat-cards.css web/src/styles/chat-sheet.css web/src/styles/profile.css web/src/styles/instructions.css web/src/styles/avatar-studio.css web/src/styles.css web/tests/stylesheets.test.ts && git commit -m "refactor: split the chat and profile stylesheets by feature, each within 800 lines"
```

---

### Task 4: The sidebar's sections and avatar row, as pure functions

Design R1.2, R1.3; Design meets code 4–6. Depends on Task 2 (the wire shape).

**Files:**
- Create: `web/src/lib/sidebar.ts`, `web/src/components/sidebar/constants.ts`, `web/tests/sidebar.test.ts`
- Modify: `web/src/api/types.ts` (`BotOut.group: string | null`), `web/src/api/bots.ts` (`BotPatchIn.group?: string | null`), `web/src/lib/botProfile.ts` (`BOT_LIMITS.group: 30`), `web/src/components/ChatList.tsx` (imports `filterChats`, `mainFirst`, `withLiveNames` from `lib/sidebar.ts`; exports none of them), `web/tests/ChatList.test.tsx` (imports from `lib/sidebar`), `web/tests/fixtures.ts` (`makeBot` gives `group: null`)

**Shapes:** the Shared Contract's `lib/sidebar.ts`. `chatSections` = `filterChats(mainFirst(withLiveNames(rows, bots), bots), query)`, then split: section `{label: null}` first with the ungrouped bots and every room, in that order; then one per label sorted with `a.localeCompare(b, undefined, { sensitivity: "base" })`; empty sections dropped. `avatarRow` per Design meets code 6. `usedLabels` = distinct trimmed labels of the other bots, sorted the same way.

**Tests (`web/tests/sidebar.test.ts`):**
- `it("puts ungrouped bots and rooms first, the main bot at the top")`
- `it("makes one section per label, sorted by label, each newest first")`
- `it("keeps a label's spelling as typed and sorts without regard to case")`
- `it("drops a section that search empties")`
- `it("the avatar row is the main bot, then the most recently active bots, at most six")`
- `it("a bot with no chat yet joins the avatar row after the active ones")`
- `it("lists the labels the other bots use, once each, sorted")`

- [ ] **Step 1: Path guard.**
- [ ] **Step 2: Red.** `cd web && npx vitest run tests/sidebar.test.ts` fails (no module).
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Green.** `cd web && npx vitest run tests/sidebar.test.ts tests/ChatList.test.tsx tests/Home.test.tsx && npx tsc --noEmit -p .` passes.
- [ ] **Step 5: Commit**

```bash
cd /Users/blckit/Desktop/Code_Projects/roost && git add web/src/lib/sidebar.ts web/src/components/sidebar/constants.ts web/src/api/types.ts web/src/api/bots.ts web/src/lib/botProfile.ts web/src/components/ChatList.tsx web/tests/sidebar.test.ts web/tests/ChatList.test.tsx web/tests/fixtures.ts && git commit -m "feat: the sidebar's chat sections by group label and its row of bots, as pure functions"
```

---

### Task 5: The fixed sidebar: search and + on top, the bots' row, chats under headings, initials and Board at the bottom

Design R1.1–R1.3. Depends on Task 4.

**Files:**
- Create: `web/src/components/sidebar/SidebarTop.tsx`, `web/src/components/sidebar/AvatarRow.tsx`, `web/src/components/sidebar/SidebarFoot.tsx`, `web/src/styles/sidebar.css`, `web/tests/Sidebar.test.tsx`
- Modify: `web/src/pages/Home.tsx` (`HomeHeader` removed; renders top, a scrolling middle with `AvatarRow`, `MyTurn` and `ChatList`, then the foot), `web/src/components/ChatList.tsx` (draws `chatSections` inside `<nav aria-label="Chats">`, one `<section>` per section: a group's `<h2 className="chat-section__title">` and its `<ul>`; `ChatRow` unchanged), `web/src/styles/layout.css` (`grid-template-columns: var(--sidebar-width) minmax(0, 1fr)`; the aside no longer scrolls itself), `web/src/styles/tokens.css` (`--sidebar-width`, `--panel-width` under Layout), `web/src/styles.css` (`sidebar.css` in place of `home.css`), `web/tests/{Home,ChatList,Layout}.test.tsx`
- Delete: `web/src/styles/home.css` (its rules move to `sidebar.css`; the desktop's empty detail pane rules to `layout.css`)

**Shapes:**
- `SidebarTop({ query, onQuery, onNewRoom })`: `<div className="sidebar-top">` with `<Input type="search" aria-label="Search chats" placeholder="Search">` (the kit's Input, a search icon before it) and the existing `Menu label="New"` (New bot, New room).
- `AvatarRow({ bots, attention, unread })`: `<ul className="avatar-row" aria-label="Your bots">`; each `<li>` holds a `NavLink` to `/bots/{id}` wrapping `<Avatar size={40} label={false} star={bot.is_primary} status={bot.status} decorative />` and a `<span className="sr-only">` with the name (and ", your main bot"); a kit `Tooltip` shows the name. Hidden while `query.trim()` is not empty.
- `SidebarFoot({ notifyOn })`: the old account `Menu` (unchanged items) with the initials, then `<Link to="/board" className="sidebar-foot__board">` holding `BoardIcon` and the word **Board**.
- `.home` becomes a flex column at `height: 100%`: `.sidebar-top` and `.sidebar-foot` are `flex: none`, `.sidebar-scroll` is `flex: 1; overflow-y: auto`.

**Tests (`web/tests/Sidebar.test.tsx`, rendering `Home` in a `MemoryRouter` with the mocks `Home.test.tsx` uses):**
- `it("search and + sit at the top, the initials menu and Board at the bottom")` (DOM order: the searchbox and New button come before the Chats nav, the Account button and Board link after it).
- `it("the avatar row shows the main bot first with its star, and each robot opens its chat")`
- `it("chats sit under their group headings, ungrouped first")`
- `it("each row shows the avatar, name, a plain one-line preview and the unread dot")`
- `it("search filters every section and hides the avatar row")`
- Update `web/tests/Home.test.tsx` ("search filters the chats" types in the always-shown field; the account menu is found by its name), `web/tests/ChatList.test.tsx` (queries `navigation` "Chats"), `web/tests/Layout.test.tsx` if it checks classes.

- [ ] **Step 1: Path guard.**
- [ ] **Step 2: Red.** `cd web && npx vitest run tests/Sidebar.test.tsx` fails.
- [ ] **Step 3: Implement.** Kit components only; colours and sizes from tokens.
- [ ] **Step 4: Green.** `cd web && npx vitest run tests/Sidebar.test.tsx tests/Home.test.tsx tests/ChatList.test.tsx tests/Layout.test.tsx tests/tokens.test.ts tests/stylesheets.test.ts && npm run build && npm run size` passes.
- [ ] **Step 5: Commit**

```bash
cd /Users/blckit/Desktop/Code_Projects/roost && git add web/src/components/sidebar/SidebarTop.tsx web/src/components/sidebar/AvatarRow.tsx web/src/components/sidebar/SidebarFoot.tsx web/src/components/ChatList.tsx web/src/pages/Home.tsx web/src/styles/sidebar.css web/src/styles/layout.css web/src/styles/tokens.css web/src/styles.css web/tests/Sidebar.test.tsx web/tests/Home.test.tsx web/tests/ChatList.test.tsx web/tests/Layout.test.tsx && git rm web/src/styles/home.css && git commit -m "feat: a fixed sidebar with search and + on top, your bots' row, chats under labels, and your initials and Board at the bottom"
```

---

### Task 6: The bot panel beside the chat, kept in the URL

Design R1.5, R1.7 (the hero without the label), R1.8; Design meets code 7–10.

**Files:**
- Create: `web/src/components/panel/BotPanel.tsx`, `web/src/components/panel/PanelHero.tsx`, `web/src/components/panel/panelTabs.ts`, `web/src/hooks/usePanelParam.ts`, `web/src/hooks/useMediaQuery.ts`, `web/src/styles/panel.css`, `web/tests/BotPanel.test.tsx`, `web/tests/usePanelParam.test.tsx`
- Modify: `web/src/pages/Chat.tsx`, `web/src/ui/Sheet.tsx` (`size?: "default" | "full"` → `ui-sheet--full`), `web/src/styles/ui-overlays.css` (`.ui-sheet--full`: inset 0, no radius), `web/src/components/profile/NameJobCard.tsx` (`nameLevel`), `web/src/styles.css` (`panel.css` after `profile.css`), `web/tests/Chat.test.tsx`, `web/tests/sheetFocus.test.tsx` (a full sheet keeps focus inside too)

**Shapes:**
- `Chat` wraps today's header, scroll and dock in `<div className="chat-page__main">`; `.chat-page` gets `chat-page--panel` while a panel is open. `ChatHeader`'s pill is `<Link to={hrefFor(tab ? null : "info")} aria-label={tab ? `Close ${name}'s profile` : `Open ${name}'s profile`} aria-expanded={tab !== null}>`.
- `BotPanel({ bot, tab, onTab, onClose, onChange })`: desktop (`!useMediaQuery(PHONE_QUERY)`): `<aside className="bot-panel" aria-label={`${name}'s profile`} tabIndex={-1}>` focused on open; Escape on it calls `onClose`; head with `IconButton label="Close profile"`; then `PanelHero`, then the kit `Tabs` (`PANEL_TABS`) with Profile's old `PANELS` map moved here (Info, Documents, Computer, Links); the `ShareTemplateDialog` state and the notice line move here too. Phone: the same body inside `<Sheet open size="full" title={`${name}'s profile`} onOpenChange={(o) => { if (!o) onClose(); }}>`. On close, focus returns to the pill (the Sheet does this on a phone; on desktop `Chat` focuses the pill's ref).
- `PanelHero({ bot, onChange })`: `Avatar size={96}` with the star, the "Main bot" mark, `StatusLabel`, `NameJobCard nameLevel="h2"`. (Task 8 adds the label.)
- `panel.css`: `.chat-page--panel` is a two-column grid (`minmax(0, 1fr) var(--panel-width)`) above 1024px; from 769px to 1024px `.bot-panel` is absolute on the right with `--shadow-lg`; it slides in with `transform` over `--duration-slow`, none under `prefers-reduced-motion`.

**Tests:**
- `web/tests/usePanelParam.test.tsx`: `it("reads the tab from ?panel= and an unknown one as Info")`, `it("opens with a new history entry, switches and closes in place")`, `it("keeps ?thread= while it opens and closes")`.
- `web/tests/BotPanel.test.tsx` (Chat in a `MemoryRouter` with the mocks `Chat.test.tsx` uses, `matchMedia` stubbed): `it("the pill opens the panel on Info and the URL says ?panel=info")`, `it("each tab is in the URL")`, `it("the hero shows the robot with its star, the status, and the name and job")`, `it("the Info tab still holds What I remember")`, `it("Close and Escape close the panel and focus goes back to the pill")`, `it("on a phone the panel is a full-screen sheet")`, `it("the chat stays usable while the panel is open")` (the composer still sends).
- `web/tests/Chat.test.tsx`: the pill's `href` is `/bots/bot-1?panel=info`.

- [ ] **Step 1: Path guard.**
- [ ] **Step 2: Red.** `cd web && npx vitest run tests/usePanelParam.test.tsx tests/BotPanel.test.tsx` fails.
- [ ] **Step 3: Implement.** `Profile.tsx` stays in place until Task 7 (both may import the tabs for one commit).
- [ ] **Step 4: Green.** `cd web && npx vitest run tests/usePanelParam.test.tsx tests/BotPanel.test.tsx tests/Chat.test.tsx tests/sheetFocus.test.tsx tests/MemoryPanel.test.tsx tests/ChatThreads.test.tsx tests/tokens.test.ts tests/stylesheets.test.ts && npm run build && npm run size` passes.
- [ ] **Step 5: Commit**

```bash
cd /Users/blckit/Desktop/Code_Projects/roost && git add web/src/components/panel/BotPanel.tsx web/src/components/panel/PanelHero.tsx web/src/components/panel/panelTabs.ts web/src/hooks/usePanelParam.ts web/src/hooks/useMediaQuery.ts web/src/pages/Chat.tsx web/src/ui/Sheet.tsx web/src/components/profile/NameJobCard.tsx web/src/styles/panel.css web/src/styles/ui-overlays.css web/src/styles.css web/tests/BotPanel.test.tsx web/tests/usePanelParam.test.tsx web/tests/Chat.test.tsx web/tests/sheetFocus.test.tsx && git commit -m "feat: the bot's profile opens as a panel beside the chat, its tab in the URL, a full-screen sheet on a phone"
```

---

### Task 7: The old Profile addresses open the panel; the Profile page goes

Design R1.6. Depends on Task 6.

**Files:**
- Create: `web/tests/routes.test.tsx`
- Modify: `web/src/App.tsx` (`ToPanel({ fallback })`: reads `:botId` and `?tab=`, `<Navigate to={`/bots/${botId}?panel=${panelTab(tab) ?? fallback}`} replace />`; `/bots/:botId/profile` → `ToPanel fallback="info"`, `/bots/:botId/desk` → `?panel=computer`), `web/src/components/StuckCard.tsx` (See its screen → `/bots/{id}?panel=computer`), `web/src/pages/Instructions.tsx` (after Save and Back → `/bots/{id}?panel=info`), `web/src/styles/profile.css` (the `.profile-page*` rules removed), `web/tests/StuckCard.test.tsx`, `web/tests/Instructions.test.tsx`, `web/tests/BotPanel.test.tsx` (gains Profile's two cases)
- Delete: `web/src/pages/Profile.tsx`, `web/tests/Profile.test.tsx`

**Tests:**
- `web/tests/routes.test.tsx` (the `AppRoutes` tree under a signed-in mock): `it("the old profile address opens the panel on its tab")`, `it("an unknown or missing tab opens Info")`, `it("the old desk address opens the Computer tab")`.
- `web/tests/BotPanel.test.tsx` gains `it("edits the name in place")` and `it("refuses a name that breaks the line without asking the server")` (moved from `Profile.test.tsx`).
- `web/tests/StuckCard.test.tsx`: See its screen's `href` is `/bots/bot-1?panel=computer`.
- `web/tests/Instructions.test.tsx`: Save and Back land on `/bots/bot-1?panel=info`.

- [ ] **Step 1: Path guard.** Then `grep -rn "/profile" web/src` lists only `App.tsx`'s route after Step 3.
- [ ] **Step 2: Red.** `cd web && npx vitest run tests/routes.test.tsx tests/StuckCard.test.tsx tests/Instructions.test.tsx` fails.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Green.** `cd web && npm test && npm run build && npm run size` passes.
- [ ] **Step 5: Commit**

```bash
cd /Users/blckit/Desktop/Code_Projects/roost && git add web/src/App.tsx web/src/components/StuckCard.tsx web/src/pages/Instructions.tsx web/src/styles/profile.css web/tests/routes.test.tsx web/tests/StuckCard.test.tsx web/tests/Instructions.test.tsx web/tests/BotPanel.test.tsx && git rm web/src/pages/Profile.tsx web/tests/Profile.test.tsx && git commit -m "feat: the old profile and desk addresses open the panel, and the Profile page goes"
```

---

### Task 8: Add a label in the hero; the sidebar follows

Design R1.4, R1.7. Depends on Tasks 4–6.

**Files:**
- Create: `web/src/components/panel/GroupLabel.tsx`, `web/tests/GroupLabel.test.tsx`
- Modify: `web/src/components/panel/PanelHero.tsx` (renders `GroupLabel` under the job), `web/src/lib/botFields.ts` (`checkGroup(value: string): string | null`), `web/src/styles/panel.css`, `web/tests/botFields.test.ts`, `web/tests/Home.test.tsx`

**Shapes:**
- `GroupLabel({ bot, labels, onChange })`, `labels = usedLabels(Object.values(live.bots), bot.id)` from `PanelHero`.
- The trigger is a kit `Chip` button: **Add a label** (quiet) or the label. It opens the kit `Popover label="Label"`: an `Input` labelled **Label** (`maxLength={BOT_LIMITS.group}`), the `labels` as one-tap `Chip` buttons (a tap saves that label), **Save** (`Button` primary sm), and **Remove label** (`Button` ghost sm) only when the bot has one.
- Save: `checkGroup` first (no request on a refusal); then `updateBot(bot.id, { group: text.trim() })`; success → `onChange(bot)` and the popover closes; a server error → `describeError` under the field, the text kept. Remove → `updateBot(bot.id, { group: "" })`.
- `checkGroup`: two lines → `A label fits on one line.`; longer than 30 → `A label is at most 30 characters.`; blank is fine (it clears).

**Tests:**
- `web/tests/GroupLabel.test.tsx`: `it("a bot with no label offers Add a label")`, `it("saves a typed label and shows it as the chip")`, `it("offers the labels other bots use in one tap")`, `it("Remove label clears it")`, `it("refuses two lines or too long a label without asking the server")`, `it("says the server's sentence and keeps your text when it refuses")`.
- `web/tests/botFields.test.ts`: `it("checks a group label: one line, at most 30 characters, blank clears")`.
- `web/tests/Home.test.tsx`: `it("a bot moves under its label when a bot_updated frame says so")`.

- [ ] **Step 1: Path guard.**
- [ ] **Step 2: Red.** `cd web && npx vitest run tests/GroupLabel.test.tsx tests/botFields.test.ts tests/Home.test.tsx` fails.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Green.** `cd web && npx vitest run tests/GroupLabel.test.tsx tests/botFields.test.ts tests/Home.test.tsx tests/BotPanel.test.tsx tests/tokens.test.ts && npm run build && npm run size` passes.
- [ ] **Step 5: Commit**

```bash
cd /Users/blckit/Desktop/Code_Projects/roost && git add web/src/components/panel/GroupLabel.tsx web/src/components/panel/PanelHero.tsx web/src/lib/botFields.ts web/src/styles/panel.css web/tests/GroupLabel.test.tsx web/tests/botFields.test.ts web/tests/Home.test.tsx && git commit -m "feat: add a label to a bot from its profile, and the sidebar groups it"
```

---

### Task 9: Quiet centred activity lines, a NEW divider, day lines and one round composer pill

Design R1.9–R1.12; Design meets code 11–12. Depends on Task 3 (the split stylesheets).

**Files:**
- Create: `web/src/lib/chatMarks.ts`, `web/src/hooks/useSeenAtOpen.ts`, `web/tests/chatMarks.test.ts`
- Modify: `web/src/components/MessageList.tsx` (`withDays` replaced by `chatMarks`; `newAfter` prop; a `new` item renders `<li className="message-new" role="separator" aria-label="New messages">New</li>`), `web/src/components/MessageRow.tsx` (the activity row loses its dot), `web/src/components/Composer.tsx` (`leading`), `web/src/hooks/useAutoGrow.ts` (returns whether it grew), `web/src/pages/Chat.tsx` (`useSeenAtOpen(botId)`; `newAfter` only when `thread.id === main.id`; the + `Menu` passed as `leading`), `web/src/styles/chat.css` (`.message--activity`, `.message--handoff` centred; `.message-date` and `.message-new` share the centred-hairline look), `web/src/styles/chat-dock.css` (the pill), `web/src/styles/memory.css` (`.message--memory` centred), `web/tests/{MessageList,Composer,Chat}.test.tsx`

**Shapes:**
- `firstUnreadId(messages, newAfter)`: `null` when `newAfter` is null; else the id of the first message with `seq > 0`, `role !== "user"` and `Date.parse(created_at) > Date.parse(newAfter)`.
- `chatMarks(messages, newAfter)`: P2's day logic (a message with no readable time joins the day before), then a `{kind: "new", id: `new-${id}`}` item right before the first unread message (after its day line when it starts a day).
- `useSeenAtOpen(chatId)`: `const [snap, setSnap] = useState(() => ({ chatId, seen: readSeen()[chatId] ?? null }))`; when `chatId` changes during render, `setSnap` with a fresh read; returns `snap.seen`.
- The pill: `.composer` with `leading` gets `border-radius: var(--radius-pill)` while one row; `useAutoGrow` now returns `boolean` (true once the box holds more than one row, its callers may ignore it), `Composer` sets `data-rows="many"` from it, and `.composer[data-rows="many"]` takes `--radius-lg`. The + is `--control-lg` round inside it.

**Tests:**
- `web/tests/chatMarks.test.ts`: `it("puts a day line before the first message of each Madrid day")`, `it("puts New above the first message after the seen time that is not yours")`, `it("no New on a first visit, when nothing is new, or when only your messages are newer")`, `it("a message with no readable time joins the day before")`.
- `web/tests/MessageList.test.tsx`: `it("draws the New line as a separator named New messages")`; replace "renders activity lines as their own quiet rows" with `it("draws activity lines centred and quiet, with no dot")`.
- `web/tests/Composer.test.tsx`: `it("holds the leading + inside the pill, before the text")`.
- `web/tests/Chat.test.tsx`: `it("shows New above the first unseen reply in the main chat, and none in an earlier conversation")`, `it("the + sits inside the composer pill")`.

- [ ] **Step 1: Path guard.**
- [ ] **Step 2: Red.** `cd web && npx vitest run tests/chatMarks.test.ts tests/MessageList.test.tsx tests/Composer.test.tsx tests/Chat.test.tsx` fails on the new cases.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Green.** `cd web && npm test && npm run build && npm run size` passes.
- [ ] **Step 5: Commit**

```bash
cd /Users/blckit/Desktop/Code_Projects/roost && git add web/src/lib/chatMarks.ts web/src/hooks/useSeenAtOpen.ts web/src/components/MessageList.tsx web/src/components/MessageRow.tsx web/src/components/Composer.tsx web/src/hooks/useAutoGrow.ts web/src/pages/Chat.tsx web/src/styles/chat.css web/src/styles/chat-dock.css web/src/styles/memory.css web/tests/chatMarks.test.ts web/tests/MessageList.test.tsx web/tests/Composer.test.tsx web/tests/Chat.test.tsx && git commit -m "feat: quiet centred activity lines, a New line at the first unseen reply, and one round composer pill"
```

---

### Task 10: "Computer is asleep" with a sleeping robot

Design R1.13; Design meets code 13.

**Files:**
- Create: `web/src/components/profile/ComputerAsleep.tsx`, `web/tests/ComputerAsleep.test.tsx`
- Modify: `web/src/components/profile/ComputerTab.tsx` (`ScreenBox`'s asleep branch renders `<ComputerAsleep bot={bot} onOpen={onOpen} />`), `web/src/styles/computer.css` (`.computer-asleep`, three `.computer-asleep__z` with a drift keyframe, stopped by `.computer-asleep--still` and by `prefers-reduced-motion`), `web/tests/ComputerTab.test.tsx`

**Shapes:** `ComputerAsleep({ bot, onOpen })`: `<div className={cx("computer-asleep", still && "computer-asleep--still")}>` with `<Avatar avatar={bot.avatar} status={bot.status} moment="off" size={72} label={false} decorative />`, three `<span className="computer-asleep__z" aria-hidden="true">z</span>`, `<h3>Computer is asleep</h3>`, `<p>{name}'s computer wakes when it needs it.</p>` and `<Button variant="primary" size="sm" onClick={onOpen}>Open it</Button>`.

**Tests:**
- `web/tests/ComputerAsleep.test.tsx`: `it("shows the bot's robot asleep, Computer is asleep and Open it")`, `it("the z marks are still under reduced motion")`, `it("Open it starts the browser")`.
- `web/tests/ComputerTab.test.tsx`: "a sleeping computer says so; Open it starts the browser, then the screen shows" finds the heading **Computer is asleep**.

- [ ] **Step 1: Path guard.**
- [ ] **Step 2: Red.** `cd web && npx vitest run tests/ComputerAsleep.test.tsx tests/ComputerTab.test.tsx` fails.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Green.** `cd web && npx vitest run tests/ComputerAsleep.test.tsx tests/ComputerTab.test.tsx tests/robotMotion.test.ts tests/tokens.test.ts tests/stylesheets.test.ts && npm run build && npm run size` passes.
- [ ] **Step 5: Commit**

```bash
cd /Users/blckit/Desktop/Code_Projects/roost && git add web/src/components/profile/ComputerAsleep.tsx web/src/components/profile/ComputerTab.tsx web/src/styles/computer.css web/tests/ComputerAsleep.test.tsx web/tests/ComputerTab.test.tsx && git commit -m "feat: a sleeping robot when a bot's computer is asleep, with Open it"
```

---

### Task 11: E2E for the shell, and the existing specs kept green

Design §Testing. Depends on Tasks 1–10.

**Files:**
- Create: `web/e2e/shell.spec.ts`
- Modify: `web/e2e/helpers.ts` (`openChat` finds the row in `getByRole("navigation", { name: "Chats" })`), and only what the shell changed in: `web/e2e/computer.spec.ts` (heading **Computer is asleep**), `web/e2e/memory.spec.ts` (the panel's **Close profile** instead of "Back to chat"), `web/e2e/profile.spec.ts`, `web/e2e/look.spec.ts`, `web/e2e/every-bot.spec.ts`, `web/e2e/main-bot.spec.ts` (scope a name heading to the panel when it is open). Find them with `grep -rn "Back to chat\|computer is asleep\|getByRole(\"list\", { name: \"Chats\" })" web/e2e`.

**The spec (`web/e2e/shell.spec.ts`)**, desktop viewport unless said:
- `test("the sidebar: search and + on top, your bots' row, chats under a label, your initials and Board at the bottom")`: `signIn` → `createBot(page, "Ivy", "Keeps the house in order")` → the "Your bots" list shows the main bot first → open Ivy's chat → the pill → **Add a label** → type `Home` → **Save** → the sidebar shows a heading `Home` with Ivy's row under it → search `Ivy` keeps that row and hides "Your bots".
- `test("the name pill opens the profile beside the chat, each tab in the address, and Back closes it")`: the pill → URL has `?panel=info` and **What I remember** shows → the Computer tab → `?panel=computer` → `page.goBack()` until no `panel` → the chat's composer is still there.
- `test("the old profile address opens the panel")`: `page.goto("/bots/<id>/profile?tab=links")` → URL `?panel=links`.
- `test("on a phone the profile is a full-screen sheet")`: `page.setViewportSize({ width: 390, height: 844 })` → open a chat → the pill → a dialog named "{name}'s profile" fills the viewport (its bounding box equals the viewport) → **Close profile**.
- `test("the composer is one round pill with + inside")`: the + button is inside the composer's box.

**Final checks (Batch E runs them after Task 12):**
- Disk guard, then `ROOST_DESKS_DIR=$(mktemp -d) make e2e`: every spec passes.

- [ ] **Step 1: Path guard.**
- [ ] **Step 2: Write the spec and the helper change; red** against the old build is not needed (the features exist); run it to green.
- [ ] **Step 3: Green.** Disk guard, then `ROOST_DESKS_DIR=$(mktemp -d) make e2e` passes every spec.
- [ ] **Step 4: Commit**

```bash
cd /Users/blckit/Desktop/Code_Projects/roost && git add web/e2e/shell.spec.ts web/e2e/helpers.ts <each existing spec changed, by name> && git commit -m "test: E2E for the sidebar, the profile panel and the composer pill"
```

---

### Task 12: The docs: CLAUDE.md's map and architecture, guarded by `tests/test_docs.py`

**Files:**
- Modify: `CLAUDE.md`, `tests/test_docs.py`

**Docs:**
- `CLAUDE.md` Documentation Map, after the memory plan line:
  - ``- `docs/plans/2026-10-20-roost-polish-r1-design.md` — polish R1, the Grok-feel shell design: the fixed sidebar (search and + on top, your bots' row, chats under group labels, initials and Board at the bottom), the profile as a panel beside the chat (`?panel=`), quiet centred activity lines, the New line, one round composer pill, and the sleeping computer (R1.1–R1.14).``
  - ``- `docs/plans/2026-10-20-roost-polish-r1.md` — the polish R1 plan: schema v16 (`bots.group_label`), `group` on `PATCH /api/bots/{id}`, `web/src/components/sidebar/`, `web/src/components/panel/`, `lib/chatMarks.ts`, and the split stylesheets.``
- `CLAUDE.md` Architecture, a new paragraph after the chat (P2) paragraph: "The shell (polish R1): the sidebar (`web/src/components/sidebar/`, sorted by `web/src/lib/sidebar.ts`) holds search and + on top, a row of your bots with the main bot first, then the chats under group headings (a bot's optional label, schema v16 `bots.group_label`, sealed under `bots:group_label`, set with `group` on `PATCH /api/bots/{id}`; never sent to a model), and your initials and Board at the bottom. A bot's Profile is a panel beside its chat (`web/src/components/panel/`), its tab in the URL as `?panel=info|documents|computer|links`, a full-screen sheet on a phone; `/bots/:id/profile` redirects to it. The chat draws day lines and a New line at the first message you have not seen (`web/src/lib/chatMarks.ts`), and its composer is one round pill with the + inside. No stylesheet passes 800 lines (`web/tests/stylesheets.test.ts`)."

**Tests (`tests/test_docs.py`):**
- `R1_DOCS = ("docs/plans/2026-10-20-roost-polish-r1-design.md", "docs/plans/2026-10-20-roost-polish-r1.md")` with `test_the_documentation_map_names_the_polish_r1_design_and_plan`.
- `R1_PLACES = ("web/src/components/sidebar/", "web/src/components/panel/", "?panel=", "bots:group_label", "schema v16", "web/src/lib/chatMarks.ts", "web/tests/stylesheets.test.ts")` with `test_the_architecture_section_says_where_the_shell_lives`.

**Final checks:**
- `… uv run pytest --cov=roost --cov-fail-under=80 -q` passes.
- `cd web && npm test && npm run build && npm run size` passes.
- Task 11's `make e2e` passes (run it after this commit if Task 11 ran first).
- `git status --short` lists none of this plan's files.

- [ ] **Step 1: Path guard.**
- [ ] **Step 2: Red.** `… uv run pytest tests/test_docs.py -q` fails on the two new tests.
- [ ] **Step 3: Edit CLAUDE.md.**
- [ ] **Step 4: Green.** `… uv run pytest tests/test_docs.py tests/test_vocabulary.py -q`, then the final checks, pass.
- [ ] **Step 5: Commit**

```bash
cd /Users/blckit/Desktop/Code_Projects/roost && git add CLAUDE.md tests/test_docs.py && git commit -m "docs: polish R1's shell in CLAUDE.md's map and architecture"
```
