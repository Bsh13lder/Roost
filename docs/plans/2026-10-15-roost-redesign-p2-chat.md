# Roost Look & Feel Redesign, P2 Chat, Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A chat that reads like a calm, modern messenger: bot replies drawn as safe markdown from a lazy chunk, borderless messages with copy and time on hover, typing dots and a caret while a bot writes, its steps as compact lines, a composer that grows in every browser without clipping a letter, and a chat list with the main bot first, unread dots and plain previews.

**Architecture:**
- **Markdown, one lazy chunk.** `web/src/components/markdown/Markdown.tsx` becomes the only module that imports `react-markdown` and `remark-gfm`. The notes preview draws through it (inside the already-lazy notes chunk), and the chat reaches it through `React.lazy`, so Vite emits one shared `Markdown-*.js` chunk and the entry grows only by the chat's own code. It renders no raw HTML, shows every link as its real host with `target="_blank" rel="noopener noreferrer"`, never fetches an image, scrolls tables and code inside themselves, gives code a Copy button and draws `[[wikilinks]]` as chips. `bundleGuard.test.ts` and `check-bundle.mjs` keep it out of the entry.
- **Messages** (`web/src/components/chat/`, `MessageRow.tsx`). A bot's text reply is `RichText`: the plain text (links as hosts) while the chunk loads, the markdown once it has, and the plain text for good if the chunk can't load (`FallbackBoundary`). Bubbles lose their borders; your messages are accent bubbles; a long reply is a full-width card. Hover (or keyboard focus) shows the time on Madrid's clock and Copy. A tainted reply carries "from web content".
- **While a bot works.** The reply's placeholder (seq 0, no text yet) shows the bot's robot with its On it signal and three dots, then a caret while text streams. The live store keeps each reply's steps: every `bot_status` activity ("adding a task") seen while that bot's placeholder is open, keyed by the reply's id (`toolLines`). The reply lists them as compact lines ("Added a task"). No backend change; `tests/test_tool_lines.py` keeps the web's past-tense table in step with every verb the gateway announces.
- **The composers** grow with their text through the kit's `fitHeight` (every browser, not only Chromium's `field-sizing`), lose the rounded corners that clipped letters, ignore the Enter an IME uses, and the chat's scroll box follows its own shrinking (`ResizeObserver`), so the last message stays in view.
- **Home.** The main-bot hero goes; the main bot is the first row, wearing its star. The open row has a soft fill, rows show unread dots (remembered in this browser), previews and notifications drop markdown, and every chat-adjacent style leaves the mono stack.

**Tech Stack:** The P1 stack, with no new dependency:
- Python 3.12 (uv), FastAPI, pydantic 2 (no backend change; one new pytest reads the code).
- Vite, React 19 and TypeScript, tested with vitest + Testing Library and Playwright.
- Already installed and MIT: `react-markdown` 10.1.0 and `remark-gfm` 4.0.1 (the notes preview's), the `@radix-ui/*` kit from P1.

**Spec:** `docs/plans/2026-10-15-roost-look-and-feel-design.md`, section "P2 — Chat", decisions V1 (Boxbot), V2 (P4 owns record cards and the canvas), V3 (build order) and V4 (dark only), and the "Evidence" line (audit findings 1, 2, 3, 6, 8 and 10). Where the design and the code disagree, the "Design meets code" list below says what this plan does.

> **Status (2026-10-15): ready to execute.** Written against `night-1` at `c2093a9`. Every task was replayed in order on a throwaway worktree of that commit by a script that applied this plan's Create, Find / Replace and Delete blocks verbatim (each Find matched exactly once), running each task's red and green commands and its commit: vitest 566 tests in 81 files, pytest 1,800 tests (94% coverage), `npm run build`, and all 11 Playwright specs (14 tests) on port 5173. The entry chunk went from about 199 KB to 202.7 KB gzip, within the 257.4 KB budget; the markdown renderer is its own 48.7 KB chunk.

## Global Constraints

- **Path guard, first in every task:**
  - `git -C /Users/blckit/Desktop/Code_Projects/roost rev-parse --show-toplevel` must print `/Users/blckit/Desktop/Code_Projects/roost`.
  - `git -C /Users/blckit/Desktop/Code_Projects/roost branch --show-current` must print `night-1`.
  - If either check fails, stop.
- **Where you may edit:**
  - Edit only under `/Users/blckit/Desktop/Code_Projects/roost`.
  - `/Users/blckit/Desktop/Code_Projects/lazyclaw` is never touched: not `lazyclaw/data`, not its containers, not its `make` targets.
- **The live Roost is never touched:**
  - Never stop, restart, rebuild or call the Docker container `roost-gateway-1` (the live gateway on `127.0.0.1:18800`), the keeper (`127.0.0.1:18801`) or `~/Roost/data`.
  - Any script or probe that imports `roost` runs with `ROOST_DATA_DIR` and `ROOST_DESKS_DIR` set to a fresh `mktemp -d`, and never opens `~/Roost/data`. `uv run pytest` is safe on its own (`tests/conftest.py` repoints both before collection); the commands below set them anyway.
  - `make e2e` starts its own throwaway gateway with `ROOST_DATA_DIR=$(mktemp -d)`; run it as `ROOST_DESKS_DIR=$(mktemp -d) make e2e` so the desks are throwaway too. It picks port 5173 by itself while the live gateway holds 18800. Never point a test at 18800.
- **Clean room (spec §10.3):**
  - Roost's look is its own: no other product's art, mascots, icons or copy.
  - Never open, fetch or search for the open-dot repos, `~/Roost-review/` or `~/.claude/projects/**`. Do not use browser MCP tools.
- **Licences:** only MIT, Apache-2.0, BSD, ISC or MPL-2.0 dependencies. P2 adds none; `web/tests/licenseGate.test.ts` stays green.
- **Disk guard:** before `make e2e`, run `df -g /System/Volumes/Data | awk 'NR==2{print $4}'`. If it shows fewer than 8 GB free, stop and report.
- **No backend change.** P2 changes no file under `roost/`. Its one Python file is a test (`tests/test_tool_lines.py`) that reads code.
- **Tests:**
  - Tests first: red, then green.
  - At least 80% line coverage (`uv run pytest --cov=roost --cov-fail-under=80`).
  - Tests never call a real LLM and never launch a real browser outside Playwright (`tests/conftest.py` forces scripted and fake). Web tests run in jsdom; `web/tests/setup.ts` gives Radix the browser APIs jsdom lacks and, from Task 5, a working `localStorage` (Node 25's own one has no methods and hides jsdom's).
  - P1's picker tests (`DatePicker`, `DateTimePicker`, `ExpenseAddForm`) load the lazy calendar and can pass vitest's 5 s limit while the Mac is very busy (load average above 15). If only those time out in a full `npm test`, run them alone (`npx vitest run tests/DatePicker.test.tsx tests/DateTimePicker.test.tsx tests/ExpenseAddForm.test.tsx`); they pass. Any other failure is real.
- **Code rules:**
  - Files at most 800 lines (typically 200–400); functions under 50 lines.
  - No mutation of shared state: the live store's reducer returns new objects, and the unread record is replaced, never edited.
  - Explicit error handling with user-friendly messages: a failed copy says "Copy failed", a chunk that can't load leaves the plain text, refused storage leaves no dots; each failure is logged with `console.warn`, never swallowed.
  - No magic values: the kit's numbers in `web/src/ui/constants.ts` (`COPY_RESET_MS`), the chat's in `web/src/components/chat/constants.ts`.
- **Tokens:** no colour and no font size is written anywhere in `web/src` but `web/src/styles/tokens.css` and the two colour-data files; `web/tests/tokens.test.ts` enforces it. Every new rule uses the tokens (`--space-*`, `--radius-*`, `--fs-*`, `--color-*`).
- **Mono is for code** (audit finding 8): in `chat.css`, `team.css`, `rooms.css`, `markdown.css` and `home.css`, `--font-mono` appears only in rules for `code` and `pre` (and the Stuck card's full address). `web/tests/chatLook.test.ts` enforces it from Task 2. Times in the chat use one 24-hour Madrid clock (`formatClock`).
- **Dark only (V4):** no light theme in this round.
- **Safety:** a bot's reply renders no raw HTML, no `javascript:` link and no remote image; a link's text is its real host (M1). The chat's localStorage record holds chat ids and times only, never message text.
- **Vocabulary** (the CLAUDE.md table and `tests/test_vocabulary.py`): the statuses verbatim (Resting · On it · Asking you · Stuck · Off duty), "main bot", Board, Profile. Never "Take the wheel", ">Desk<", "Talk ·", " in Talk", "Category", "By category" or "categories" in `web/src`.
- **Git:**
  - Commit after each task's green tests. Stage files **by name**, never `git add -A`, `-a` or `.`.
  - Messages are conventional, with **no Co-Authored-By or any AI attribution line** (CLAUDE.md overrides any default).
- **Commands:**
  - Prefix every command with `cd /Users/blckit/Desktop/Code_Projects/roost &&`.
  - `ROOST_DATA_DIR=$(mktemp -d) ROOST_DESKS_DIR=$(mktemp -d) uv run pytest tests/<file>.py -q` runs one file; the same with no path runs the suite.
  - `cd web && npx vitest run tests/<file>` runs one web test; `npm test` runs them all; `npm run build && npm run size` checks the types, the build and the entry chunk's budget.

## Design meets code

What the design says, what the code holds today, and what this plan does:

1. **"Small cards for tool work: Added task …, Saved document …".** The gateway stores nothing per tool step. While a bot works it only publishes `bot_status` frames whose `activity` is a present-tense phrase without the record's name ("adding a task", "writing a doc", "opening elpais.com"; `roost/*/tools.py` `_ACTIVITY` and the `_announce` calls). P2 builds the lines on the web from those frames, with no backend change: the live store files each activity under the reply the bot is writing (its open placeholder), and the reply lists them, the current one as "Adding a task…", finished ones as "Added a task". They are live only: a reload shows the reply without them. Names, persistence and live records are P4's record cards, as the design says.
2. **"Tainted messages keep their 'from web content' mark".** In chat only the Suggestion and Stuck cards had a mark; a text reply had none. P2 adds a "from web content" badge (the kit's `Badge`, danger tone like the Board's chip, sans type) under a tainted bot reply.
3. **"`[[wikilinks]]` as chips".** The chat has nowhere to open a note yet: there is no note route, and the Board keeps the open note in component state. In chat a wikilink is a plain chip; in the notes preview it stays a button that opens the note. P4's canvas makes the chat's chips open.
4. **"It is already a lazy chunk for notes; reuse it".** `react-markdown` sat inside the lazy `NotesBoard` chunk with the notes code. P2 moves the drawing into `components/markdown/Markdown.tsx`, which both the notes preview (statically, inside the notes chunk) and the chat (through `React.lazy`) use, so Vite emits one `Markdown-*.js` chunk both load: about 49 KB gzip, out of the entry.
5. **"Status faces on avatars", "day separators", "the robot beside bot messages is the new Boxbot".** All three exist already: P1 drew every avatar as a status-aware Boxbot (the chat list passes each bot's status), and S1.5 added the day separators. P2 pins the first with a test, keeps the second, and the typing row's robot shows the On it signal (P1's `Avatar` comment anticipated "think"; the design says On it, so P2 passes the status and fixes the comment).
6. **"Unread dots".** The gateway keeps no read state, and adding one is a schema change the design does not ask for. P2 keeps, in this browser's localStorage, the time of the newest message you have seen in each chat; a chat seen for the first time counts as read, so a new browser starts with no dots. Refused or broken storage means no dots, never an error.
7. **"Long bot replies are full-width cards".** "Long" is not defined. P2: 280 characters or more, more than 4 lines, or any heading, list, table or code block (`isLongReply`).
8. **"The composer never clips the first or last letter".** The cause was the textarea's own pill radius (`.chat-composer .composer__box { border-radius: var(--radius-pill) }`): a textarea scrolls, so its rounded corners clip the glyphs under them. It also grew only through `field-sizing: content`, which only Chromium has. P2 removes the radius, gives the box a little inline padding, and grows it with the kit's `fitHeight` (P1's `Textarea`) in every browser, in both composers.
9. **"The large main-bot hero is dropped".** The hero was the only link named "Chief, your main bot". The main bot's row now carries ", your main bot" as visually hidden text after its name, and `web/e2e/main-bot.spec.ts` checks the first row instead of the hero.
10. **Markdown changes what a spec can read.** `web/e2e/records.spec.ts` waited for the literal text "Saved to [[Ana]]."; drawn as markdown it is "Saved to" and an "Ana" chip, so the spec checks the chip (Task 2).
11. **Audit finding 3 (native date inputs and selects)** was P1's and is done; nothing in the chat uses them. **Finding 10 (canvas hooks)**: P2 leaves the hooks P4 needs: every message row carries `data-message-id`, and a reply's steps render in one component (`ToolLines`) that P4's record cards can replace.

## Review Focus

These are the input classes the design implies but the main tests do not exercise. The test for each one is added to the task named.

1. **A reply written after reading a hostile page:** raw HTML (`<img onerror>`, `<script>`), a `javascript:` link, a remote image (a tracking pixel), a link whose text names another site.
   - Expected: no element made from the HTML (it shows as text), no script link (its words show as plain text), no image fetched (`[image: tracker]`), each link shown as its real host and opened with `noopener noreferrer`, and the reply marked "from web content".
   - Tests: Task 1, `it("renders a hostile reply safely: no raw HTML, no script link, no remote image, real hosts only")` (`web/tests/Markdown.test.tsx`), and Task 2, `it("marks a reply written after reading web content")` (`web/tests/MessageRow.test.tsx`).
2. **The markdown chunk cannot load:** a deploy renamed it while the tab stayed open, or the network dropped.
   - Expected: every reply keeps showing its plain text (links as hosts), the failure is logged, the rest of the chat works.
   - Test: Task 2, `it("keeps the plain text, links drawn as their real host, instead of blanking the chat")` (`web/tests/RichTextFallback.test.tsx`).
3. **Typing in Japanese, Chinese or Korean:** the input method uses Enter to confirm a word.
   - Expected: that Enter never sends; the next plain Enter does.
   - Tests: Task 4, `it("never sends on the Enter that confirms an IME candidate")` (`web/tests/Composer.test.tsx`) and `it("never sends on the Enter that confirms an IME candidate, and grows with its text")` (`web/tests/MentionComposer.test.tsx`).
4. **A wide reply:** a table with long file names, a 190-character code line, a 100-character word.
   - Expected: the table and the code scroll inside themselves; the chat and the page never scroll sideways.
   - Test: Task 6, `test("a markdown reply: its step, a heading, a chip, a table and code that scroll inside it, and Copy code")` (`web/e2e/chat.spec.ts`), against the styles of Tasks 1 and 2.
5. **A browser that refuses storage or holds garbage:** a private window, Safari with site data blocked, a full quota, a value an older version left.
   - Expected: Home lists the chats with no dots and no error; nothing throws.
   - Test: Task 5, `it("starts fresh and never breaks when the browser refuses storage or holds garbage")` (`web/tests/unread.test.ts`).

---

## Shared Contract (every task uses these exact names)

### Markdown (`web/src/components/markdown/`, Task 1)

| File | Export and behaviour |
|---|---|
| `Markdown.tsx` | `export default function Markdown({ text, onWikilink?, className? }: MarkdownProps)`; root `div.md` (+ `className`). The only importer of `react-markdown` and `remark-gfm`. Components: `a` (`[[wikilink]]` → `button.wikilink-chip` when `onWikilink` is given, else `span.wikilink-chip.wikilink-chip--static`; an http(s) link → `a.md__link` showing its host, `target="_blank" rel="noopener noreferrer"`; anything else → `span`), `img` → `span.md__image` "[image: alt]", `pre` → `CodeBlock`, `table` → `div.md__table` (`role="region"`, `aria-label="Table"`, `tabIndex={0}`) around the table. |
| `CodeBlock.tsx` | `CodeBlock({ node?, children })` → `div.md__code` with an `IconButton` (`.md__copy`, labels "Copy code" / "Copied" / "Copy failed") and the `pre`; `hastText(node)` |
| `markdownLinks.ts` | `WIKILINK_PREFIX = "#wikilink/"`, `withWikilinkHrefs(markdown)`, `wikilinkTarget(href): string \| null` (moved from `NotePreview.tsx`, which re-exports `withWikilinkHrefs`) |
| `web/src/hooks/useCopy.ts` | `useCopy(resetMs = COPY_RESET_MS): { state: CopyState; copy(text) }`, `CopyState = "idle" \| "copied" \| "failed"` |
| `web/src/ui/constants.ts` | `COPY_RESET_MS = 1500` |
| `web/src/components/icons.tsx` | `CopyIcon()` |
| `web/src/styles/markdown.css` | `.md` and its blocks, `.md__link`, `.md__image`, `.md__code`, `.md__copy`, `.md__table`, `.wikilink-chip--static` (imported in `styles.css` after `notes.css`) |

### Messages (`web/src/components/chat/`, `MessageRow.tsx`, Tasks 2–3)

| Name | Where | What |
|---|---|---|
| `RichText({ text, id })` | `chat/RichText.tsx` | `lazy(() => import("../markdown/Markdown"))` inside `Suspense` and `FallbackBoundary`, both falling back to `PlainText` |
| `FallbackBoundary({ fallback, children })` | `chat/FallbackBoundary.tsx` | error boundary; logs with `console.warn` |
| `PlainText({ text, keyPrefix })`, `renderBody(body, keyPrefix)` | `chat/PlainText.tsx` | `span.message__plain`; `renderBody` moves here from `MessageRow.tsx` unchanged |
| `MessageActions({ text, createdAt })` | `chat/MessageActions.tsx` | `div.message__actions`: `time.message__time` (`formatClock`) and an `IconButton` "Copy message" / "Copied" / "Copy failed" |
| `isLongReply(text)` | `chat/replyShape.ts` | true for ≥ `LONG_REPLY_CHARS`, > `LONG_REPLY_LINES` lines, or a heading, list, table or code block |
| constants | `chat/constants.ts` | `LONG_REPLY_CHARS = 280`, `LONG_REPLY_LINES = 4` (Task 2), `TOOL_LINES_SHOWN = 5` (Task 3), `COMPOSER_MAX_ROWS = 8` (Task 4) |
| `formatClock(iso)` | `web/src/lib/chatTime.ts` | "14:19" on Madrid's clock, "" for a broken time; `formatChatTime` uses it for today |
| `TypingDots({ name })` | `chat/TypingDots.tsx` | `div.message__typing`, `role="status"`, named "`<name>` is on it", three `WorkingDots` |
| `ToolLines({ lines, working })` | `chat/ToolLines.tsx` | `ul.tool-lines` named "Steps": "`n` earlier step(s)" then the last `TOOL_LINES_SHOWN`; the last one is current (`tool-line--current`, spinner) while `working` |
| `toolLineText(activity, done)`, `PAST` | `web/src/lib/toolLines.ts` | "Adding a task…" / "Added a task" |
| `MessageRow` | `components/MessageRow.tsx` | `li.message` with `data-message-id`; `message--card` for a long bot text reply; `div.message__body` (+ `message__body--streaming` and `aria-busy="true"` while a placeholder's text streams); a Badge "from web content" (`.message__taint`) and `MessageActions` under a settled text message; new prop `toolLines?: readonly string[]` |
| `MessageList` | `components/MessageList.tsx` | new prop `toolLines?: Readonly<Record<string, readonly string[]>>`, passed to each row by message id |
| `LiveState.toolLines` | `web/src/store/live.ts` | `Readonly<Record<string, readonly string[]>>`, `{}` at first. A `bot_status` frame with status `on_it` and an activity appends it to every open placeholder (seq 0, role bot) that bot authored, unless it repeats the last line. `message_done` drops the lines of a reply it drops. |

### The composers (Task 4)

- `useAutoGrow(box: RefObject<HTMLTextAreaElement | null>, value: string, maxRows: number)` (`web/src/hooks/useAutoGrow.ts`), on the kit's `fitHeight`.
- `isSendKey(event): boolean` (`web/src/lib/composerKeys.ts`): Enter without Shift, not while `nativeEvent.isComposing`, not `keyCode` 229.
- `useKeepBottom(): (element: HTMLElement | null) => void | (() => void)` and `followShrink(box, before): number` (`web/src/hooks/useKeepBottom.ts`); `Chat` and `RoomView` put the ref on `.chat-page__scroll`.

### Home (Task 5)

- `plainText(markdown): string` (`web/src/lib/plainText.ts`), on the notes' `plainSnippet`.
- `web/src/lib/unread.ts`: `SeenTimes`, `SeenStorage`, `SEEN_STORAGE_KEY = "roost.chat-seen.v1"`, `readSeen(storage?)`, `writeSeen(seen, storage?)`, `markSeen(rows, seen, openId)`, `unreadChats(rows, seen, openId)`.
- `useUnread(rows): ReadonlySet<string>` (`web/src/hooks/useUnread.ts`), the open chat read from the route (`/bots/:botId`, `/rooms/:roomId`).
- `ChatList`: new prop `unread?: ReadonlySet<string>`; `mainFirst(rows, bots)`; the main bot's name is followed by `span.sr-only` ", your main bot"; `li.chat-row--unread`; `span.chat-row__bottom` holds the preview or status line and `span.chat-row__unread` (visually hidden "Unread").

### File structure

| File | Task | Responsibility |
|---|---|---|
| `web/src/components/markdown/{Markdown.tsx,CodeBlock.tsx,markdownLinks.ts}`, `web/src/components/notes/NotePreview.tsx`, `web/src/hooks/useCopy.ts`, `web/src/ui/constants.ts`, `web/src/components/icons.tsx`, `web/src/styles/{markdown.css,notes.css}`, `web/src/styles.css`, `web/scripts/check-bundle.mjs`, `web/tests/{Markdown.test.tsx,bundleGuard.test.ts}` | 1 | one safe, lazy markdown renderer |
| `web/src/components/chat/{RichText.tsx,FallbackBoundary.tsx,PlainText.tsx,MessageActions.tsx,replyShape.ts,constants.ts}`, `web/src/components/MessageRow.tsx`, `web/src/lib/chatTime.ts`, `web/src/styles/{chat.css,team.css,rooms.css}`, `web/e2e/records.spec.ts`, `web/tests/{MessageRow.test.tsx,RichTextFallback.test.tsx,chatLook.test.ts,bundleGuard.test.ts,ChatThreads.test.tsx}` | 2 | messages: markdown, cards, bubbles, hover actions, the web-content mark |
| `web/src/components/chat/{TypingDots.tsx,ToolLines.tsx,constants.ts}`, `web/src/lib/toolLines.ts`, `web/src/store/live.ts`, `web/src/components/{MessageList,MessageRow,Avatar}.tsx`, `web/src/pages/{Chat,Room}.tsx`, `web/src/styles/chat.css`, `tests/test_tool_lines.py`, `web/tests/{toolLines.test.ts,live.test.ts,MessageList.test.tsx}` | 3 | typing dots, the caret, step lines |
| `web/src/hooks/{useAutoGrow,useKeepBottom}.ts`, `web/src/lib/composerKeys.ts`, `web/src/components/{Composer,MentionComposer}.tsx`, `web/src/components/chat/constants.ts`, `web/src/pages/{Chat,Room}.tsx`, `web/src/styles/chat.css`, `web/tests/{Composer,MentionComposer,useKeepBottom}.test.tsx` | 4 | the composers |
| `web/src/lib/{plainText,unread,attention}.ts`, `web/src/hooks/useUnread.ts`, `web/src/components/ChatList.tsx`, `web/src/pages/Home.tsx`, `web/src/styles/home.css`, `web/tests/{plainText,unread,attention,chatLook}.test.ts`, `web/tests/{ChatList,Home}.test.tsx`, `web/tests/setup.ts`, `web/e2e/main-bot.spec.ts` | 5 | Home and the chat list |
| `web/e2e/chat.spec.ts`, `web/e2e/fixtures/team-script.json`, `CLAUDE.md`, `tests/test_docs.py`, this plan | 6 | E2E, docs, the final checks |

---

### Task 1: One markdown renderer, lazy and safe, shared by the notes preview and the chat

Design P2 "Messages" (markdown, tables, code with copy, links, wikilinks as chips) and Review Focus 1. Today `react-markdown` is used only by `web/src/components/notes/NotePreview.tsx`, inside the lazy notes chunk; the chat shows replies as plain text (audit finding 1).
- **`components/markdown/Markdown.tsx`** becomes the one module that imports `react-markdown` and `remark-gfm`. It keeps every M1 rule the notes preview had (a link shows its real host; images are never fetched; raw HTML is never rendered, it shows as text) and adds what a chat reply needs: links open in a new tab with no opener, a table is its own focusable scroll box, a code block scrolls inside itself and has Copy, and a `[[wikilink]]` is a chip, a button only where something can open the note.
- **`NotePreview.tsx`** shrinks to a call of it. Its `withWikilinkHrefs` moves to `markdownLinks.ts` (re-exported, so `noteText.test.ts` keeps working), and the preview's markdown styles move from `notes.css` to a shared `markdown.css`.
- **`useCopy`** copies to the clipboard and says how it went ("Copied" or "Copy failed") for `COPY_RESET_MS`; it never throws and logs a refusal.
- **The guards:** `bundleGuard.test.ts` fails if anything but `Markdown.tsx` imports `react-markdown` or `remark-gfm`, or anything but the notes preview imports `Markdown` statically; `check-bundle.mjs` refuses an entry chunk that holds react-markdown's changelog address. Task 2 adds the chat's lazy import.

**Files:**
- Create: `web/src/components/markdown/Markdown.tsx`, `web/src/components/markdown/CodeBlock.tsx`, `web/src/components/markdown/markdownLinks.ts`, `web/src/hooks/useCopy.ts`, `web/src/styles/markdown.css`, `web/tests/Markdown.test.tsx`
- Modify: `web/src/components/notes/NotePreview.tsx` (rewritten), `web/src/components/icons.tsx`, `web/src/ui/constants.ts`, `web/src/styles/notes.css`, `web/src/styles.css`, `web/scripts/check-bundle.mjs`, `web/tests/bundleGuard.test.ts`
- Test: `web/tests/Markdown.test.tsx`, `web/tests/bundleGuard.test.ts`; `web/tests/NoteEditor.test.tsx` and `web/tests/noteText.test.ts` stay green unchanged

**Interfaces:**
- Consumes: `linkHost` (`web/src/lib/linkHost.ts`), `mapWikilinks` and `stripFrontMatter` (`web/src/components/notes/noteHelpers.ts`), `wikilinkHref` and `wikilinkLabel` (`web/src/components/notes/wikilink.ts`), `IconButton` and `cx` (`web/src/ui/`), `CheckIcon` (`web/src/components/icons.tsx`).
- Produces: `Markdown` (default export) with `MarkdownProps { text; onWikilink?; className? }`; `CodeBlock`, `hastText`; `WIKILINK_PREFIX`, `withWikilinkHrefs`, `wikilinkTarget`; `useCopy`, `CopyState`; `COPY_RESET_MS`; `CopyIcon`; the CSS classes in the Shared Contract. Task 2 imports `useCopy`, `CopyIcon` and the lazy `../markdown/Markdown`.

- [ ] **Step 1: Path guard**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && git -C /Users/blckit/Desktop/Code_Projects/roost rev-parse --show-toplevel && git -C /Users/blckit/Desktop/Code_Projects/roost branch --show-current`
Expected: `/Users/blckit/Desktop/Code_Projects/roost` then `night-1`. If either differs, stop.

Then confirm P1 has landed and this task has not run:

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && test -f web/src/components/avatar/AvatarStudio.tsx && test ! -f web/src/components/markdown/Markdown.tsx && grep -c 'from "react-markdown"' web/src/components/notes/NotePreview.tsx`
Expected: `1`. Otherwise stop.

- [ ] **Step 2: Write the failing tests**

Create `web/tests/Markdown.test.tsx`:

```tsx
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Markdown from "../src/components/markdown/Markdown";
import { hastText } from "../src/components/markdown/CodeBlock";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

// A bot's reply as the model writes it: a heading, a list, a [[wikilink]], a table, a code block and links.
const REPLY = [
  "## Your week",
  "",
  "- **Monday**: dentist",
  "- Tue: [[Garden plan]]",
  "",
  "| Day | Task |",
  "| --- | --- |",
  "| Mon | Dentist |",
  "",
  "```",
  "npm run build",
  "```",
  "",
  "See https://example.com/a/b and [the docs](https://docs.example/guide).",
].join("\n");

describe("Markdown (redesign P2)", () => {
  it("draws headings, lists, a table in its own scroll box and a code block", () => {
    const { container } = render(<Markdown text={REPLY} />);
    expect(screen.getByRole("heading", { level: 2, name: "Your week" })).toBeInTheDocument();
    expect(screen.getByText("Monday").tagName).toBe("STRONG");
    const table = screen.getByRole("region", { name: "Table" });
    expect(within(table).getByRole("table")).toBeInTheDocument();
    expect(table).toHaveAttribute("tabindex", "0");
    expect(container.querySelector(".md__code pre code")).toHaveTextContent("npm run build");
  });

  it("shows each link as its real host, opening in a new tab with no opener", () => {
    render(<Markdown text={REPLY} />);
    const docs = screen.getByRole("link", { name: "docs.example" });
    expect(docs).toHaveAttribute("href", "https://docs.example/guide");
    expect(docs).toHaveAttribute("target", "_blank");
    expect(docs).toHaveAttribute("rel", "noopener noreferrer");
    expect(screen.getByRole("link", { name: "example.com" })).toHaveAttribute("href", "https://example.com/a/b");
    expect(screen.queryByText("the docs")).toBeNull();
  });

  it("draws a [[wikilink]] as a chip: a plain chip in chat, a button where a note can open", async () => {
    const { unmount } = render(<Markdown text={REPLY} />);
    expect(screen.getByText("Garden plan")).toHaveClass("wikilink-chip", "wikilink-chip--static");
    expect(screen.queryByRole("button", { name: "Garden plan" })).toBeNull();
    unmount();
    const onWikilink = vi.fn();
    render(<Markdown text={REPLY} onWikilink={onWikilink} />);
    await userEvent.click(screen.getByRole("button", { name: "Garden plan" }));
    expect(onWikilink).toHaveBeenCalledWith("Garden plan");
  });

  it("copies a code block's text, and says so", async () => {
    const user = userEvent.setup();
    render(<Markdown text={REPLY} />);
    await user.click(screen.getByRole("button", { name: "Copy code" }));
    expect(await navigator.clipboard.readText()).toBe("npm run build");
    expect(screen.getByRole("button", { name: "Copied" })).toBeInTheDocument();
  });

  it("says Copy failed when the browser refuses the clipboard", async () => {
    const user = userEvent.setup();
    vi.spyOn(navigator.clipboard, "writeText").mockRejectedValue(new DOMException("Denied", "NotAllowedError"));
    render(<Markdown text={REPLY} />);
    await user.click(screen.getByRole("button", { name: "Copy code" }));
    expect(await screen.findByRole("button", { name: "Copy failed" })).toBeInTheDocument();
  });

  // Review Focus 1: a reply written after reading a hostile page.
  it("renders a hostile reply safely: no raw HTML, no script link, no remote image, real hosts only", () => {
    const hostile = [
      '<img src="https://evil.example/x.png" onerror="alert(1)"> <script>alert(2)</script>',
      "",
      "[Your bank](https://phish.example/login) and [run me](javascript:alert(3))",
      "",
      "![tracker](https://evil.example/pixel.png)",
    ].join("\n");
    const { container } = render(<Markdown text={hostile} />);
    expect(container.querySelector("img, script, iframe")).toBeNull();
    expect(container).toHaveTextContent('<img src="https://evil.example/x.png" onerror="alert(1)">');
    expect(screen.getAllByRole("link")).toHaveLength(1);
    expect(screen.getByRole("link", { name: "phish.example" })).toHaveAttribute("href", "https://phish.example/login");
    expect(screen.queryByText("Your bank")).toBeNull();
    expect(screen.getByText("run me").tagName).toBe("SPAN");
    expect(screen.getByText("[image: tracker]")).toBeInTheDocument();
  });

  it("reads a code block's text from its tree", () => {
    const pre = { type: "element", children: [{ type: "element", children: [{ type: "text", value: "a\nb\n" }] }] };
    expect(hastText(pre)).toBe("a\nb\n");
    expect(hastText(undefined)).toBe("");
  });
});
```

`web/tests/bundleGuard.test.ts`. Find:

```ts
const CALENDAR = "ui/date/Calendar.tsx";
```

Replace with:

```ts
const CALENDAR = "ui/date/Calendar.tsx";
// Redesign P2: react-markdown and remark-gfm live only in the markdown renderer, a lazy chunk the notes
// preview and the chat share.
const MARKDOWN = "components/markdown/Markdown.tsx";
const NOTE_PREVIEW = "components/notes/NotePreview.tsx";
```

`web/tests/bundleGuard.test.ts`. Find:

```ts
    const popover = readFileSync(join(SRC, "ui/date/CalendarPopover.tsx"), "utf8");
    expect(popover).toContain('lazy(() => import("./Calendar"))');
  });
});
```

Replace with:

```ts
    const popover = readFileSync(join(SRC, "ui/date/CalendarPopover.tsx"), "utf8");
    expect(popover).toContain('lazy(() => import("./Calendar"))');
  });

  it("imports react-markdown and remark-gfm only in the markdown renderer", () => {
    const importers = sources(SRC)
      .filter((path) => staticImports(path).some((spec) => spec === "react-markdown" || spec === "remark-gfm"))
      .map((path) => relative(SRC, path));
    expect(importers).toEqual([MARKDOWN]);
  });

  it("reaches the markdown renderer statically only from the notes preview, inside the lazy notes chunk", () => {
    const importers = sources(SRC)
      .filter((path) => staticImports(path).some((spec) => /(^|\/)Markdown$/.test(spec)))
      .map((path) => relative(SRC, path));
    expect(importers).toEqual([NOTE_PREVIEW]);
    const notesBoard = sources(SRC)
      .filter((path) => staticImports(path).some((spec) => /(^|\/)NotesBoard$/.test(spec)))
      .map((path) => relative(SRC, path));
    expect(notesBoard).toEqual([]);
  });
});
```

- [ ] **Step 3: Run them to see them fail**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && cd web && npx vitest run tests/Markdown.test.tsx tests/bundleGuard.test.ts`
Expected: FAIL.
- `tests/Markdown.test.tsx` fails to load: `Failed to resolve import "../src/components/markdown/Markdown"`.
- `tests/bundleGuard.test.ts`: 2 failed, 2 passed. The new two fail: `NotePreview.tsx` is still the one importing `react-markdown`, and nothing imports `Markdown`.

- [ ] **Step 4: Copy, its icon and its number**

Create `web/src/hooks/useCopy.ts`:

```ts
import { useCallback, useEffect, useRef, useState } from "react";
import { COPY_RESET_MS } from "../ui/constants";

export type CopyState = "idle" | "copied" | "failed";

// Copies text to the clipboard and says how it went for a moment (redesign P2): "copied", or "failed"
// when the browser has no clipboard here or refuses it. Never throws.
export function useCopy(resetMs: number = COPY_RESET_MS): { state: CopyState; copy: (text: string) => void } {
  const [state, setState] = useState<CopyState>("idle");
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => () => window.clearTimeout(timer.current), []);
  const settle = useCallback((next: CopyState) => {
    setState(next);
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setState("idle"), resetMs);
  }, [resetMs]);
  const copy = useCallback((text: string) => {
    const clipboard = typeof navigator === "undefined" ? undefined : navigator.clipboard;
    if (!clipboard?.writeText) {
      settle("failed");
      return;
    }
    clipboard.writeText(text).then(() => settle("copied"), (error: unknown) => {
      console.warn("Copy to the clipboard failed.", error);
      settle("failed");
    });
  }, [settle]);
  return { state, copy };
}
```

`web/src/ui/constants.ts`. Find:

```ts
export const MAX_DATE_TEXT = 100; // the gateway's MAX_DUE_TEXT_LENGTH (roost/constants.py)
```

Replace with:

```ts
export const MAX_DATE_TEXT = 100; // the gateway's MAX_DUE_TEXT_LENGTH (roost/constants.py)
export const COPY_RESET_MS = 1500; // how long "Copied" (or "Copy failed") shows before Copy comes back
```

`web/src/components/icons.tsx`. Find:

```tsx
export function CheckIcon() {
  return <Icon><path d="M4 10.5l4 4 8-9" /></Icon>;
}
```

Replace with:

```tsx
export function CheckIcon() {
  return <Icon><path d="M4 10.5l4 4 8-9" /></Icon>;
}

export function CopyIcon() {
  return (
    <Icon>
      <rect x={7} y={7} width={10} height={10} rx={2} />
      <path d="M13 7V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h2" />
    </Icon>
  );
}
```

- [ ] **Step 5: The renderer**

Create `web/src/components/markdown/markdownLinks.ts`:

```ts
import { mapWikilinks } from "../notes/noteHelpers";
import { wikilinkHref, wikilinkLabel } from "../notes/wikilink";

// [[wikilinks]] inside markdown (M2, shared by the notes preview and the chat since redesign P2).
export const WIKILINK_PREFIX = "#wikilink/";

// encodeURIComponent leaves ( and ) alone, and an unbalanced one would end the
// markdown link early: "[[Smile :)]]" must still be one chip.
function markdownSafeHref(target: string): string {
  return wikilinkHref(target).replace(/\(/g, "%28").replace(/\)/g, "%29");
}

// [[Target|Label]] → [Label](#wikilink/Target), so the markdown renderer hands
// it to our link component, which draws it as a chip (LazyClaw's NoteDetail bridge).
export function withWikilinkHrefs(markdown: string): string {
  return mapWikilinks(markdown, (link) => `[${wikilinkLabel(link)}](${markdownSafeHref(link.target)})`);
}

// A hand-typed "#wikilink/%E0%A4" can't be decoded: plain text, never a crash.
export function wikilinkTarget(href: string): string | null {
  try {
    return decodeURIComponent(href.slice(WIKILINK_PREFIX.length).split("#")[0]);
  } catch {
    return null;
  }
}
```

Create `web/src/components/markdown/CodeBlock.tsx`:

```tsx
import type { ReactNode } from "react";
import { useCopy } from "../../hooks/useCopy";
import { IconButton } from "../../ui/IconButton";
import { CheckIcon, CopyIcon } from "../icons";

// The part of a hast node a code block needs: its text lives in "text" leaves.
interface HastNode {
  type: string;
  value?: string;
  children?: readonly HastNode[];
}

const COPY_LABEL = { idle: "Copy code", copied: "Copied", failed: "Copy failed" } as const;

// A code block's text as the reader would select it.
export function hastText(node: HastNode | undefined): string {
  if (!node) return "";
  if (node.type === "text") return node.value ?? "";
  return (node.children ?? []).map(hastText).join("");
}

// A fenced code block (redesign P2): it scrolls inside itself, and Copy sits in its corner.
export function CodeBlock({ node, children }: { node?: unknown; children?: ReactNode }) {
  const { state, copy } = useCopy();
  const text = hastText(node as HastNode | undefined).replace(/\n$/, "");
  return (
    <div className="md__code">
      <IconButton className="md__copy" label={COPY_LABEL[state]} tooltip={false} size="sm"
        icon={state === "copied" ? <CheckIcon /> : <CopyIcon />} onClick={() => copy(text)} />
      <pre>{children}</pre>
    </div>
  );
}
```

Create `web/src/components/markdown/Markdown.tsx`:

```tsx
import type { ReactNode } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { linkHost } from "../../lib/linkHost";
import { cx } from "../../ui/cx";
import { CodeBlock } from "./CodeBlock";
import { WIKILINK_PREFIX, wikilinkTarget, withWikilinkHrefs } from "./markdownLinks";

// Markdown for bot replies and note previews (redesign P2). The only module that imports react-markdown,
// so it loads as one lazy chunk (web/tests/bundleGuard.test.ts). Safe by construction:
// - raw HTML is never rendered: react-markdown shows it as text;
// - a link's text is its real host (M1), it opens in a new tab with no opener, and only http(s) is a link;
// - an image is never fetched: it shows as "[image: alt]";
// - a [[wikilink]] is a chip: a button where the page can open the note, a plain chip elsewhere.
export interface MarkdownProps {
  text: string;
  onWikilink?: (target: string) => void;
  className?: string;
}

const PLUGINS = [remarkGfm];

interface LinkProps {
  href?: string;
  onWikilink?: (target: string) => void;
  children?: ReactNode;
}

function MarkdownLink({ href, onWikilink, children }: LinkProps) {
  if (href?.startsWith(WIKILINK_PREFIX)) {
    const target = wikilinkTarget(href);
    if (target === null) return <span>{children}</span>;
    if (!onWikilink) return <span className="wikilink-chip wikilink-chip--static">{children}</span>;
    return <button type="button" className="wikilink-chip" onClick={() => onWikilink(target)}>{children}</button>;
  }
  const host = linkHost(href);
  if (host === null) return <span>{children}</span>;
  return <a href={href} target="_blank" rel="noopener noreferrer" className="md__link">{host}</a>;
}

function components(onWikilink?: (target: string) => void): Components {
  return {
    a: ({ href, children }) => <MarkdownLink href={href} onWikilink={onWikilink}>{children}</MarkdownLink>,
    // Never fetched: drawing a reply or a note must not send anything to the host an image names.
    img: ({ alt }) => <span className="md__image">{`[image: ${alt || "untitled"}]`}</span>,
    pre: ({ node, children }) => <CodeBlock node={node}>{children}</CodeBlock>,
    // A wide table scrolls inside its own box, never the chat or the page.
    table: ({ children }) => (
      <div className="md__table" role="region" aria-label="Table" tabIndex={0}>
        <table>{children}</table>
      </div>
    ),
  };
}

export default function Markdown({ text, onWikilink, className }: MarkdownProps) {
  return (
    <div className={cx("md", className)}>
      <ReactMarkdown remarkPlugins={PLUGINS} components={components(onWikilink)}>
        {withWikilinkHrefs(text)}
      </ReactMarkdown>
    </div>
  );
}
```

`web/src/components/notes/NotePreview.tsx`. Replace the whole file (today 70 lines, from `import type { ReactNode } from "react";` to the end of `NotePreview`) with:

```tsx
import Markdown from "../markdown/Markdown";
import { stripFrontMatter } from "./noteHelpers";

export { withWikilinkHrefs } from "../markdown/markdownLinks";

export interface NotePreviewProps {
  content: string;
  onWikilink: (target: string) => void;
}

// A note's markdown, drawn by the shared renderer (redesign P2), where a [[link]] opens its note.
export function NotePreview({ content, onWikilink }: NotePreviewProps) {
  return <Markdown className="note-preview" text={stripFrontMatter(content)} onWikilink={onWikilink} />;
}
```

- [ ] **Step 6: The styles**

Create `web/src/styles/markdown.css`:

```css
/* ---------------------------------------------------------------------
   Markdown (redesign P2): bot replies and note previews, both drawn by
   components/markdown/Markdown.tsx. Tailwind's preflight strips every
   element's own look, so the blocks get theirs back here. Mono is for
   code only.
   --------------------------------------------------------------------- */

.md {
  min-width: 0;
  line-height: 1.6;
  overflow-wrap: anywhere;
}

.md > :first-child {
  margin-top: 0;
}

.md > :last-child {
  margin-bottom: 0;
}

.md :is(p, ul, ol, blockquote, .md__code, .md__table) {
  margin: 0 0 var(--space-3);
}

.md :is(h1, h2, h3, h4, h5, h6) {
  margin: var(--space-4) 0 var(--space-2);
  font-family: var(--font-sans);
  font-weight: 600;
  line-height: 1.3;
}

.md h1 {
  font-size: var(--fs-heading);
}

.md h2 {
  font-size: var(--fs-lead);
}

.md :is(h3, h4, h5, h6) {
  font-size: var(--fs-body);
}

.md ul {
  padding-left: 22px;
  list-style: disc;
}

.md ol {
  padding-left: 22px;
  list-style: decimal;
}

.md li + li {
  margin-top: var(--space-1);
}

.md li > :is(ul, ol) {
  margin: var(--space-1) 0 0;
}

.md .contains-task-list {
  padding-left: 2px;
  list-style: none;
}

.md input[type="checkbox"] {
  margin-right: 6px;
  accent-color: var(--color-accent);
}

.md blockquote {
  padding-left: var(--space-3);
  border-left: 3px solid var(--color-border-strong);
  color: var(--color-text-secondary);
}

.md code {
  padding: 1px 6px;
  border-radius: var(--radius-xs);
  background: var(--color-raised);
  font: var(--fs-label) var(--font-mono);
}

.md hr {
  margin: var(--space-4) 0;
  border: 0;
  border-top: 1px solid var(--color-border);
}

.md__link {
  color: var(--color-accent-strong);
  text-decoration: underline;
  text-underline-offset: 2px;
}

.md__image {
  color: var(--color-text-secondary);
  font-style: italic;
}

/* A code block scrolls inside itself; Copy sits in its corner. */
.md__code {
  position: relative;
}

.md__code pre {
  margin: 0;
  padding: var(--space-3) 44px var(--space-3) var(--space-3);
  border-radius: var(--radius-sm);
  background: var(--color-sunken);
  overflow-x: auto;
  overflow-wrap: normal;
  white-space: pre;
}

.md__code pre code {
  padding: 0;
  background: none;
}

.md__copy {
  position: absolute;
  top: 6px;
  right: 6px;
  color: var(--color-text-secondary);
}

/* A table is its own scroll box, never wider than the reply. */
.md__table {
  max-width: 100%;
  overflow-x: auto;
  border-radius: var(--radius-sm);
}

.md__table:focus-visible {
  outline: 2px solid var(--color-accent-strong);
}

.md__table table {
  border-collapse: collapse;
}

.md :is(th, td) {
  padding: 6px 10px;
  border: 1px solid var(--color-border);
  overflow-wrap: normal;
  text-align: left;
}

.md th {
  background: var(--color-raised);
  font-weight: 600;
}

/* A [[wikilink]] where nothing opens it yet (the chat, until P4's canvas). */
.wikilink-chip--static {
  cursor: default;
}
```

`web/src/styles.css`. Find:

```css
@import "./styles/notes.css";
```

Replace with:

```css
@import "./styles/notes.css";
@import "./styles/markdown.css";
```

`web/src/styles/notes.css`. Find:

```css
.note-preview {
  padding: 12px 16px; border: 1px solid var(--color-border); border-radius: var(--radius-md);
  background: var(--color-panel); line-height: 1.6; overflow-wrap: anywhere;
}
.note-preview__image { color: var(--color-text-secondary); font-style: italic; }
/* Markdown in the preview: Tailwind's preflight strips every element's own look. */
.note-preview > :first-child { margin-top: 0; }
.note-preview > :last-child { margin-bottom: 0; }
.note-preview :is(p, ul, ol, blockquote, pre, table) { margin: 0 0 12px; }
.note-preview :is(h1, h2, h3, h4, h5, h6) {
  margin: 20px 0 8px; font-family: var(--font-sans); font-weight: 600; line-height: 1.25;
}
.note-preview h1 { font-size: var(--fs-title); }
.note-preview h2 { font-size: var(--fs-lead); }
.note-preview :is(h3, h4, h5, h6) { font-size: var(--fs-body); }
.note-preview ul { padding-left: 22px; list-style: disc; }
.note-preview ol { padding-left: 22px; list-style: decimal; }
.note-preview li + li { margin-top: 4px; }
.note-preview li > :is(ul, ol) { margin: 4px 0 0; }
.note-preview .contains-task-list { padding-left: 2px; list-style: none; }
.note-preview input[type="checkbox"] { margin-right: 6px; accent-color: var(--color-accent); }
.note-preview blockquote { padding-left: 12px; border-left: 3px solid var(--color-border-strong); color: var(--color-text-secondary); }
.note-preview code { padding: 1px 6px; border-radius: 6px; background: var(--color-raised); font: var(--fs-label) var(--font-mono); }
.note-preview pre { padding: 12px; border-radius: var(--radius-sm); background: var(--color-sunken); overflow-x: auto; }
.note-preview pre code { padding: 0; background: none; }
.note-preview hr { margin: 16px 0; border: 0; border-top: 1px solid var(--color-border); }
.note-preview table { display: block; max-width: 100%; overflow-x: auto; border-collapse: collapse; }
.note-preview :is(th, td) { padding: 6px 10px; border: 1px solid var(--color-border); text-align: left; }
.note-preview th { background: var(--color-raised); font-weight: 600; }
.note-preview__link { color: var(--color-accent-strong); text-decoration: underline; text-underline-offset: 2px; }
```

Replace with:

```css
/* The preview's box; its markdown is styled in markdown.css (redesign P2). */
.note-preview {
  padding: 12px 16px; border: 1px solid var(--color-border); border-radius: var(--radius-md);
  background: var(--color-panel);
}
.note-preview.md h1 { font-size: var(--fs-title); }
```

- [ ] **Step 7: The size check refuses react-markdown in the entry**

`web/scripts/check-bundle.mjs`. Find:

```js
// Redesign P1: react-day-picker's class prefix. The calendar is a lazy chunk; it must never be in the entry.
const LAZY_ONLY_MARKERS = ["rdp-"];
```

Replace with:

```js
// Code that must stay in a lazy chunk, found by a string only it carries: react-day-picker's class prefix
// (redesign P1) and react-markdown's changelog address (redesign P2).
const LAZY_ONLY_MARKERS = {
  "rdp-": "The calendar (react-day-picker)",
  "remarkjs/react-markdown": "The markdown renderer (react-markdown)",
};
```

`web/scripts/check-bundle.mjs`. Find:

```js
const leaked = LAZY_ONLY_MARKERS.filter((marker) => text.includes(marker));
if (leaked.length > 0) {
  console.error(`The calendar is in the main bundle (${leaked.join(", ")}): import it through React.lazy only.`);
  process.exit(1);
}
```

Replace with:

```js
const leaked = Object.entries(LAZY_ONLY_MARKERS).filter(([marker]) => text.includes(marker));
if (leaked.length > 0) {
  console.error(`${leaked.map(([, what]) => what).join(" and ")} is in the main bundle: import it through React.lazy only.`);
  process.exit(1);
}
```

- [ ] **Step 8: Run the tests to see them pass**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && cd web && npx vitest run tests/Markdown.test.tsx tests/bundleGuard.test.ts tests/NoteEditor.test.tsx tests/noteText.test.ts tests/tokens.test.ts`
Expected: PASS: `Markdown` 7, `bundleGuard` 4, and the notes and token tests as before.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && cd web && npm test && npm run build && npm run size`
Expected:
- every vitest file passes;
- the build succeeds; the renderer still rides in the lazy `NotesBoard-*.js` chunk (it gets a chunk of its own in Task 2, once the chat loads it too);
- the size check prints the entry within budget (about 199 KB gzip of 257 KB), and does not say "The markdown renderer (react-markdown) is in the main bundle".

- [ ] **Step 9: Commit**

Run:

```bash
cd /Users/blckit/Desktop/Code_Projects/roost && \
git add web/src/components/markdown/Markdown.tsx web/src/components/markdown/CodeBlock.tsx \
  web/src/components/markdown/markdownLinks.ts web/src/components/notes/NotePreview.tsx web/src/hooks/useCopy.ts \
  web/src/ui/constants.ts web/src/components/icons.tsx web/src/styles/markdown.css web/src/styles/notes.css \
  web/src/styles.css web/scripts/check-bundle.mjs web/tests/Markdown.test.tsx web/tests/bundleGuard.test.ts && \
git commit -m "feat: one lazy markdown renderer for notes and chat: tables in a scroll box, code with Copy, links as their real host"
```

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && git status --short`
Expected: none of the files above is listed.

---

### Task 2: Bot replies as markdown, borderless messages, long replies as cards, copy and time on hover

Design P2 "Messages" and Review Focus 1 and 2. Today `MessageRow.tsx` draws every body as plain text inside a bordered bubble (`chat.css`), shows no time and offers no copy, and a tainted text reply carries no mark.
- **`RichText`** draws a bot's text reply through the lazy `Markdown` (Task 1). The plain text (links as their real host, `PlainText`, the old `renderBody` moved out of `MessageRow`) shows while the chunk loads, and stays for good if it cannot load: `FallbackBoundary` catches the failed import and logs it. Your own messages, notices and card fallbacks stay plain text.
- **Messages lose their borders.** A bot's short reply sits on a soft fill; yours is an accent bubble (white text on violet, 4.5:1 or more by P1's token test); a long reply (`isLongReply`) is a full-width card.
- **Hover actions.** On hover or keyboard focus a small bar shows the time on Madrid's clock (`formatClock`, the chat's one time format) and Copy, which copies the message as written ("Copied", or "Copy failed" when the browser refuses). On a touch screen the bar sits under the message. A reply still being written has no bar.
- **"from web content"** marks a tainted bot reply, always visible.
- **Mono is for code** (audit finding 8): the activity rows, the handoff arrow, the room's "coordinator" chip and New room's note leave the mono stack; `chatLook.test.ts` keeps it so.
- Every message row carries `data-message-id` (P4's canvas hooks).
- Two specs depended on the old look: `ChatThreads.test.tsx` read a whole row's text (now it also holds the time), so it reads the body; `web/e2e/records.spec.ts` waited for the literal "Saved to [[Ana]].", now an "Ana" chip (Design meets code 10). Task 6 runs the E2E.

**Files:**
- Create: `web/src/components/chat/RichText.tsx`, `web/src/components/chat/FallbackBoundary.tsx`, `web/src/components/chat/PlainText.tsx`, `web/src/components/chat/MessageActions.tsx`, `web/src/components/chat/replyShape.ts`, `web/src/components/chat/constants.ts`, `web/tests/MessageRow.test.tsx`, `web/tests/RichTextFallback.test.tsx`, `web/tests/chatLook.test.ts`
- Modify: `web/src/components/MessageRow.tsx` (rewritten), `web/src/lib/chatTime.ts`, `web/src/styles/chat.css`, `web/src/styles/team.css`, `web/src/styles/rooms.css`, `web/tests/bundleGuard.test.ts`, `web/tests/ChatThreads.test.tsx`, `web/e2e/records.spec.ts`
- Test: the three new files, `web/tests/bundleGuard.test.ts`, `web/tests/ChatThreads.test.tsx`, `web/tests/MessageList.test.tsx` (unchanged, still green)

**Interfaces:**
- Consumes: `Markdown` (Task 1, lazily), `useCopy`, `CopyIcon`, `CheckIcon`; `IconButton`, `Badge`, `cx` (`web/src/ui/`); `linkHost`; `Avatar`, `CreatedBotCard`, `SuggestionCard`, `StuckCard`; `parseStuckMessage`, `parseCreatedCard`, `parseSuggestion`.
- Produces: `RichText({ text, id })`, `FallbackBoundary`, `PlainText({ text, keyPrefix })`, `renderBody(body, keyPrefix)`, `MessageActions({ text, createdAt })`, `isLongReply(text)`, `LONG_REPLY_CHARS`, `LONG_REPLY_LINES`, `formatClock(iso)`; `MessageRow` with the classes in the Shared Contract (`message--card`, `message__plain`, `message__actions`, `message__time`, `message__taint`, `data-message-id`). Task 3 adds `toolLines` and the typing state to `MessageRow`.

- [ ] **Step 1: Path guard**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && git -C /Users/blckit/Desktop/Code_Projects/roost rev-parse --show-toplevel && git -C /Users/blckit/Desktop/Code_Projects/roost branch --show-current`
Expected: `/Users/blckit/Desktop/Code_Projects/roost` then `night-1`. If either differs, stop.

Then confirm Task 1 has landed and this task has not:

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && test -f web/src/components/markdown/Markdown.tsx && test ! -f web/src/components/chat/RichText.tsx && grep -c "export function renderBody" web/src/components/MessageRow.tsx`
Expected: `1`. Otherwise stop.

- [ ] **Step 2: Write the failing tests**

Create `web/tests/MessageRow.test.tsx`:

```tsx
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { MessageRow, type MessageRowProps } from "../src/components/MessageRow";
import { makeBot, makeMessage } from "./fixtures";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

const SCOUT = makeBot({ id: "bot-1", name: "Scout" });

function renderRow(overrides: Partial<MessageRowProps> = {}) {
  const props: MessageRowProps = {
    message: makeMessage({ author_bot_id: "bot-1" }), runStart: true, fallbackName: "Scout", team: [SCOUT], ...overrides,
  };
  return render(<MemoryRouter><ul><MessageRow {...props} /></ul></MemoryRouter>);
}

describe("MessageRow (redesign P2)", () => {
  it("draws a bot's reply as markdown once the renderer has loaded", async () => {
    renderRow({ message: makeMessage({ author_bot_id: "bot-1", body: "**Done.** See [[Garden plan]]." }) });
    expect((await screen.findByText("Done.")).tagName).toBe("STRONG");
    expect(screen.getByText("Garden plan")).toHaveClass("wikilink-chip");
  });

  it("keeps your own message as you typed it, in an accent bubble", () => {
    const { container } = renderRow({ message: makeMessage({ role: "user", body: "**not bold** please" }) });
    expect(screen.getByText("**not bold** please")).toBeInTheDocument();
    expect(container.querySelector("li")).toHaveClass("message--user");
    expect(container.querySelector("strong")).toBeNull();
  });

  it("makes a long reply a full-width card and keeps a short one a bubble", () => {
    const long = renderRow({ message: makeMessage({ author_bot_id: "bot-1", body: "## Plan\n\n- one\n- two" }) });
    expect(long.container.querySelector("li")).toHaveClass("message--card");
    cleanup();
    const short = renderRow({ message: makeMessage({ author_bot_id: "bot-1", body: "On it." }) });
    expect(short.container.querySelector("li")).not.toHaveClass("message--card");
  });

  it("shows the Madrid time it was sent and copies the message as written", async () => {
    const user = userEvent.setup();
    renderRow({ message: makeMessage({ author_bot_id: "bot-1", body: "**Done.**", created_at: "2026-10-14T12:19:00Z" }) });
    expect(screen.getByText("14:19")).toHaveAttribute("datetime", "2026-10-14T12:19:00Z");
    await user.click(screen.getByRole("button", { name: "Copy message" }));
    expect(await navigator.clipboard.readText()).toBe("**Done.**");
    expect(screen.getByRole("button", { name: "Copied" })).toBeInTheDocument();
  });

  it("marks a reply written after reading web content", () => {
    renderRow({ message: makeMessage({ author_bot_id: "bot-1", body: "The page says the shop opens at 9.", tainted: true }) });
    expect(screen.getByText("from web content")).toBeInTheDocument();
  });

  it("offers no copy and no time on a reply still being written, nor on a card", () => {
    renderRow({ message: makeMessage({ author_bot_id: "bot-1", body: "", seq: 0 }), liveText: "Wri" });
    expect(screen.queryByRole("button", { name: "Copy message" })).toBeNull();
    cleanup();
    const body = JSON.stringify({ name: "Ledger", job: "Keeps the books", avatar: { shape: "wide", color: "#3b82f6", badge: "finance" } });
    renderRow({ message: makeMessage({ kind: "suggestion", author_bot_id: "bot-1", body }) });
    expect(screen.getByRole("button", { name: "Create this bot" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Copy message" })).toBeNull();
  });
});
```

Create `web/tests/RichTextFallback.test.tsx`:

```tsx
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { RichText } from "../src/components/chat/RichText";

// Review Focus 2: the markdown chunk fails to load (a deploy renamed it while this tab stayed open).
vi.mock("../src/components/markdown/Markdown", () => {
  throw new Error("Failed to fetch dynamically imported module");
});

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe("RichText when the markdown renderer cannot load", () => {
  it("keeps the plain text, links drawn as their real host, instead of blanking the chat", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    render(<RichText text="**Done.** See https://example.com/x" id="m-1" />);
    await vi.waitFor(() => expect(warn).toHaveBeenCalled());
    expect(screen.getByText("**Done.** See", { exact: false })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "example.com" })).toHaveAttribute("href", "https://example.com/x");
  });
});
```

Create `web/tests/chatLook.test.ts`:

```ts
// @vitest-environment node
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { formatChatTime, formatClock } from "../src/lib/chatTime";

// Audit finding 8 (redesign P2): in the chat, mono is for code only, never chips, times, dates or amounts,
// and every time is one 24-hour clock on Madrid time.
const STYLES = fileURLToPath(new URL("../src/styles/", import.meta.url));
const CHAT_STYLESHEETS = ["chat.css", "team.css", "rooms.css", "markdown.css"];
// Code, and a Stuck card's full address, which is shown verbatim on purpose.
const CODE_SELECTOR = /\b(?:code|pre)\b|stuck-card__url/;
const COMMENT = /\/\*[\s\S]*?\*\//g;
const RULE = /([^{}]+)\{([^{}]*)\}/g;
const MONO = /font(?:-family)?\s*:[^;]*var\(--font-mono\)/;

function monoSelectors(css: string): string[] {
  return [...css.replace(COMMENT, "").matchAll(RULE)]
    .filter(([, , body]) => MONO.test(body))
    .map(([, selector]) => selector.trim());
}

describe("the chat's type and time (audit finding 8)", () => {
  it("uses mono only for code in the chat's stylesheets", () => {
    const found = CHAT_STYLESHEETS.flatMap((file) => monoSelectors(readFileSync(STYLES + file, "utf8"))
      .filter((selector) => !CODE_SELECTOR.test(selector))
      .map((selector) => `${file}: ${selector}`));
    expect(found).toEqual([]);
  });

  it("finds a mono rule when there is one (the scanner works)", () => {
    const css = ".a { font-family: var(--font-mono); }\n@media (x) {\n  .b code { font: var(--fs-label) var(--font-mono); }\n}";
    expect(monoSelectors(css)).toEqual([".a", ".b code"]);
  });

  it("says every message and chat-list time on one 24-hour Madrid clock", () => {
    expect(formatClock("2026-10-14T12:19:00Z")).toBe("14:19");
    expect(formatClock("2026-01-14T12:19:00Z")).toBe("13:19"); // winter time
    expect(formatChatTime("2026-10-14T12:19:00Z", new Date("2026-10-14T13:00:00Z"))).toBe(formatClock("2026-10-14T12:19:00Z"));
    expect(formatClock("not a time")).toBe("");
  });
});
```

`web/tests/bundleGuard.test.ts`. Find:

```ts
    expect(notesBoard).toEqual([]);
  });
});
```

Replace with:

```ts
    expect(notesBoard).toEqual([]);
  });

  it("the chat reaches the markdown renderer through React.lazy only", () => {
    const richText = readFileSync(join(SRC, "components/chat/RichText.tsx"), "utf8");
    expect(richText).toContain('lazy(() => import("../markdown/Markdown"))');
  });
});
```

`web/tests/ChatThreads.test.tsx` (a row now also holds the time it was sent, so the order is read from the bodies). Find:

```tsx
    expect(rows.map((row) => row.textContent?.replace(/^(You|Scout)/, ""))).toEqual(["first", "reply b1", "second", "reply b2"]);
```

Replace with:

```tsx
    expect(rows.map((row) => row.querySelector(".message__body")?.textContent)).toEqual(["first", "reply b1", "second", "reply b2"]);
```

`web/e2e/records.spec.ts`. Find:

```ts
  await sayAndSee(page, "Office", "note: Ana's birthday is 3 May, she likes orchids", "Saved to [[Ana]].");
```

Replace with:

```ts
  await say(page, "Office", "note: Ana's birthday is 3 May, she likes orchids");
  // Redesign P2: the reply is markdown, so its [[Ana]] is a chip.
  const saved = detailPane(page).locator(".message--bot").filter({ hasText: "Saved to" });
  await expect(saved.locator(".wikilink-chip", { hasText: "Ana" })).toBeVisible();
```

- [ ] **Step 3: Run them to see them fail**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && cd web && npx vitest run tests/MessageRow.test.tsx tests/RichTextFallback.test.tsx tests/chatLook.test.ts tests/bundleGuard.test.ts tests/ChatThreads.test.tsx`
Expected: FAIL.
- `tests/RichTextFallback.test.tsx` fails to load: `Failed to resolve import "../src/components/chat/RichText"`.
- `tests/MessageRow.test.tsx`: 4 failed, 2 passed (no markdown, no card, no time or Copy, no mark yet).
- `tests/chatLook.test.ts`: 2 failed, 1 passed: four mono rules (`chat.css` `.message--activity`, `team.css` `.message__handoff-arrow`, `rooms.css` `.room-pick__note` and `.room-header__role`) and `formatClock is not a function`.
- `tests/bundleGuard.test.ts`: 1 failed (no `RichText.tsx`), 4 passed.
- `tests/ChatThreads.test.tsx` passes: its new reading works on today's rows too.

- [ ] **Step 4: The pieces**

Create `web/src/components/chat/constants.ts`:

```ts
// The chat's numbers (redesign P2), in one place.
export const LONG_REPLY_CHARS = 280; // a bot reply this long is a full-width card, not a bubble
export const LONG_REPLY_LINES = 4; // so is one with more lines than this
```

Create `web/src/components/chat/replyShape.ts`:

```ts
import { LONG_REPLY_CHARS, LONG_REPLY_LINES } from "./constants";

// A heading, a fenced code block, a list item or a table row at the start of a line.
const BLOCK_MARKDOWN = /^(?:#{1,6}\s|```|\s*[-*+]\s|\s*\d+[.)]\s|\s*\|.*\|)/m;

// A reply that reads better full width (redesign P2): long, or built of markdown blocks.
export function isLongReply(text: string): boolean {
  return text.length >= LONG_REPLY_CHARS || text.split("\n").length > LONG_REPLY_LINES || BLOCK_MARKDOWN.test(text);
}
```

Create `web/src/components/chat/PlainText.tsx` (`renderBody` is moved here from `MessageRow.tsx`, unchanged):

```tsx
import { linkHost } from "../../lib/linkHost";

// Splits a message body into plain-text segments and http(s) links. A
// link renders as its real hostname (never the raw URL or any text the
// bot supplied for it) so a bot can't disguise where a link actually
// goes — this is also why remote images are never rendered at all: the
// body is plain text, there is no markdown image syntax or <img> path here.
const LINK_PATTERN = /https?:\/\/[^\s<>"')]+/g;

export function renderBody(body: string, keyPrefix: string) {
  const parts: Array<string | { url: string; host: string }> = [];
  let lastIndex = 0;
  for (const match of body.matchAll(LINK_PATTERN)) {
    const url = match[0];
    const start = match.index ?? 0;
    if (start > lastIndex) parts.push(body.slice(lastIndex, start));
    const host = linkHost(url);
    parts.push(host ? { url, host } : url);
    lastIndex = start + url.length;
  }
  if (lastIndex < body.length) parts.push(body.slice(lastIndex));

  return parts.map((part, index) => {
    const key = `${keyPrefix}-${index}`;
    if (typeof part === "string") return <span key={key}>{part}</span>;
    return (
      <a key={key} href={part.url} target="_blank" rel="noopener noreferrer" className="message__link">
        {part.host}
      </a>
    );
  });
}

// A body as written (redesign P2): your own messages, notices, and a bot's reply while the markdown
// renderer loads, or if it never does. Its line breaks are kept (styles/chat.css).
export function PlainText({ text, keyPrefix }: { text: string; keyPrefix: string }) {
  return <span className="message__plain">{renderBody(text, keyPrefix)}</span>;
}
```

Create `web/src/components/chat/FallbackBoundary.tsx`:

```tsx
import { Component, type ErrorInfo, type ReactNode } from "react";

interface FallbackBoundaryProps {
  fallback: ReactNode;
  children: ReactNode;
}

// Shows `fallback` instead of a part that failed to draw (redesign P2: a lazy chunk that could not load),
// so one broken piece never blanks the whole chat. The failure is logged, never hidden.
export class FallbackBoundary extends Component<FallbackBoundaryProps, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError(): { failed: boolean } {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.warn("Showing plain text: the markdown renderer could not load.", error, info.componentStack);
  }

  render(): ReactNode {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}
```

Create `web/src/components/chat/RichText.tsx`:

```tsx
import { lazy, Suspense } from "react";
import { FallbackBoundary } from "./FallbackBoundary";
import { PlainText } from "./PlainText";

// The markdown renderer is a lazy chunk (shared with the notes preview), so the entry stays in budget.
const Markdown = lazy(() => import("../markdown/Markdown"));

// A bot's reply as markdown (redesign P2). The plain text shows while the renderer loads, and stays if it
// never does: the reply is always readable.
export function RichText({ text, id }: { text: string; id: string }) {
  const plain = <PlainText text={text} keyPrefix={id} />;
  return (
    <FallbackBoundary fallback={plain}>
      <Suspense fallback={plain}>
        <Markdown text={text} />
      </Suspense>
    </FallbackBoundary>
  );
}
```

Create `web/src/components/chat/MessageActions.tsx`:

```tsx
import { useCopy } from "../../hooks/useCopy";
import { formatClock } from "../../lib/chatTime";
import { IconButton } from "../../ui/IconButton";
import { CheckIcon, CopyIcon } from "../icons";

const COPY_LABEL = { idle: "Copy message", copied: "Copied", failed: "Copy failed" } as const;

// A message's quiet actions (redesign P2): the time it was sent, on Madrid's clock, and Copy, which copies
// the message as it was written. They show on hover or keyboard focus (styles/chat.css).
export function MessageActions({ text, createdAt }: { text: string; createdAt: string }) {
  const { state, copy } = useCopy();
  const clock = formatClock(createdAt);
  return (
    <div className="message__actions">
      {clock ? <time className="message__time" dateTime={createdAt}>{clock}</time> : null}
      <IconButton label={COPY_LABEL[state]} tooltip={false} size="sm"
        icon={state === "copied" ? <CheckIcon /> : <CopyIcon />} onClick={() => copy(text)} />
    </div>
  );
}
```

`web/src/lib/chatTime.ts`. Find:

```ts
export function formatChatTime(iso: string, now: Date = new Date()): string {
  const when = new Date(iso);
  if (Number.isNaN(when.getTime())) return "";
  const days = daysBetween(when, now);
  if (days <= 0) return clockFormat.format(when);
```

Replace with:

```ts
// A message's own time (redesign P2): 14:19 on Madrid's clock, the chat's one time format.
export function formatClock(iso: string): string {
  const when = new Date(iso);
  return Number.isNaN(when.getTime()) ? "" : clockFormat.format(when);
}

export function formatChatTime(iso: string, now: Date = new Date()): string {
  const when = new Date(iso);
  if (Number.isNaN(when.getTime())) return "";
  const days = daysBetween(when, now);
  if (days <= 0) return formatClock(iso);
```

- [ ] **Step 5: The row**

`web/src/components/MessageRow.tsx`. Replace the whole file (today 138 lines, starting `// One row of a conversation: a bubble (you on the right, a bot on the`) with:

```tsx
// One row of a conversation: a message (you on the right in an accent bubble, a bot on the left, a long
// reply as a full-width card), a quiet line (activity, a handoff between bots, a notice), a suggestion
// card, a "Created <name>" card or a Stuck card. Split out of MessageList so the list stays a loop.
import { Avatar } from "./Avatar";
import { CreatedBotCard } from "./CreatedBotCard";
import { StuckCard } from "./StuckCard";
import { SuggestionCard } from "./SuggestionCard";
import { MessageActions } from "./chat/MessageActions";
import { PlainText } from "./chat/PlainText";
import { RichText } from "./chat/RichText";
import { isLongReply } from "./chat/replyShape";
import { Badge } from "../ui/Badge";
import { cx } from "../ui/cx";
import { parseStuckMessage } from "../lib/stuck";
import { parseCreatedCard, parseSuggestion } from "../lib/team";
import type { AvatarOut, BotOut, MessageOut, StuckCardOut } from "../api/types";

export interface MessageRowProps {
  message: MessageOut;
  runStart: boolean;
  liveText?: string;
  fallbackName: string;
  fallbackAvatar?: AvatarOut;
  team: readonly BotOut[];
  // Every Stuck card this page knows, by card id: a "stuck" message folds once its card is closed.
  stuck?: Readonly<Record<string, StuckCardOut>>;
  // Rooms only: a bot's text message gets a Reply that addresses its author.
  onReply?: (author: BotOut) => void;
}

function authorOf(message: MessageOut, team: readonly BotOut[]): BotOut | undefined {
  return message.author_bot_id ? team.find((bot) => bot.id === message.author_bot_id) : undefined;
}

// Handoff lines, activity lines and notices: one quiet row, no bubble.
function QuietRow({ message, kind }: { message: MessageOut; kind: string }) {
  if (kind === "handoff") {
    return (
      <li className="message message--activity message--handoff">
        <span className="message__handoff-arrow" aria-hidden="true">
          ⇄
        </span>
        <span className="message__handoff-text">{message.body}</span>
      </li>
    );
  }
  if (message.role === "activity") {
    return (
      <li className="message message--activity">
        <span className="message__activity-dot" aria-hidden="true" />
        <span className="message__activity-text">{message.body}</span>
      </li>
    );
  }
  return <li className={`message message--notice message--notice-${kind}`}>{message.body}</li>;
}

const NO_STUCK: Readonly<Record<string, StuckCardOut>> = {};

interface RowBodyProps {
  message: MessageOut;
  kind: string;
  text: string;
  name: string;
  team: readonly BotOut[];
  stuck: Readonly<Record<string, StuckCardOut>>;
}

// A card when the body is a valid one for its kind; otherwise the text: a bot's reply as markdown, anything
// else as written, its links drawn safely either way.
function RowBody({ message, kind, text, name, team, stuck }: RowBodyProps) {
  const created = kind === "bot_created" ? parseCreatedCard(message.body) : null;
  if (created) return <CreatedBotCard card={created} team={team} />;
  const suggestion = kind === "suggestion" ? parseSuggestion(message.body) : null;
  if (suggestion) return <SuggestionCard suggestion={suggestion} team={team} tainted={message.tainted} />;
  const blocked = kind === "stuck" ? parseStuckMessage(message.body) : null;
  if (blocked) {
    return <StuckCard data={blocked} card={stuck[blocked.card_id]} botName={name} tainted={message.tainted} />;
  }
  const rich = message.role === "bot" && kind === "text";
  return (
    <div className="message__body">
      {rich ? <RichText text={text} id={message.id} /> : <PlainText text={text} keyPrefix={message.id} />}
    </div>
  );
}

// Under a settled text message: the "from web content" mark (always shown) and its hover actions.
function MessageMeta({ message, isUser }: { message: MessageOut; isUser: boolean }) {
  return (
    <>
      {message.tainted && !isUser ? <Badge tone="danger" className="message__taint">from web content</Badge> : null}
      <MessageActions text={message.body} createdAt={message.created_at} />
    </>
  );
}

export function MessageRow({
  message, runStart, liveText, fallbackName, fallbackAvatar, team, stuck = NO_STUCK, onReply,
}: MessageRowProps) {
  const kind = message.kind ?? "text";
  if (kind === "handoff" || message.role === "activity" || message.role === "system") {
    return <QuietRow message={message} kind={kind} />;
  }
  const isUser = message.role === "user";
  const author = authorOf(message, team);
  const name = isUser ? "You" : author?.name ?? fallbackName;
  const avatar = author?.avatar ?? fallbackAvatar;
  const text = liveText ?? message.body;
  // A reply still being written (seq 0) has nothing to copy yet.
  const settled = message.seq !== 0 && (kind === "text" || kind === "card_answer");
  const card = !isUser && kind === "text" && isLongReply(text);
  return (
    <li className={cx("message", isUser ? "message--user" : "message--bot", runStart && "message--run-start", card && "message--card")}
      data-message-id={message.id}>
      {!isUser && avatar ? (
        <span className="message__avatar">
          {runStart ? <Avatar avatar={avatar} status="resting" size={32} label={false} decorative /> : null}
        </span>
      ) : null}
      <div className="message__content">
        <div className={`message__author${runStart && !isUser ? "" : " sr-only"}`}>{name}</div>
        <RowBody message={message} kind={kind} text={text} name={name} team={team} stuck={stuck} />
        {settled ? <MessageMeta message={message} isUser={isUser} /> : null}
        {onReply && author && kind === "text" && !isUser ? (
          <button type="button" className="message__reply" aria-label={`Reply to ${author.name}`} onClick={() => onReply(author)}>
            Reply
          </button>
        ) : null}
      </div>
    </li>
  );
}
```

- [ ] **Step 6: The styles**

`web/src/styles/chat.css`. Find:

```css
.message__content {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
```

Replace with:

```css
.message__content {
  position: relative;
  display: flex;
  flex-direction: column;
  min-width: 0;
}
```

`web/src/styles/chat.css`. Find:

```css
.message__body {
  padding: 9px 15px;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
  line-height: 1.5;
}

.message--bot .message__body {
  border: 1px solid var(--color-border);
  border-radius: 6px 20px 20px 20px;
  background: var(--color-raised);
}

.message--bot:not(.message--run-start) .message__body {
  border-radius: 6px 20px 20px 6px;
}

.message--user .message__body {
  border: 1px solid var(--color-accent-edge);
  border-radius: 22px 22px 6px 22px;
  background: var(--color-accent-tint);
  color: var(--color-text);
}

.message__link {
  color: var(--color-accent-soft);
  text-decoration: underline;
  text-decoration-color: var(--color-accent-edge);
  text-underline-offset: 3px;
}

.message--activity {
  align-self: flex-start;
  align-items: center;
  gap: 8px;
  max-width: 100%;
  padding: 3px 0 3px 42px;
  color: var(--color-text-secondary);
  font-family: var(--font-mono);
  font-size: var(--fs-caption);
}
```

Replace with:

```css
/* No borders (redesign P2): a bot's short reply sits on a soft fill, yours in an accent bubble, and a
   long reply is a full-width card. */
.message__body {
  min-width: 0;
  padding: 9px 15px;
  overflow-wrap: anywhere;
  line-height: 1.5;
}

/* Plain text keeps its line breaks; markdown lays out its own blocks. */
.message__plain {
  white-space: pre-wrap;
}

.message--bot .message__body {
  border-radius: var(--radius-xs) var(--radius-lg) var(--radius-lg) var(--radius-lg);
  background: var(--color-raised);
}

.message--bot:not(.message--run-start) .message__body {
  border-radius: var(--radius-xs) var(--radius-lg) var(--radius-lg) var(--radius-xs);
}

.message--user .message__body {
  border-radius: var(--radius-lg) var(--radius-lg) var(--radius-xs) var(--radius-lg);
  background: var(--color-accent);
  color: var(--color-on-accent);
}

.message--card {
  align-self: stretch;
  max-width: 100%;
}

.message--card .message__content {
  flex: 1;
}

.message--card .message__body,
.message--card:not(.message--run-start) .message__body {
  padding: var(--space-4) var(--space-5);
  border-radius: var(--radius-md);
  background: var(--color-panel);
  box-shadow: var(--shadow-sm);
}

.message__link {
  color: var(--color-accent-strong);
  text-decoration: underline;
  text-underline-offset: 3px;
}

.message--user .message__link {
  color: var(--color-on-accent);
}

/* The "from web content" mark: always shown under a reply that read a page. */
.message__taint {
  align-self: flex-start;
  margin-top: var(--space-1);
}

/* Time and Copy float over the message's top edge on hover or keyboard focus, over the free side. */
.message__actions {
  position: absolute;
  top: calc(-1 * var(--space-3));
  z-index: 1;
  display: flex;
  align-items: center;
  gap: var(--space-1);
  padding: 2px 2px 2px var(--space-3);
  border-radius: var(--radius-pill);
  background: var(--color-overlay);
  box-shadow: var(--shadow-sm);
  opacity: 0;
  pointer-events: none;
  transition: opacity var(--duration-fast) var(--ease-standard);
}

.message--bot .message__actions {
  left: var(--space-2);
}

.message--user .message__actions {
  right: var(--space-2);
}

.message--card .message__actions {
  right: var(--space-3);
  left: auto;
}

.message:hover .message__actions,
.message:focus-within .message__actions {
  opacity: 1;
  pointer-events: auto;
}

.message__actions .icon-btn {
  color: var(--color-text-secondary);
}

.message__time {
  color: var(--color-text-secondary);
  font-size: var(--fs-caption);
  font-variant-numeric: tabular-nums;
}

/* A touch screen has no hover: the actions sit quietly under the message instead. */
@media (hover: none) {
  .message__actions {
    position: static;
    align-self: flex-start;
    margin-top: 2px;
    padding: 0;
    background: none;
    box-shadow: none;
    opacity: 1;
    pointer-events: auto;
  }

  .message--user .message__actions {
    align-self: flex-end;
  }
}

.message--activity {
  align-self: flex-start;
  align-items: center;
  gap: 8px;
  max-width: 100%;
  padding: 3px 0 3px 42px;
  color: var(--color-text-secondary);
  font-size: var(--fs-caption);
}
```

`web/src/styles/team.css`. Find:

```css
.message__handoff-arrow { flex: none; color: var(--color-accent-strong); font-family: var(--font-mono); }
```

Replace with:

```css
.message__handoff-arrow { flex: none; color: var(--color-accent-strong); }
```

`web/src/styles/rooms.css`. Find:

```css
.room-pick__note {
  margin-left: auto;
  color: var(--color-text-faint);
  font-family: var(--font-mono);
  font-size: var(--fs-caption);
}
```

Replace with:

```css
.room-pick__note {
  margin-left: auto;
  color: var(--color-text-faint);
  font-size: var(--fs-caption);
}
```

`web/src/styles/rooms.css`. Find:

```css
.room-header__role {
  padding: 1px 8px;
  border: 1px solid var(--color-accent-edge);
  border-radius: var(--radius-pill);
  color: var(--color-accent-strong);
  font-family: var(--font-mono);
  font-size: var(--fs-caption);
}
```

Replace with:

```css
.room-header__role {
  padding: 1px 8px;
  border: 1px solid var(--color-accent-edge);
  border-radius: var(--radius-pill);
  color: var(--color-accent-strong);
  font-size: var(--fs-caption);
}
```

- [ ] **Step 7: Run the tests to see them pass**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && cd web && npx vitest run tests/MessageRow.test.tsx tests/RichTextFallback.test.tsx tests/chatLook.test.ts tests/bundleGuard.test.ts tests/ChatThreads.test.tsx tests/MessageList.test.tsx tests/Room.test.tsx tests/Chat.test.tsx tests/tokens.test.ts`
Expected: PASS.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && cd web && npm test && npm run build && npm run size`
Expected: every vitest file passes; the build lists `Markdown-*.js` apart from the entry; the entry stays within budget (about 200 KB gzip).

- [ ] **Step 8: Commit**

Run:

```bash
cd /Users/blckit/Desktop/Code_Projects/roost && \
git add web/src/components/chat/RichText.tsx web/src/components/chat/FallbackBoundary.tsx \
  web/src/components/chat/PlainText.tsx web/src/components/chat/MessageActions.tsx web/src/components/chat/replyShape.ts \
  web/src/components/chat/constants.ts web/src/components/MessageRow.tsx web/src/lib/chatTime.ts \
  web/src/styles/chat.css web/src/styles/team.css web/src/styles/rooms.css web/tests/MessageRow.test.tsx \
  web/tests/RichTextFallback.test.tsx web/tests/chatLook.test.ts web/tests/bundleGuard.test.ts \
  web/tests/ChatThreads.test.tsx web/e2e/records.spec.ts && \
git commit -m "feat: bot replies as markdown, borderless bubbles and full-width cards, copy and time on hover, the web-content mark"
```

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && git status --short`
Expected: none of the files above is listed.

---

### Task 3: Typing dots, a caret while text streams, and the bot's steps as compact lines

Design P2 "Typing indicator" and "Small cards for tool work" (audit finding 2). Today a reply's placeholder (a `message` frame with seq 0 and no body, published before the bot's first step) draws as an empty bubble until text streams, and a bot's steps reach the web only as `bot_status` frames whose `activity` the chat header shows and then forgets.
- **Typing.** While a reply has no text yet, its row shows the bot's robot with the On it signal and three animated dots (`TypingDots`, a status named "`<bot>` is on it"), never an empty bubble. Once text streams, the body carries `message__body--streaming` and `aria-busy="true"`, and a caret follows the text (CSS). Reduced motion stills the caret and the spinner.
- **Steps.** The live store's reducer files every `bot_status` activity of a bot that is On it under the reply it is writing: its open placeholder (seq 0, role bot, authored by that bot), keyed by the reply's id, without repeating the last line. The stored reply keeps the placeholder's id, so its lines stay with it; a reply closed with nothing stored drops them. `ToolLines` lists the last five ("2 earlier steps" before them): the current one as "Saving a note…" with a spinner, finished ones as "Added a task" with a tick (`toolLineText`, `PAST`). Live only, as the design says (P4 stores record cards).
- **The verbs.** `tests/test_tool_lines.py` imports every domain's `_ACTIVITY` table and scans `roost/talk/*.py` for `announce("…")`, and fails if the web's `PAST` table lacks the past tense of any verb the gateway announces.
- `Avatar.tsx`'s comment said P2 would show "think"; it shows the On it status, and the comment says so.

**Files:**
- Create: `web/src/lib/toolLines.ts`, `web/src/components/chat/TypingDots.tsx`, `web/src/components/chat/ToolLines.tsx`, `web/tests/toolLines.test.ts`, `tests/test_tool_lines.py`
- Modify: `web/src/store/live.ts`, `web/src/components/MessageList.tsx`, `web/src/components/MessageRow.tsx`, `web/src/components/Avatar.tsx`, `web/src/components/chat/constants.ts`, `web/src/pages/Chat.tsx`, `web/src/pages/Room.tsx`, `web/src/styles/chat.css`, `web/tests/live.test.ts`, `web/tests/MessageList.test.tsx`
- Test: `web/tests/toolLines.test.ts`, `web/tests/live.test.ts`, `web/tests/MessageList.test.tsx`, `tests/test_tool_lines.py`

**Interfaces:**
- Consumes: Task 2's `MessageRow` (its `RowBody`, `writing` rows), `cx`, `CheckIcon`, `WorkingDots` (`web/src/components/WorkingIndicator.tsx`), `Avatar` (status `on_it` draws the `onit` moment), `BotStatusFrame` (`web/src/api/types.ts`); `roost.{tasks,money,notes,documents,projects}.tools._ACTIVITY`.
- Produces: `LiveState.toolLines`; `toolLineText(activity, done)`; `TypingDots({ name })`; `ToolLines({ lines, working })`; `TOOL_LINES_SHOWN = 5`; `MessageList`'s and `MessageRow`'s `toolLines` props. A mocked live state without `toolLines` still renders (the list's default is `{}`).

- [ ] **Step 1: Path guard**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && git -C /Users/blckit/Desktop/Code_Projects/roost rev-parse --show-toplevel && git -C /Users/blckit/Desktop/Code_Projects/roost branch --show-current`
Expected: `/Users/blckit/Desktop/Code_Projects/roost` then `night-1`. If either differs, stop.

Then confirm Task 2 has landed and this task has not:

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && test -f web/src/components/chat/RichText.tsx && test ! -f web/src/lib/toolLines.ts && grep -c "toolLines" web/src/store/live.ts`
Expected: `0`. Otherwise stop.

- [ ] **Step 2: Write the failing tests**

Create `web/tests/toolLines.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { toolLineText } from "../src/lib/toolLines";

describe("toolLineText (redesign P2)", () => {
  it("says the current step as it happens", () => {
    expect(toolLineText("adding a task", false)).toBe("Adding a task…");
  });

  it("says a finished step in the past tense", () => {
    expect(toolLineText("adding a task", true)).toBe("Added a task");
    expect(toolLineText("writing a doc", true)).toBe("Wrote a doc");
    expect(toolLineText("reading elpais.com", true)).toBe("Read elpais.com");
    expect(toolLineText("setting a budget", true)).toBe("Set a budget");
    expect(toolLineText("asking Scout", true)).toBe("Asked Scout");
  });

  it("keeps a line it has no past tense for as it is, capitalised", () => {
    expect(toolLineText("waiting: you have control of my computer", true)).toBe("Waiting: you have control of my computer");
  });
});
```

Create `tests/test_tool_lines.py`:

```python
"""Redesign P2: a bot's steps show in its reply as compact lines, and a finished step reads in the past
tense ("adding a task" becomes "Added a task"). The web does that with one table, ``PAST`` in
``web/src/lib/toolLines.ts``; this test keeps it in step with every verb the gateway announces."""

import re
from pathlib import Path

from roost.documents.tools import _ACTIVITY as DOCUMENT_ACTIVITY
from roost.money.tools import _ACTIVITY as MONEY_ACTIVITY
from roost.notes.tools import _ACTIVITY as NOTE_ACTIVITY
from roost.projects.tools import _ACTIVITY as PROJECT_ACTIVITY
from roost.tasks.tools import _ACTIVITY as TASK_ACTIVITY

ROOT = Path(__file__).resolve().parents[1]
TOOL_LINES = ROOT / "web" / "src" / "lib" / "toolLines.ts"
TALK = ROOT / "roost" / "talk"
ANNOUNCED = re.compile(r'announce\(f?"([a-z]+)[ :]')
PAST_ENTRY = re.compile(r'\b([a-z]+): "[a-z]+"')


def _web_past_verbs() -> set[str]:
    table = TOOL_LINES.read_text(encoding="utf-8").split("const PAST")[1].split("};")[0]
    return set(PAST_ENTRY.findall(table))


def _announced_verbs() -> set[str]:
    domain = [*TASK_ACTIVITY.values(), *MONEY_ACTIVITY.values(), *NOTE_ACTIVITY.values(),
              *DOCUMENT_ACTIVITY.values(), *PROJECT_ACTIVITY.values()]
    spoken = [verb for path in TALK.glob("*.py") for verb in ANNOUNCED.findall(path.read_text(encoding="utf-8"))]
    return {text.split()[0] for text in domain} | set(spoken)


def test_the_scan_finds_the_web_table_and_the_spoken_verbs():
    assert {"adding", "writing"} <= _web_past_verbs()
    assert {"opening", "reading", "asking", "creating", "waiting"} <= _announced_verbs()


def test_every_announced_verb_has_a_past_tense_on_the_web():
    assert sorted(_announced_verbs() - _web_past_verbs()) == []
```

`web/tests/live.test.ts`. Find:

```ts
    // The reducer never mutates its input (immutability rule).
    expect(opened.stuckCards["card-1"].state).toBe("open");
  });
});
```

Replace with:

```ts
    // The reducer never mutates its input (immutability rule).
    expect(opened.stuckCards["card-1"].state).toBe("open");
  });
});

describe("tool lines (redesign P2)", () => {
  const placeholder = (id: string): ServerFrame => ({
    type: "message", seq: 1, thread_id: "t", message: makeMessage({ id, thread_id: "t", seq: 0, body: "", author_bot_id: "bot-1" }),
  });
  const status = (seq: number, activity: string | null, botId = "bot-1", state: BotOut["status"] = "on_it"): ServerFrame =>
    ({ type: "bot_status", seq, bot_id: botId, status: state, activity });

  it("starts with none", () => {
    expect(initialLiveState().toolLines).toEqual({});
  });

  it("adds each new activity of a working bot to the reply it is writing, once", () => {
    const before = applyFrame(initialLiveState(), placeholder("r1"));
    let state = applyFrame(before, status(2, "adding a task"));
    state = applyFrame(state, status(3, "adding a task"));
    state = applyFrame(state, status(4, "saving a note"));
    expect(state.toolLines).toEqual({ r1: ["adding a task", "saving a note"] });
    expect(before.toolLines).toEqual({}); // the reducer never mutates its input
  });

  it("keeps the lines on the stored reply, which takes the placeholder's id", () => {
    let state = applyFrame(initialLiveState(), placeholder("r1"));
    state = applyFrame(state, status(2, "adding a task"));
    state = applyFrame(state, {
      type: "message", seq: 3, thread_id: "t", message: makeMessage({ id: "r1", thread_id: "t", seq: 4, body: "Added.", author_bot_id: "bot-1" }),
    });
    state = applyFrame(state, { type: "message_done", seq: 5, thread_id: "t", message_id: "r1" });
    state = applyFrame(state, status(6, "checking your tasks")); // no reply is open now: it joins none
    expect(state.toolLines).toEqual({ r1: ["adding a task"] });
  });

  it("ignores another bot's steps, a status with no activity, and a Stuck bot's line", () => {
    let state = applyFrame(initialLiveState(), placeholder("r1"));
    state = applyFrame(state, status(2, "opening elpais.com", "bot-2"));
    state = applyFrame(state, status(3, null));
    state = applyFrame(state, status(4, "waiting for login.example to let me in", "bot-1", "stuck"));
    expect(state.toolLines).toEqual({});
  });

  it("drops the lines of a reply that closed with nothing stored", () => {
    let state = applyFrame(initialLiveState(), placeholder("r1"));
    state = applyFrame(state, status(2, "adding a task"));
    state = applyFrame(state, { type: "message_done", seq: 3, thread_id: "t", message_id: "r1" });
    expect(state.toolLines).toEqual({});
  });
});
```

`web/tests/MessageList.test.tsx`. Find:

```tsx
import { cleanup, render, screen } from "@testing-library/react";
```

Replace with:

```tsx
import { cleanup, render, screen, within } from "@testing-library/react";
```

`web/tests/MessageList.test.tsx`. Find:

```tsx
  it("your continue line is your own bubble", () => {
    const body = "I cleared the block on shop.example. Read the page again and carry on with: book a table";
    render(<MessageList messages={[makeMessage({ role: "user", kind: "card_answer", body })]} botName="Scout" />);
    expect(screen.getByText(body).closest("li")).toHaveClass("message--user");
  });
});
```

Replace with:

```tsx
  it("your continue line is your own bubble", () => {
    const body = "I cleared the block on shop.example. Read the page again and carry on with: book a table";
    render(<MessageList messages={[makeMessage({ role: "user", kind: "card_answer", body })]} botName="Scout" />);
    expect(screen.getByText(body).closest("li")).toHaveClass("message--user");
  });
});

describe("MessageList while a bot works (redesign P2)", () => {
  const PLACEHOLDER = makeMessage({ id: "r-1", author_bot_id: "bot-1", body: "", seq: 0 });
  const steps = () => within(screen.getByRole("list", { name: "Steps" })).getAllByRole("listitem").map((li) => li.textContent);

  it("shows the bot's robot On it and three dots before any text, never an empty bubble", () => {
    const { container } = render(
      <MessageList messages={[makeMessage({ id: "u", role: "user", body: "plan my week" }), PLACEHOLDER]} botName="Scout" botAvatar={AVATAR} />,
    );
    const typing = screen.getByRole("status", { name: "Scout is on it" });
    expect(typing.querySelectorAll(".working-dots__dot")).toHaveLength(3);
    expect(container.querySelector('[data-message-id="r-1"] svg.avatar')).toHaveAttribute("data-moment", "onit");
    expect(container.querySelector('[data-message-id="r-1"] .message__body')).toBeNull();
  });

  it("shows a caret while the text streams, and none once the reply is in", () => {
    const { container, rerender } = render(
      <MessageList messages={[PLACEHOLDER]} streaming={{ "r-1": "Here is" }} botName="Scout" botAvatar={AVATAR} />,
    );
    expect(screen.queryByRole("status", { name: "Scout is on it" })).toBeNull();
    expect(container.querySelector(".message__body")).toHaveClass("message__body--streaming");
    expect(container.querySelector(".message__body")).toHaveAttribute("aria-busy", "true");
    rerender(<MessageList messages={[{ ...PLACEHOLDER, seq: 2, body: "Here is the plan." }]} botName="Scout" botAvatar={AVATAR} />);
    expect(container.querySelector(".message__body")).not.toHaveClass("message__body--streaming");
  });

  it("lists what the bot did as compact lines: the current step while it works, all past once the reply is in", () => {
    const lines = { "r-1": ["adding a task", "saving a note"] };
    const { rerender } = render(<MessageList messages={[PLACEHOLDER]} toolLines={lines} botName="Scout" botAvatar={AVATAR} />);
    expect(steps()).toEqual(["Added a task", "Saving a note…"]);
    rerender(<MessageList messages={[{ ...PLACEHOLDER, seq: 2, body: "Done." }]} toolLines={lines} botName="Scout" botAvatar={AVATAR} />);
    expect(steps()).toEqual(["Added a task", "Saved a note"]);
  });

  it("shows only the last few steps of a long run, with a count of the earlier ones", () => {
    const lines = { "r-1": ["opening a.example", "reading a.example", "opening b.example", "reading b.example", "opening c.example", "reading c.example", "adding a task"] };
    render(<MessageList messages={[{ ...PLACEHOLDER, seq: 2, body: "Done." }]} toolLines={lines} botName="Scout" botAvatar={AVATAR} />);
    expect(steps()).toEqual(["2 earlier steps", "Opened b.example", "Read b.example", "Opened c.example", "Read c.example", "Added a task"]);
  });
});
```

- [ ] **Step 3: Run them to see them fail**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && cd web && npx vitest run tests/toolLines.test.ts tests/live.test.ts tests/MessageList.test.tsx`
Expected: FAIL.
- `tests/toolLines.test.ts` fails to load: `Failed to resolve import "../src/lib/toolLines"`.
- `tests/live.test.ts`: the 5 new tests fail (`toolLines` is undefined); the rest pass.
- `tests/MessageList.test.tsx`: the 4 new tests fail (no status, no streaming class, no "Steps" list); the rest pass.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && ROOST_DATA_DIR=$(mktemp -d) ROOST_DESKS_DIR=$(mktemp -d) uv run pytest tests/test_tool_lines.py -q`
Expected: FAIL, 2 failed: `FileNotFoundError` for `web/src/lib/toolLines.ts`.

- [ ] **Step 4: The steps, in the live store**

Create `web/src/lib/toolLines.ts`:

```ts
// A bot's step, as the gateway announces it while the bot works ("adding a task", "opening elpais.com"),
// written as a compact line in its reply (redesign P2): "Adding a task…" while it is the current step,
// "Added a task" once done. P4 turns these lines into live record cards.
//
// Every verb the gateway announces has its past tense here: tests/test_tool_lines.py checks it.
const PAST: Readonly<Record<string, string>> = {
  adding: "added", asking: "asked", changing: "changed", checking: "checked", completing: "completed",
  correcting: "corrected", creating: "created", deleting: "deleted", filing: "filed", logging: "logged",
  looking: "looked", making: "made", opening: "opened", reading: "read", saving: "saved", searching: "searched",
  setting: "set", undoing: "undid", updating: "updated", waiting: "waited", writing: "wrote",
};

const capitalised = (text: string): string => text.charAt(0).toUpperCase() + text.slice(1);

export function toolLineText(activity: string, done: boolean): string {
  const text = activity.trim();
  if (!done) return `${capitalised(text)}…`;
  const [verb, ...rest] = text.split(" ");
  const past = PAST[verb.toLowerCase()];
  return capitalised(past ? [past, ...rest].join(" ") : text);
}
```

`web/src/store/live.ts`. Find:

```ts
import type { BotOut, MessageDoneFrame, MessageOut, ServerFrame, StuckCardOut } from "../api/types";
```

Replace with:

```ts
import type { BotOut, BotStatusFrame, MessageDoneFrame, MessageOut, ServerFrame, StuckCardOut } from "../api/types";
```

`web/src/store/live.ts`. Find:

```ts
  readonly stuckCards: Readonly<Record<string, StuckCardOut>>;
}
```

Replace with:

```ts
  readonly stuckCards: Readonly<Record<string, StuckCardOut>>;
  // What each reply's bot did while writing it (redesign P2): the bot_status activities ("adding a task")
  // seen while the reply's placeholder was open, oldest first, keyed by the reply's message id. Live
  // only: a reload starts empty, and P4's stored record cards take over.
  readonly toolLines: Readonly<Record<string, readonly string[]>>;
}
```

`web/src/store/live.ts`. Find:

```ts
    boardVersion: { tasks: 0, money: 0, notes: 0, documents: 0 }, stuckCards: {},
  };
```

Replace with:

```ts
    boardVersion: { tasks: 0, money: 0, notes: 0, documents: 0 }, stuckCards: {}, toolLines: {},
  };
```

`web/src/store/live.ts`. Find:

```ts
type BoardVersion = LiveState["boardVersion"];
```

Replace with:

```ts
// A working bot's new activity joins the trail of the reply it is writing: its open placeholder (seq 0),
// whatever the thread. The same activity twice in a row is one line.
function withToolLine(state: LiveState, frame: BotStatusFrame): LiveState["toolLines"] {
  const activity = frame.activity;
  if (frame.status !== "on_it" || !activity) return state.toolLines;
  const open = Object.values(state.messagesByThread).flat()
    .filter((message) => message.seq === 0 && message.role === "bot" && message.author_bot_id === frame.bot_id);
  return open.reduce((lines, message) => {
    const trail = lines[message.id] ?? [];
    return trail.at(-1) === activity ? lines : { ...lines, [message.id]: [...trail, activity] };
  }, state.toolLines);
}

type BoardVersion = LiveState["boardVersion"];
```

`web/src/store/live.ts`. Find:

```ts
      return {
        ...state,
        cursor: frame.seq,
        bots: updated ? { ...state.bots, [frame.bot_id]: updated } : state.bots,
      };
```

Replace with:

```ts
      return {
        ...state,
        cursor: frame.seq,
        bots: updated ? { ...state.bots, [frame.bot_id]: updated } : state.bots,
        toolLines: withToolLine(state, frame),
      };
```

`web/src/store/live.ts`. Find:

```ts
    case "message_done": {
      return {
        ...state,
        cursor: frame.seq,
        streaming: withoutKey(state.streaming, frame.message_id),
        messagesByThread: { ...state.messagesByThread, [frame.thread_id]: closeMessage(state, frame) },
      };
    }
```

Replace with:

```ts
    case "message_done": {
      const kept = closeMessage(state, frame);
      // A reply closed with nothing stored is gone, and so are its lines.
      const gone = !kept.some((message) => message.id === frame.message_id);
      return {
        ...state,
        cursor: frame.seq,
        streaming: withoutKey(state.streaming, frame.message_id),
        messagesByThread: { ...state.messagesByThread, [frame.thread_id]: kept },
        toolLines: gone ? withoutKey(state.toolLines, frame.message_id) : state.toolLines,
      };
    }
```

- [ ] **Step 5: Dots, lines and the row**

`web/src/components/chat/constants.ts`. Find:

```ts
export const LONG_REPLY_LINES = 4; // so is one with more lines than this
```

Replace with:

```ts
export const LONG_REPLY_LINES = 4; // so is one with more lines than this
export const TOOL_LINES_SHOWN = 5; // a reply lists at most this many of its bot's latest steps
```

Create `web/src/components/chat/TypingDots.tsx`:

```tsx
import { WorkingDots } from "../WorkingIndicator";

// Where a reply will be while its bot is On it and has written nothing yet (redesign P2): three dots,
// beside the bot's robot showing its On it signal (MessageRow).
export function TypingDots({ name }: { name: string }) {
  return (
    <div className="message__typing" role="status" aria-label={`${name} is on it`}>
      <WorkingDots size={6} />
    </div>
  );
}
```

Create `web/src/components/chat/ToolLines.tsx`:

```tsx
import { toolLineText } from "../../lib/toolLines";
import { cx } from "../../ui/cx";
import { CheckIcon } from "../icons";
import { TOOL_LINES_SHOWN } from "./constants";

export interface ToolLinesProps {
  lines: readonly string[]; // the bot's activities for this reply, oldest first (store/live.ts toolLines)
  working: boolean; // the reply is still being written: its last line is the current step
}

// What the bot did for this reply (redesign P2), one compact line per step: the latest few, with a count
// of the earlier ones. Live only; P4 turns them into record cards.
export function ToolLines({ lines, working }: ToolLinesProps) {
  const earlier = Math.max(0, lines.length - TOOL_LINES_SHOWN);
  const shown = lines.slice(earlier);
  return (
    <ul className="tool-lines" aria-label="Steps">
      {earlier > 0 ? <li className="tool-line tool-line--earlier">{`${earlier} earlier ${earlier === 1 ? "step" : "steps"}`}</li> : null}
      {shown.map((activity, index) => {
        const current = working && index === shown.length - 1;
        return (
          <li key={earlier + index} className={cx("tool-line", current && "tool-line--current")}>
            <span className="tool-line__mark" aria-hidden="true">
              {current ? <span className="tool-line__spinner" /> : <CheckIcon />}
            </span>
            {toolLineText(activity, !current)}
          </li>
        );
      })}
    </ul>
  );
}
```

`web/src/components/MessageRow.tsx`. Find:

```tsx
import { MessageActions } from "./chat/MessageActions";
import { PlainText } from "./chat/PlainText";
import { RichText } from "./chat/RichText";
import { isLongReply } from "./chat/replyShape";
```

Replace with:

```tsx
import { MessageActions } from "./chat/MessageActions";
import { PlainText } from "./chat/PlainText";
import { RichText } from "./chat/RichText";
import { ToolLines } from "./chat/ToolLines";
import { TypingDots } from "./chat/TypingDots";
import { isLongReply } from "./chat/replyShape";
```

`web/src/components/MessageRow.tsx`. Find:

```tsx
  // Rooms only: a bot's text message gets a Reply that addresses its author.
  onReply?: (author: BotOut) => void;
}

function authorOf(message: MessageOut, team: readonly BotOut[]): BotOut | undefined {
```

Replace with:

```tsx
  // Rooms only: a bot's text message gets a Reply that addresses its author.
  onReply?: (author: BotOut) => void;
  // What the bot did while writing this reply (store/live.ts toolLines), oldest first.
  toolLines?: readonly string[];
}

const NO_LINES: readonly string[] = [];

function authorOf(message: MessageOut, team: readonly BotOut[]): BotOut | undefined {
```

`web/src/components/MessageRow.tsx`. Find:

```tsx
interface RowBodyProps {
  message: MessageOut;
  kind: string;
  text: string;
  name: string;
  team: readonly BotOut[];
  stuck: Readonly<Record<string, StuckCardOut>>;
}
```

Replace with:

```tsx
interface RowBodyProps {
  message: MessageOut;
  kind: string;
  text: string;
  streaming: boolean;
  name: string;
  team: readonly BotOut[];
  stuck: Readonly<Record<string, StuckCardOut>>;
}
```

`web/src/components/MessageRow.tsx`. Find:

```tsx
function RowBody({ message, kind, text, name, team, stuck }: RowBodyProps) {
```

Replace with:

```tsx
function RowBody({ message, kind, text, streaming, name, team, stuck }: RowBodyProps) {
```

`web/src/components/MessageRow.tsx`. Find:

```tsx
  const rich = message.role === "bot" && kind === "text";
  return (
    <div className="message__body">
      {rich ? <RichText text={text} id={message.id} /> : <PlainText text={text} keyPrefix={message.id} />}
    </div>
  );
}
```

Replace with:

```tsx
  const rich = message.role === "bot" && kind === "text";
  // While the text streams in, a caret follows it (styles/chat.css).
  return (
    <div className={cx("message__body", streaming && "message__body--streaming")} aria-busy={streaming || undefined}>
      {rich ? <RichText text={text} id={message.id} /> : <PlainText text={text} keyPrefix={message.id} />}
    </div>
  );
}
```

`web/src/components/MessageRow.tsx`. Find:

```tsx
export function MessageRow({
  message, runStart, liveText, fallbackName, fallbackAvatar, team, stuck = NO_STUCK, onReply,
}: MessageRowProps) {
```

Replace with:

```tsx
export function MessageRow({
  message, runStart, liveText, fallbackName, fallbackAvatar, team, stuck = NO_STUCK, onReply, toolLines = NO_LINES,
}: MessageRowProps) {
```

`web/src/components/MessageRow.tsx`. Find:

```tsx
  const text = liveText ?? message.body;
  // A reply still being written (seq 0) has nothing to copy yet.
  const settled = message.seq !== 0 && (kind === "text" || kind === "card_answer");
  const card = !isUser && kind === "text" && isLongReply(text);
  return (
    <li className={cx("message", isUser ? "message--user" : "message--bot", runStart && "message--run-start", card && "message--card")}
      data-message-id={message.id}>
      {!isUser && avatar ? (
        <span className="message__avatar">
          {runStart ? <Avatar avatar={avatar} status="resting" size={32} label={false} decorative /> : null}
        </span>
      ) : null}
      <div className="message__content">
        <div className={`message__author${runStart && !isUser ? "" : " sr-only"}`}>{name}</div>
        <RowBody message={message} kind={kind} text={text} name={name} team={team} stuck={stuck} />
        {settled ? <MessageMeta message={message} isUser={isUser} /> : null}
```

Replace with:

```tsx
  const text = liveText ?? message.body;
  // A reply still being written (seq 0): dots until its first words, then a caret; nothing to copy yet.
  const writing = !isUser && message.seq === 0;
  const typing = writing && !text;
  const settled = !writing && (kind === "text" || kind === "card_answer");
  const card = !isUser && kind === "text" && isLongReply(text);
  return (
    <li className={cx("message", isUser ? "message--user" : "message--bot", runStart && "message--run-start", card && "message--card")}
      data-message-id={message.id}>
      {!isUser && avatar ? (
        <span className="message__avatar">
          {runStart || typing ? <Avatar avatar={avatar} status={typing ? "on_it" : "resting"} size={32} label={false} decorative /> : null}
        </span>
      ) : null}
      <div className="message__content">
        <div className={`message__author${runStart && !isUser ? "" : " sr-only"}`}>{name}</div>
        {toolLines.length > 0 ? <ToolLines lines={toolLines} working={writing} /> : null}
        {typing ? <TypingDots name={name} /> : (
          <RowBody message={message} kind={kind} text={text} streaming={writing} name={name} team={team} stuck={stuck} />
        )}
        {settled ? <MessageMeta message={message} isUser={isUser} /> : null}
```

`web/src/components/Avatar.tsx`. Find:

```tsx
  // A moment instead of the status's own (P2's typing indicator shows "think").
```

Replace with:

```tsx
  // A moment instead of the status's own: Thinking, New message or Done. (P2's typing row shows the On it status.)
```

- [ ] **Step 6: The list and the pages pass the steps on**

`web/src/components/MessageList.tsx`. Find:

```tsx
  // Rooms pass this so each bot message offers Reply; Chat does not.
  onReply?: (author: BotOut) => void;
}

const NO_TEAM: readonly BotOut[] = [];
```

Replace with:

```tsx
  // Rooms pass this so each bot message offers Reply; Chat does not.
  onReply?: (author: BotOut) => void;
  // What each reply's bot did while writing it, by message id (store/live.ts toolLines, redesign P2).
  toolLines?: Readonly<Record<string, readonly string[]>>;
}

const NO_TEAM: readonly BotOut[] = [];
const NO_LINES: Readonly<Record<string, readonly string[]>> = {};
```

`web/src/components/MessageList.tsx`. Find:

```tsx
export function MessageList({ messages, streaming = {}, botName, botAvatar, team = NO_TEAM, stuck, onReply }: MessageListProps) {
  const endRef = useRef<HTMLDivElement>(null);
  const streamedLength = Object.values(streaming).reduce((total, text) => total + text.length, 0);

  // Keep the newest message in view as messages arrive and replies stream in.
  useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: "end" });
  }, [messages.length, streamedLength]);
```

Replace with:

```tsx
export function MessageList({
  messages, streaming = {}, botName, botAvatar, team = NO_TEAM, stuck, onReply, toolLines = NO_LINES,
}: MessageListProps) {
  const endRef = useRef<HTMLDivElement>(null);
  const streamedLength = Object.values(streaming).reduce((total, text) => total + text.length, 0);
  const stepCount = Object.values(toolLines).reduce((total, lines) => total + lines.length, 0);

  // Keep the newest message in view as messages arrive, replies stream in and steps are added.
  useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: "end" });
  }, [messages.length, streamedLength, stepCount]);
```

`web/src/components/MessageList.tsx`. Find:

```tsx
              liveText={streaming[item.message.id]}
```

Replace with:

```tsx
              liveText={streaming[item.message.id]}
              toolLines={toolLines[item.message.id]}
```

`web/src/pages/Chat.tsx`. Find:

```tsx
        <MessageList messages={all} streaming={live.streaming} botName={bot.name} botAvatar={bot.avatar}
          team={Object.values(live.bots)} stuck={stuck} />
```

Replace with:

```tsx
        <MessageList messages={all} streaming={live.streaming} botName={bot.name} botAvatar={bot.avatar}
          team={Object.values(live.bots)} stuck={stuck} toolLines={live.toolLines} />
```

`web/src/pages/Room.tsx`. Find:

```tsx
          <MessageList messages={allMessages} streaming={live.streaming} botName="the room" team={liveTeam} onReply={reply} />
```

Replace with:

```tsx
          <MessageList messages={allMessages} streaming={live.streaming} botName="the room" team={liveTeam} onReply={reply}
            toolLines={live.toolLines} />
```

- [ ] **Step 7: The styles**

`web/src/styles/chat.css`. Find:

```css
.message-list__end {
  height: 1px;
}
```

Replace with:

```css
.message-list__end {
  height: 1px;
}

/* ---- While a bot works (redesign P2): dots, the caret, its steps ------ */

.message__typing {
  display: inline-flex;
  align-items: center;
  align-self: flex-start;
  height: 38px;
  padding: 0 var(--space-4);
  border-radius: var(--radius-xs) var(--radius-lg) var(--radius-lg) var(--radius-lg);
  background: var(--color-raised);
  color: var(--color-text-secondary);
}

/* The caret at the end of a reply that is still streaming in. */
.message__body--streaming .message__plain::after,
.message__body--streaming .md > :last-child::after {
  content: "";
  display: inline-block;
  width: 2px;
  height: 1.1em;
  margin-left: 2px;
  vertical-align: text-bottom;
  background: var(--color-accent-strong);
  animation: roost-caret 1s steps(2, start) infinite;
}

.tool-lines {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin: 0 0 var(--space-2);
  padding: 0;
  list-style: none;
}

.tool-line {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  color: var(--color-text-secondary);
  font-size: var(--fs-caption);
  overflow-wrap: anywhere;
}

.tool-line--earlier {
  padding-left: 20px;
  color: var(--color-text-faint);
}

.tool-line__mark {
  display: inline-grid;
  flex: none;
  place-items: center;
  width: 14px;
  height: 14px;
  color: var(--color-ok);
}

.tool-line__mark svg {
  width: 12px;
  height: 12px;
}

.tool-line__spinner {
  width: 10px;
  height: 10px;
  border: 2px solid var(--color-border-strong);
  border-top-color: var(--color-accent-strong);
  border-radius: 50%;
  animation: roost-spin 0.9s linear infinite;
}

@keyframes roost-caret {
  to {
    visibility: hidden;
  }
}

@keyframes roost-spin {
  to {
    transform: rotate(360deg);
  }
}

@media (prefers-reduced-motion: reduce) {
  .message__body--streaming .message__plain::after,
  .message__body--streaming .md > :last-child::after,
  .tool-line__spinner {
    animation: none;
  }
}
```

- [ ] **Step 8: Run the tests to see them pass**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && cd web && npx vitest run tests/toolLines.test.ts tests/live.test.ts tests/MessageList.test.tsx tests/MessageRow.test.tsx tests/Chat.test.tsx tests/ChatThreads.test.tsx tests/Room.test.tsx tests/Home.test.tsx tests/Avatar.test.tsx tests/tokens.test.ts`
Expected: PASS.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && ROOST_DATA_DIR=$(mktemp -d) ROOST_DESKS_DIR=$(mktemp -d) uv run pytest tests/test_tool_lines.py -q`
Expected: PASS, 2 passed.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && cd web && npm test && npm run build && npm run size`
Expected: every vitest file passes; the build succeeds; the entry stays within budget.

- [ ] **Step 9: Commit**

Run:

```bash
cd /Users/blckit/Desktop/Code_Projects/roost && \
git add web/src/lib/toolLines.ts web/src/components/chat/TypingDots.tsx web/src/components/chat/ToolLines.tsx \
  web/src/components/chat/constants.ts web/src/store/live.ts web/src/components/MessageList.tsx \
  web/src/components/MessageRow.tsx web/src/components/Avatar.tsx web/src/pages/Chat.tsx web/src/pages/Room.tsx \
  web/src/styles/chat.css web/tests/toolLines.test.ts web/tests/live.test.ts web/tests/MessageList.test.tsx \
  tests/test_tool_lines.py && \
git commit -m "feat: typing dots and a caret while a bot writes, and its steps as compact lines"
```

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && git status --short`
Expected: none of the files above is listed.

---

### Task 4: The composers grow in every browser, clip no letter, ignore an IME's Enter, and keep the last message in view

Design P2 "Composer", audit finding 6 and Review Focus 3. Today both composers' textareas grow only through CSS `field-sizing: content` (Chromium alone), the chat's box has a pill radius of its own that clips the glyphs under its rounded corners, Enter sends even when an input method uses it to confirm a word, and a growing dock shortens the scroll box under the last message, hiding it.
- **`useAutoGrow`** fits the box to its text after every change with the kit's `fitHeight` (P1's `Textarea`), up to `COMPOSER_MAX_ROWS` (8) lines, then the box scrolls. Both `Composer` and the room's `MentionComposer` use it.
- **`isSendKey`**: Enter without Shift sends, except while `isComposing` or with Safari's IME key code 229.
- **The box** has no radius of its own and 4 px of room at each side (the composer's padding gives back the 4 px), so the first and last letters always show; `field-sizing` and the fixed `max-height` go.
- **`useKeepBottom`** is a callback ref on the chat's and the room's scroll box. A `ResizeObserver` follows the box's height; when it shrinks (the composer grew, a notice appeared), the box scrolls down by as much (`followShrink`), so the last message stays in view. Being a ref, it starts whenever the box appears (after "Loading…") and stops when it goes.
- The + menu and New conversation / Past conversations are unchanged.

**Files:**
- Create: `web/src/hooks/useAutoGrow.ts`, `web/src/hooks/useKeepBottom.ts`, `web/src/lib/composerKeys.ts`, `web/tests/useKeepBottom.test.tsx`
- Modify: `web/src/components/Composer.tsx`, `web/src/components/MentionComposer.tsx`, `web/src/components/chat/constants.ts`, `web/src/pages/Chat.tsx`, `web/src/pages/Room.tsx`, `web/src/styles/chat.css`, `web/tests/Composer.test.tsx`, `web/tests/MentionComposer.test.tsx`
- Test: `web/tests/Composer.test.tsx`, `web/tests/MentionComposer.test.tsx`, `web/tests/useKeepBottom.test.tsx`; the real browser checks are Task 6's `chat.spec.ts`

**Interfaces:**
- Consumes: `fitHeight(box, maxRows)` (`web/src/ui/Textarea.tsx`), `Chat` and `RoomView` as Task 3 left them.
- Produces: `useAutoGrow(box, value, maxRows)`, `isSendKey(event)`, `useKeepBottom()`, `followShrink(box, before)`, `COMPOSER_MAX_ROWS = 8`.

- [ ] **Step 1: Path guard**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && git -C /Users/blckit/Desktop/Code_Projects/roost rev-parse --show-toplevel && git -C /Users/blckit/Desktop/Code_Projects/roost branch --show-current`
Expected: `/Users/blckit/Desktop/Code_Projects/roost` then `night-1`. If either differs, stop.

Then confirm Task 3 has landed and this task has not:

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && test -f web/src/lib/toolLines.ts && test ! -f web/src/hooks/useAutoGrow.ts && grep -c "field-sizing: content" web/src/styles/chat.css`
Expected: `1`. Otherwise stop.

- [ ] **Step 2: Write the failing tests**

Create `web/tests/useKeepBottom.test.tsx`:

```tsx
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { followShrink, useKeepBottom } from "../src/hooks/useKeepBottom";

let resized: (() => void) | null = null;
class FakeResizeObserver {
  constructor(callback: () => void) {
    resized = callback;
  }
  observe() {}
  disconnect() {
    resized = null;
  }
}

function Scroller() {
  return <div ref={useKeepBottom()} data-testid="scroller" />;
}

afterEach(() => { cleanup(); vi.unstubAllGlobals(); resized = null; });

describe("followShrink (redesign P2)", () => {
  it("scrolls down by as much as the box got shorter, and never up when it grew", () => {
    const box = { clientHeight: 480, scrollTop: 1000 };
    expect(followShrink(box, 500)).toBe(480);
    expect(box.scrollTop).toBe(1020);
    box.clientHeight = 520;
    expect(followShrink(box, 480)).toBe(520);
    expect(box.scrollTop).toBe(1020);
  });
});

describe("useKeepBottom (redesign P2)", () => {
  it("follows the scroll box's height while it is on screen, and lets go once it leaves", () => {
    vi.stubGlobal("ResizeObserver", FakeResizeObserver);
    let height = 500;
    vi.spyOn(HTMLElement.prototype, "clientHeight", "get").mockImplementation(() => height);
    const view = render(<Scroller />);
    const scroller = screen.getByTestId("scroller");
    scroller.scrollTop = 1000;
    height = 470; // the composer grew by a line and a half
    resized?.();
    expect(scroller.scrollTop).toBe(1030);
    view.unmount();
    expect(resized).toBeNull();
  });
});
```

`web/tests/Composer.test.tsx`. Find:

```tsx
import { cleanup, render, screen, waitFor } from "@testing-library/react";
```

Replace with:

```tsx
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
```

`web/tests/Composer.test.tsx`. Find:

```tsx
    await waitFor(() => expect(box).toHaveValue(""));
  });
});
```

Replace with:

```tsx
    await waitFor(() => expect(box).toHaveValue(""));
  });

  // Review Focus 3: Japanese, Chinese and Korean input confirm a word with Enter.
  it("never sends on the Enter that confirms an IME candidate", () => {
    const onSend = vi.fn();
    render(<Composer onSend={onSend} />);
    const box = screen.getByRole("textbox");
    fireEvent.change(box, { target: { value: "にほんご" } });
    fireEvent.keyDown(box, { key: "Enter", isComposing: true });
    fireEvent.keyDown(box, { key: "Enter", keyCode: 229 }); // Safari, while the IME holds the key
    expect(onSend).not.toHaveBeenCalled();
    fireEvent.keyDown(box, { key: "Enter" });
    expect(onSend).toHaveBeenCalledWith("にほんご");
  });

  it("grows with its text in any browser, up to eight lines, then scrolls", () => {
    render(<Composer onSend={vi.fn()} />);
    const box = screen.getByRole("textbox") as HTMLTextAreaElement;
    Object.assign(box.style, { lineHeight: "21px", paddingTop: "7px", paddingBottom: "7px" });
    Object.defineProperty(box, "scrollHeight", { configurable: true, get: () => 21 * box.value.split("\n").length + 14 });
    fireEvent.change(box, { target: { value: "one\ntwo\nthree" } });
    expect(box.style.height).toBe("77px");
    expect(box.style.overflowY).toBe("hidden");
    fireEvent.change(box, { target: { value: Array.from({ length: 12 }, (_, line) => `line ${line}`).join("\n") } });
    expect(box.style.height).toBe(`${21 * 8 + 14}px`);
    expect(box.style.overflowY).toBe("auto");
  });
});
```

`web/tests/MentionComposer.test.tsx`. Find:

```tsx
import { cleanup, render, screen } from "@testing-library/react";
```

Replace with:

```tsx
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
```

`web/tests/MentionComposer.test.tsx`. Find:

```tsx
  it("a reply puts the mention in front of the draft and focuses the box", async () => {
```

Replace with:

```tsx
  it("never sends on the Enter that confirms an IME candidate, and grows with its text", () => {
    const { box, onSend } = setup();
    Object.assign(box.style, { lineHeight: "21px", paddingTop: "7px", paddingBottom: "7px" });
    Object.defineProperty(box, "scrollHeight", { configurable: true, get: () => 21 * (box as HTMLTextAreaElement).value.split("\n").length + 14 });
    fireEvent.change(box, { target: { value: "にほんご\nです" } });
    fireEvent.keyDown(box, { key: "Enter", isComposing: true });
    expect(onSend).not.toHaveBeenCalled();
    expect(box.style.height).toBe("56px");
  });

  it("a reply puts the mention in front of the draft and focuses the box", async () => {
```

- [ ] **Step 3: Run them to see them fail**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && cd web && npx vitest run tests/Composer.test.tsx tests/MentionComposer.test.tsx tests/useKeepBottom.test.tsx`
Expected: FAIL.
- `tests/useKeepBottom.test.tsx` fails to load: `Failed to resolve import "../src/hooks/useKeepBottom"`.
- `tests/Composer.test.tsx`: 2 failed (the IME's Enter sends; the box keeps no height of its own), 5 passed.
- `tests/MentionComposer.test.tsx`: 1 failed (the IME's Enter sends), the rest pass.

- [ ] **Step 4: The hooks and the send key**

Create `web/src/hooks/useAutoGrow.ts`:

```ts
import { useLayoutEffect, type RefObject } from "react";
import { fitHeight } from "../ui/Textarea";

// Grows a textarea with its text in every browser (redesign P2): the kit's fitHeight after each change,
// up to maxRows lines, then it scrolls. CSS `field-sizing: content` alone works in Chromium only.
export function useAutoGrow(box: RefObject<HTMLTextAreaElement | null>, value: string, maxRows: number): void {
  useLayoutEffect(() => {
    if (box.current) fitHeight(box.current, maxRows);
  }, [box, value, maxRows]);
}
```

Create `web/src/hooks/useKeepBottom.ts`:

```ts
import { useCallback } from "react";

interface ScrollBox {
  readonly clientHeight: number;
  scrollTop: number;
}

// A scroll box that just changed height: if it got shorter (the composer grew a line, a notice appeared),
// it scrolls down by as much, so what sat at its bottom edge, the last message, stays in view. Returns
// the height to compare with next time.
export function followShrink(box: ScrollBox, before: number): number {
  const shrunk = before - box.clientHeight;
  if (shrunk > 0) box.scrollTop += shrunk;
  return box.clientHeight;
}

// The chat's scroll box keeps its last message in view while the dock below it grows (redesign P2).
// A callback ref, so it follows the box from whenever it appears (after Loading…) until it goes.
export function useKeepBottom(): (element: HTMLElement | null) => void | (() => void) {
  return useCallback((element: HTMLElement | null) => {
    if (!element || typeof ResizeObserver === "undefined") return undefined;
    let height = element.clientHeight;
    const observer = new ResizeObserver(() => {
      height = followShrink(element, height);
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
}
```

Create `web/src/lib/composerKeys.ts`:

```ts
import type { KeyboardEvent } from "react";

// What Safari reports for a key the input method (IME) is still handling.
const IME_KEY_CODE = 229;

// The composers' send key (redesign P2): Enter sends and Shift+Enter is a new line. The Enter that
// confirms a word in Japanese, Chinese or Korean input belongs to the IME and never sends half a message.
export function isSendKey(event: KeyboardEvent<HTMLTextAreaElement>): boolean {
  if (event.key !== "Enter" || event.shiftKey) return false;
  return !(event.nativeEvent.isComposing || event.keyCode === IME_KEY_CODE);
}
```

`web/src/components/chat/constants.ts`. Find:

```ts
export const TOOL_LINES_SHOWN = 5; // a reply lists at most this many of its bot's latest steps
```

Replace with:

```ts
export const TOOL_LINES_SHOWN = 5; // a reply lists at most this many of its bot's latest steps
export const COMPOSER_MAX_ROWS = 8; // the message box grows to this many lines, then scrolls
```

- [ ] **Step 5: The composers**

`web/src/components/Composer.tsx`. Find:

```tsx
import { useState, type KeyboardEvent } from "react";
```

Replace with:

```tsx
import { useRef, useState, type KeyboardEvent } from "react";
import { COMPOSER_MAX_ROWS } from "./chat/constants";
import { useAutoGrow } from "../hooks/useAutoGrow";
import { isSendKey } from "../lib/composerKeys";
```

`web/src/components/Composer.tsx`. Find:

```tsx
// Enter sends, Shift+Enter inserts a newline.
export function Composer({ onSend, placeholder, disabled = false, size = "regular" }: ComposerProps) {
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
```

Replace with:

```tsx
// Enter sends, Shift+Enter inserts a newline (never the Enter an IME uses), and the box grows with its text.
export function Composer({ onSend, placeholder, disabled = false, size = "regular" }: ComposerProps) {
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const boxRef = useRef<HTMLTextAreaElement>(null);
  useAutoGrow(boxRef, text, COMPOSER_MAX_ROWS);
```

`web/src/components/Composer.tsx`. Find:

```tsx
  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      trySend();
    }
  };
```

Replace with:

```tsx
  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (isSendKey(event)) {
      event.preventDefault();
      trySend();
    }
  };
```

`web/src/components/Composer.tsx`. Find:

```tsx
      <textarea
        className="composer__box"
```

Replace with:

```tsx
      <textarea
        ref={boxRef}
        className="composer__box"
```

`web/src/components/MentionComposer.tsx`. Find:

```tsx
} from "react";
```

Replace with:

```tsx
} from "react";
import { COMPOSER_MAX_ROWS } from "./chat/constants";
import { useAutoGrow } from "../hooks/useAutoGrow";
import { isSendKey } from "../lib/composerKeys";
```

`web/src/components/MentionComposer.tsx`. Find:

```tsx
  const { sending, send } = useSender(onSend, () => edit("", 0));
```

Replace with:

```tsx
  const { sending, send } = useSender(onSend, () => edit("", 0));
  useAutoGrow(boxRef, text, COMPOSER_MAX_ROWS);
```

`web/src/components/MentionComposer.tsx`. Find:

```tsx
    if (open && handleListKey(event, keys)) return;
    if (event.key === "Enter" && !event.shiftKey) {
```

Replace with:

```tsx
    if (open && handleListKey(event, keys)) return;
    if (isSendKey(event)) {
```

- [ ] **Step 6: The pages keep the last message in view**

`web/src/pages/Chat.tsx`. Find:

```tsx
import { useNewConversation } from "../hooks/useNewConversation";
```

Replace with:

```tsx
import { useKeepBottom } from "../hooks/useKeepBottom";
import { useNewConversation } from "../hooks/useNewConversation";
```

`web/src/pages/Chat.tsx`. Find:

```tsx
  const openStuck = useOpenStuck(setNotice);
```

Replace with:

```tsx
  const openStuck = useOpenStuck(setNotice);
  const keepBottom = useKeepBottom();
```

`web/src/pages/Chat.tsx`. Find:

```tsx
      <div className="chat-page__scroll">
        <MessageList messages={all} streaming={live.streaming} botName={bot.name} botAvatar={bot.avatar}
```

Replace with:

```tsx
      <div className="chat-page__scroll" ref={keepBottom}>
        <MessageList messages={all} streaming={live.streaming} botName={bot.name} botAvatar={bot.avatar}
```

`web/src/pages/Room.tsx`. Find:

```tsx
import { useLiveState } from "../hooks/useLiveStore";
```

Replace with:

```tsx
import { useKeepBottom } from "../hooks/useKeepBottom";
import { useLiveState } from "../hooks/useLiveStore";
```

`web/src/pages/Room.tsx`. Find:

```tsx
  const live = useLiveState();

  if (error) return <ErrorNotice message={error} onRetry={load} />;
```

Replace with:

```tsx
  const live = useLiveState();
  const keepBottom = useKeepBottom();

  if (error) return <ErrorNotice message={error} onRetry={load} />;
```

`web/src/pages/Room.tsx`. Find:

```tsx
      <div className="chat-page__scroll">
        {allMessages.length === 0 ? (
```

Replace with:

```tsx
      <div className="chat-page__scroll" ref={keepBottom}>
        {allMessages.length === 0 ? (
```

- [ ] **Step 7: The box's styles**

`web/src/styles/chat.css`. Find:

```css
.composer {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  padding: 7px 7px 7px 18px;
```

Replace with:

```css
.composer {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  padding: 7px 7px 7px 14px;
```

`web/src/styles/chat.css`. Find:

```css
.composer__box {
  flex: 1;
  min-width: 0;
  min-height: 24px;
  max-height: 200px;
  padding: 7px 0;
  border: none;
  background: transparent;
  color: var(--color-text);
  font: inherit;
  line-height: 1.5;
  resize: none;
  field-sizing: content;
}
```

Replace with:

```css
/* The box grows with its text in every browser (hooks/useAutoGrow: up to COMPOSER_MAX_ROWS lines, then
   it scrolls). It has no rounded corners of its own and a little room at each side, so no letter is
   ever clipped (audit finding 6). */
.composer__box {
  flex: 1;
  min-width: 0;
  min-height: 24px;
  padding: 7px var(--space-1);
  border: none;
  border-radius: 0;
  background: transparent;
  color: var(--color-text);
  font: inherit;
  line-height: 1.5;
  resize: none;
  overflow-y: hidden;
}
```

`web/src/styles/chat.css`. Find:

```css
.chat-composer > .composer {
  flex: 1;
  min-width: 0;
  padding: 2px 3px 2px 18px;
  border-radius: 22px;
}

.chat-composer .composer__box {
  border-radius: var(--radius-pill);
}
```

Replace with:

```css
.chat-composer > .composer {
  flex: 1;
  min-width: 0;
  padding: 2px 3px 2px 14px;
  border-radius: 22px;
}
```

- [ ] **Step 8: Run the tests to see them pass**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && cd web && npx vitest run tests/Composer.test.tsx tests/MentionComposer.test.tsx tests/useKeepBottom.test.tsx tests/Chat.test.tsx tests/ChatThreads.test.tsx tests/Room.test.tsx tests/tokens.test.ts`
Expected: PASS: `Composer` 7, `MentionComposer` 9, `useKeepBottom` 2, and the pages as before.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && cd web && npm test && npm run build && npm run size`
Expected: every vitest file passes; the build succeeds (the callback ref's cleanup type-checks on React 19); the entry stays within budget.

- [ ] **Step 9: Commit**

Run:

```bash
cd /Users/blckit/Desktop/Code_Projects/roost && \
git add web/src/hooks/useAutoGrow.ts web/src/hooks/useKeepBottom.ts web/src/lib/composerKeys.ts \
  web/src/components/Composer.tsx web/src/components/MentionComposer.tsx web/src/components/chat/constants.ts \
  web/src/pages/Chat.tsx web/src/pages/Room.tsx web/src/styles/chat.css web/tests/Composer.test.tsx \
  web/tests/MentionComposer.test.tsx web/tests/useKeepBottom.test.tsx && \
git commit -m "fix: the composers grow in every browser, clip no letter, ignore an IME's Enter and keep the last message in view"
```

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && git status --short`
Expected: none of the files above is listed.

---

### Task 5: Home: the main bot first with its star, a soft active row, unread dots and plain previews

Design P2 "Sidebar" and "chat-list previews strip markdown", and Review Focus 5. Today Home draws the main bot as a 120 px hero above the list (`MainBotHero`), the open row has an outlined fill, nothing marks a chat with new messages, and a preview is the reply's markdown flattened to one line ("## Plan **Done.** see [[Garden plan]]").
- **The hero goes.** `ChatList` puts the main bot's row first (`mainFirst`); the rest stay newest first, as the gateway sends them. The row wears the robot's star (it already did) and says ", your main bot" to screen readers. Search finds it like any other chat.
- **The open row** (NavLink's `active`, `aria-current="page"`) gets a soft accent fill, no outline.
- **Unread dots.** `useUnread` reads the open chat from the route and keeps, in this browser's localStorage, the time of the newest message seen in each chat (`lib/unread.ts`). A chat seen for the first time counts as read; a newer message that is not yours puts a dot on its row until you open it. Refused storage, a broken value, or a full quota leave no dots and never an error; each is logged.
- **Plain previews.** `plainText` drops what a flattened reply carries (headings, emphasis, inline code, link targets, `[[Target|Label]]` brackets, a table's rule and cell walls, a leading quote mark) and leaves sums, ranges and snake_case alone. The chat list shows and searches it; a browser notification's text uses it too.
- **Status signals** on the list's robots were drawn by P1 (each row passes its bot's status); a test pins it. The room's "#" glyph leaves the mono stack, and `chatLook.test.ts` now covers `home.css`.
- `web/tests/setup.ts` gives every test a working localStorage: Node 25 puts its own, method-less one on the global and hides jsdom's.
- `web/e2e/main-bot.spec.ts` checks the first row instead of the hero.

**Files:**
- Create: `web/src/lib/plainText.ts`, `web/src/lib/unread.ts`, `web/src/hooks/useUnread.ts`, `web/tests/plainText.test.ts`, `web/tests/unread.test.ts`
- Modify: `web/src/components/ChatList.tsx`, `web/src/pages/Home.tsx`, `web/src/lib/attention.ts`, `web/src/styles/home.css`, `web/tests/ChatList.test.tsx`, `web/tests/Home.test.tsx`, `web/tests/attention.test.ts`, `web/tests/chatLook.test.ts`, `web/tests/setup.ts`, `web/e2e/main-bot.spec.ts`
- Test: the two new files and the five modified test files

**Interfaces:**
- Consumes: `plainSnippet` and `mapWikilinks` (`web/src/components/notes/noteHelpers.ts`), `wikilinkLabel`, `cx`, `ChatRowOut` and `BotOut` (`web/src/api/types.ts`), `useMatch` (react-router-dom).
- Produces: `plainText(markdown)`; `SeenTimes`, `SeenStorage`, `SEEN_STORAGE_KEY`, `readSeen`, `writeSeen`, `markSeen`, `unreadChats`; `useUnread(rows)`; `ChatList`'s `unread` prop and `mainFirst(rows, bots)`.

- [ ] **Step 1: Path guard**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && git -C /Users/blckit/Desktop/Code_Projects/roost rev-parse --show-toplevel && git -C /Users/blckit/Desktop/Code_Projects/roost branch --show-current`
Expected: `/Users/blckit/Desktop/Code_Projects/roost` then `night-1`. If either differs, stop.

Then confirm Task 4 has landed and this task has not:

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && test -f web/src/hooks/useAutoGrow.ts && test ! -f web/src/lib/unread.ts && grep -c "function MainBotHero" web/src/pages/Home.tsx`
Expected: `1`. Otherwise stop.

- [ ] **Step 2: Write the failing tests**

Create `web/tests/plainText.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { plainText } from "../src/lib/plainText";

describe("plainText (redesign P2)", () => {
  it("drops the marks a flattened reply carries and keeps its words", () => {
    expect(plainText("## Plan **Done.** See [the docs](https://docs.example/x) and [[Garden plan|my garden]]."))
      .toBe("Plan Done. See the docs and my garden.");
    expect(plainText("Use `npm run build` and *really* check ~~old~~ _new_ steps"))
      .toBe("Use npm run build and really check old new steps");
    expect(plainText("> Quoted: | Day | Task | |---|:---:| | Mon | Dentist |")).toBe("Quoted: Day Task Mon Dentist");
    expect(plainText("## Week\n\n| Day | Task |\n| --- | --- |\n| Mon | Dentist |")).toBe("Week Day Task Mon Dentist");
  });

  it("leaves plain words alone: sums, snake_case, ranges and a lone star", () => {
    expect(plainText("2 * 3 = 6, snake_case_name, 3 - 4 EUR, rated 5 *")).toBe("2 * 3 = 6, snake_case_name, 3 - 4 EUR, rated 5 *");
  });
});
```

Create `web/tests/unread.test.ts`:

```ts
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ChatRowOut } from "../src/api/types";
import { markSeen, readSeen, SEEN_STORAGE_KEY, unreadChats, writeSeen } from "../src/lib/unread";

const row = (id: string, last_at: string, from_you = false): ChatRowOut => ({
  kind: "bot", id, name: id, thread_id: null, preview: "hi", preview_kind: "text", from_you, last_at, tainted: false,
});

afterEach(() => { vi.restoreAllMocks(); localStorage.clear(); });

describe("unread chats (redesign P2)", () => {
  it("counts a chat seen for the first time as read, then dots it when a newer message comes", () => {
    const first = markSeen([row("a", "2026-10-14T10:00:00Z")], {}, null);
    expect(first).toEqual({ a: "2026-10-14T10:00:00Z" });
    const rows = [row("a", "2026-10-14T11:00:00Z")];
    expect(markSeen(rows, first, null)).toBe(first); // nothing new to remember
    expect([...unreadChats(rows, first, null)]).toEqual(["a"]);
  });

  it("never dots the chat you have open, nor one whose newest message is yours", () => {
    const seen = { a: "2026-10-14T10:00:00Z", b: "2026-10-14T10:00:00Z" };
    const rows = [row("a", "2026-10-14T11:00:00Z"), row("b", "2026-10-14T11:00:00Z", true)];
    expect([...unreadChats(rows, seen, "a")]).toEqual([]);
    expect(markSeen(rows, seen, "a")).toEqual({ a: "2026-10-14T11:00:00Z", b: "2026-10-14T11:00:00Z" });
  });

  it("remembers what you saw in this browser", () => {
    writeSeen({ a: "2026-10-14T10:00:00Z" });
    expect(readSeen()).toEqual({ a: "2026-10-14T10:00:00Z" });
  });

  // Review Focus 5: a private window, blocked site data, or a value another version left behind.
  it("starts fresh and never breaks when the browser refuses storage or holds garbage", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    localStorage.setItem(SEEN_STORAGE_KEY, "{not json");
    expect(readSeen()).toEqual({});
    localStorage.setItem(SEEN_STORAGE_KEY, JSON.stringify({ a: 42 }));
    expect(readSeen()).toEqual({});
    const refusing = {
      getItem: () => { throw new DOMException("denied", "SecurityError"); },
      setItem: () => { throw new DOMException("full", "QuotaExceededError"); },
    };
    expect(readSeen(refusing)).toEqual({});
    expect(() => writeSeen({ a: "2026-10-14T10:00:00Z" }, refusing)).not.toThrow();
    vi.spyOn(window, "localStorage", "get").mockImplementation(() => { throw new DOMException("denied", "SecurityError"); });
    expect(readSeen()).toEqual({});
    expect(() => writeSeen({ a: "2026-10-14T10:00:00Z" })).not.toThrow();
    expect(warn).toHaveBeenCalled();
  });
});
```

`web/tests/setup.ts`. Find:

```ts
  globalThis.ResizeObserver ??= class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
}
```

Replace with:

```ts
  globalThis.ResizeObserver ??= class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
}

// Node 25 puts its own localStorage on the global, and it has no methods unless node runs with a valid
// --localstorage-file; it also hides jsdom's. Give every test a working, empty one (redesign P2's unread
// dots), as a getter so a test can still make it throw.
if (typeof window !== "undefined" && typeof window.localStorage?.getItem !== "function") {
  class MemoryStorage {
    private readonly items = new Map<string, string>();
    get length(): number { return this.items.size; }
    clear(): void { this.items.clear(); }
    getItem(key: string): string | null { return this.items.get(key) ?? null; }
    key(index: number): string | null { return [...this.items.keys()][index] ?? null; }
    removeItem(key: string): void { this.items.delete(key); }
    setItem(key: string, value: string): void { this.items.set(key, String(value)); }
  }
  const storage = new MemoryStorage() as unknown as Storage;
  Object.defineProperty(globalThis, "localStorage", { configurable: true, get: () => storage });
}
```

`web/tests/attention.test.ts`. Find:

```ts
  it("the empty placeholder, a card, your own message or a switched-off bot never do", () => {
```

Replace with:

```ts
  it("says a reply in plain words, without its markdown", () => {
    const frame = message({ body: "## Done\n\n**Booked** [the table](https://x.example/t) for [[Saturday]]." });
    expect(attentionFor(frame, { "bot-1": SCOUT })?.body).toBe("Done Booked the table for Saturday.");
  });

  it("the empty placeholder, a card, your own message or a switched-off bot never do", () => {
```

`web/tests/chatLook.test.ts`. Find:

```ts
const CHAT_STYLESHEETS = ["chat.css", "team.css", "rooms.css", "markdown.css"];
```

Replace with:

```ts
const CHAT_STYLESHEETS = ["chat.css", "team.css", "rooms.css", "markdown.css", "home.css"];
```

`web/tests/ChatList.test.tsx`. Find:

```tsx
import { cleanup, render, screen } from "@testing-library/react";
```

Replace with:

```tsx
import { cleanup, render, screen, within } from "@testing-library/react";
```

`web/tests/ChatList.test.tsx`. Find:

```tsx
function renderList(props: Partial<Parameters<typeof ChatList>[0]> = {}) {
  return render(
    <MemoryRouter>
      <ChatList rows={ROWS} bots={BOTS} query="" attention={new Set()} now={NOW} {...props} />
    </MemoryRouter>,
  );
}
```

Replace with:

```tsx
function renderList(props: Partial<Parameters<typeof ChatList>[0]> = {}, path = "/") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <ChatList rows={ROWS} bots={BOTS} query="" attention={new Set()} now={NOW} {...props} />
    </MemoryRouter>,
  );
}
```

`web/tests/ChatList.test.tsx`. Find:

```tsx
  it("your own last message reads You:, and a bot that needs you is highlighted", () => {
    renderList({ rows: [{ ...ROWS[0], from_you: true, preview: "hello" }], attention: new Set(["bot-1"]) });
    expect(screen.getByText("You: hello")).toBeInTheDocument();
    expect(screen.getByRole("listitem")).toHaveClass("chat-row--attention");
  });
});
```

Replace with:

```tsx
  it("your own last message reads You:, and a bot that needs you is highlighted", () => {
    renderList({ rows: [{ ...ROWS[0], from_you: true, preview: "hello" }], attention: new Set(["bot-1"]) });
    expect(screen.getByText("You: hello")).toBeInTheDocument();
    expect(screen.getByRole("listitem")).toHaveClass("chat-row--attention");
  });
});

describe("ChatList (redesign P2)", () => {
  const CHIEF = makeBot({ id: "bot-9", name: "Chief", is_primary: true });
  const WITH_CHIEF: ChatRowOut[] = [...ROWS, { kind: "bot", id: "bot-9", name: "Chief", thread_id: null, preview: null,
    preview_kind: null, from_you: false, last_at: "2026-10-01T10:00:00Z", tainted: false }];

  it("puts the main bot first, wearing its star, then every other chat newest first", () => {
    renderList({ rows: WITH_CHIEF, bots: { ...BOTS, "bot-9": CHIEF } });
    const links = screen.getAllByRole("link");
    expect(links.map((link) => link.getAttribute("href"))).toEqual(["/bots/bot-9", "/bots/bot-1", "/rooms/room-1", "/bots/bot-2"]);
    expect(links[0]).toHaveAccessibleName(/^Chief ?, your main bot/);
    expect(links[0].querySelector(".robot__star")).not.toBeNull();
    expect(links[1].querySelector(".robot__star")).toBeNull();
  });

  it("shows a preview as plain words, never the reply's markdown", () => {
    renderList({ rows: [{ ...ROWS[0], preview: "**Booked** [the table](https://x.example/t) for [[Saturday]]." }] });
    expect(screen.getByText("Booked the table for Saturday.")).toBeInTheDocument();
  });

  it("dots a chat with a message you have not seen", () => {
    renderList({ unread: new Set(["bot-1"]) });
    expect(within(screen.getByRole("link", { name: /^Scout\b/ })).getByText("Unread")).toBeInTheDocument();
    expect(screen.getAllByText("Unread")).toHaveLength(1);
  });

  it("marks the open chat's row, and each robot's screen shows its bot's status", () => {
    const busy = makeBot({ id: "bot-1", name: "Scout", status: "on_it", activity: "opening elpais.com" });
    renderList({ bots: { ...BOTS, "bot-1": busy } }, "/bots/bot-2");
    expect(screen.getByRole("link", { name: /^Ledger\b/ })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: /^Scout\b/ }).querySelector("svg.avatar")).toHaveAttribute("data-moment", "onit");
    expect(screen.getByRole("link", { name: /^Ledger\b/ }).querySelector("svg.avatar")).toHaveAttribute("data-moment", "rest");
  });
});
```

(The accessible-name pattern allows the space jsdom puts between the name and the hidden text; Chrome reads "Chief, your main bot".)

`web/tests/Home.test.tsx`. Find:

```tsx
beforeEach(() => {
  liveState = initialLiveState();
```

Replace with:

```tsx
beforeEach(() => {
  localStorage.clear();
  liveState = initialLiveState();
```

`web/tests/Home.test.tsx`. Find:

```tsx
  it("pins the main bot big, with its star, linking to its chat", async () => {
    renderHome();
    const hero = await screen.findByRole("link", { name: "Chief, your main bot" });
    expect(hero).toHaveAttribute("href", "/bots/bot-9");
    expect(screen.getByRole("list", { name: "Chats" })).toBeInTheDocument();
  });
```

Replace with:

```tsx
  it("puts the main bot first in the list, wearing its star, with no hero above it", async () => {
    const { container } = renderHome();
    const chats = await screen.findByRole("list", { name: "Chats" });
    const first = within(chats).getAllByRole("link")[0];
    expect(first).toHaveAttribute("href", "/bots/bot-9");
    expect(first).toHaveAccessibleName(/^Chief ?, your main bot/);
    expect(first.querySelector(".robot__star")).not.toBeNull();
    expect(container.querySelector(".main-bot")).toBeNull();
  });
```

`web/tests/Home.test.tsx`. Find:

```tsx
  it("the main bot steps aside while you search, so the results sit at the top", async () => {
    renderHome();
    await screen.findByRole("link", { name: "Chief, your main bot" });
    await userEvent.click(screen.getByRole("button", { name: "Search" }));
    await userEvent.type(screen.getByRole("textbox", { name: "Search chats" }), "chief");
    expect(screen.queryByRole("link", { name: "Chief, your main bot" })).not.toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /Chief/ })).toHaveLength(1);
  });
```

Replace with:

```tsx
  it("search finds the main bot like any other chat", async () => {
    renderHome();
    const chats = await screen.findByRole("list", { name: "Chats" });
    await userEvent.click(screen.getByRole("button", { name: "Search" }));
    await userEvent.type(screen.getByRole("textbox", { name: "Search chats" }), "chief");
    expect(within(chats).getAllByRole("link").map((link) => link.getAttribute("href"))).toEqual(["/bots/bot-9"]);
  });

  it("dots a chat with a message you have not seen, and clears it once you open that chat", async () => {
    localStorage.setItem("roost.chat-seen.v1", JSON.stringify({ "bot-1": "2026-10-14T10:00:00Z", "bot-9": "2026-10-01T10:00:00Z" }));
    renderHome();
    const chats = await screen.findByRole("list", { name: "Chats" });
    expect(within(within(chats).getByRole("link", { name: /^Scout\b/ })).getByText("Unread")).toBeInTheDocument();
    expect(within(within(chats).getByRole("link", { name: /^Chief\b/ })).queryByText("Unread")).toBeNull();
    cleanup();
    render(<MemoryRouter initialEntries={["/bots/bot-1"]}><Home /></MemoryRouter>);
    const open = await screen.findByRole("link", { name: /^Scout\b/ });
    expect(within(open).queryByText("Unread")).toBeNull();
    await waitFor(() => expect(JSON.parse(localStorage.getItem("roost.chat-seen.v1") ?? "{}")["bot-1"]).toBe("2026-10-14T12:19:00Z"));
  });
```

`web/tests/Home.test.tsx`. Find:

```tsx
  it("steps aside while you search, like the main bot", async () => {
```

Replace with:

```tsx
  it("steps aside while you search", async () => {
```

`web/tests/Home.test.tsx`. Find:

```tsx
    expect(screen.getByRole("link", { name: "Chief, your main bot" })).toBeInTheDocument();
```

Replace with:

```tsx
    expect(screen.getByRole("link", { name: /^Chief ?, your main bot/ })).toBeInTheDocument();
```

`web/e2e/main-bot.spec.ts`. Find:

```ts
  await signIn(page);
  await expect(page.getByRole("link", { name: "Chief, your main bot" })).toBeVisible();
  await openChat(page, "Chief");
```

Replace with:

```ts
  await signIn(page);
  // Redesign P2: no hero above the list; the main bot is the first chat, wearing its star.
  const first = page.getByRole("list", { name: "Chats" }).getByRole("link").first();
  await expect(first).toHaveAccessibleName(/^Chief ?, your main bot/);
  await expect(first.locator(".robot__star")).toBeVisible();
  await openChat(page, "Chief");
```

- [ ] **Step 3: Run them to see them fail**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && cd web && npx vitest run tests/plainText.test.ts tests/unread.test.ts tests/attention.test.ts tests/chatLook.test.ts tests/ChatList.test.tsx tests/Home.test.tsx`
Expected: FAIL.
- `tests/plainText.test.ts` and `tests/unread.test.ts` fail to load (`Failed to resolve import`).
- `tests/attention.test.ts`: 1 failed (the body keeps its markdown).
- `tests/chatLook.test.ts`: 1 failed (`home.css: .chat-row__room` is mono).
- `tests/ChatList.test.tsx`: 3 failed (main bot first, plain preview, the dot); the status and active-row test passes already (P1).
- `tests/Home.test.tsx`: 2 failed (the hero is still there; no dot); the rest pass.

- [ ] **Step 4: Plain words and the unread record**

Create `web/src/lib/plainText.ts`:

```ts
import { mapWikilinks, plainSnippet } from "../components/notes/noteHelpers";
import { wikilinkLabel } from "../components/notes/wikilink";

// A table's rule row ("|---|:---:|") and its cell walls.
const TABLE_RULE = /\|?(?:\s*:?-{3,}:?\s*\|)+(?:\s*:?-{3,}:?\s*)?/g;
const CELL_WALL = /\s*\|\s*/g;
// A quote mark at the very start.
const QUOTE_MARK = /^>\s+/;
// *word* or _word_ between spaces or punctuation; "2 * 3" and snake_case stay as they are.
const EMPHASIS = /(^|[\s(])[*_]([^*_\s](?:[^*_]*[^*_\s])?)[*_](?=[\s).,!?:;]|$)/g;

// A message as one line of plain words (redesign P2), for the chat list's previews and a notification's
// text: a reply's markdown, which the server only flattens to one line, would show its marks, link
// targets and table rules. Builds on the notes list's plainSnippet. [[Target|Label]] goes first: its
// bar is not a table's.
export function plainText(markdown: string): string {
  const words = mapWikilinks(markdown, wikilinkLabel).replace(TABLE_RULE, " ").replace(CELL_WALL, " ");
  return plainSnippet(words).replace(QUOTE_MARK, "").replace(EMPHASIS, "$1$2");
}
```

Create `web/src/lib/unread.ts`:

```ts
import type { ChatRowOut } from "../api/types";

// Unread dots on the chat list (redesign P2). For each chat, the time of the newest message you have
// seen. A row whose newest message is later, and not yours, has a dot until you open it. A chat seen for
// the first time counts as read, so a new browser starts with no dots. Kept in this browser only.
export type SeenTimes = Readonly<Record<string, string>>;
export type SeenStorage = Pick<Storage, "getItem" | "setItem">;

export const SEEN_STORAGE_KEY = "roost.chat-seen.v1";

const isSeenTimes = (value: unknown): value is SeenTimes =>
  typeof value === "object" && value !== null && !Array.isArray(value)
  && Object.values(value).every((time) => typeof time === "string");

const later = (time: string, than: string | undefined): boolean => than !== undefined && Date.parse(time) > Date.parse(than);

// The browser's storage; none when reading it throws (Safari with site data blocked).
function browserStorage(): SeenStorage | undefined {
  try {
    return window.localStorage;
  } catch (error) {
    console.warn("This browser keeps no site data here: unread dots last until the page reloads.", error);
    return undefined;
  }
}

// What this browser remembers. Nothing, never an error, when storage is refused or holds something else.
export function readSeen(storage: SeenStorage | undefined = browserStorage()): SeenTimes {
  try {
    const parsed: unknown = JSON.parse(storage?.getItem(SEEN_STORAGE_KEY) ?? "{}");
    return isSeenTimes(parsed) ? parsed : {};
  } catch (error) {
    console.warn("Could not read the chats you have seen; starting with none unread.", error);
    return {};
  }
}

export function writeSeen(seen: SeenTimes, storage: SeenStorage | undefined = browserStorage()): void {
  try {
    storage?.setItem(SEEN_STORAGE_KEY, JSON.stringify(seen));
  } catch (error) {
    console.warn("Could not remember the chats you have seen.", error);
  }
}

// The seen times after a look at the list: a chat seen for the first time counts as read, and the open
// chat, or one whose newest message is yours, is read up to its newest message. The same object when
// nothing changed, so a caller can tell.
export function markSeen(rows: readonly ChatRowOut[], seen: SeenTimes, openId: string | null): SeenTimes {
  const updates = rows.filter((row) => !(row.id in seen) || ((row.id === openId || row.from_you) && later(row.last_at, seen[row.id])));
  return updates.length === 0 ? seen : { ...seen, ...Object.fromEntries(updates.map((row) => [row.id, row.last_at])) };
}

// The chats with a newer message than the one you saw, and not yours. The open chat never has a dot.
export function unreadChats(rows: readonly ChatRowOut[], seen: SeenTimes, openId: string | null): ReadonlySet<string> {
  return new Set(rows
    .filter((row) => row.id !== openId && !row.from_you && later(row.last_at, seen[row.id]))
    .map((row) => row.id));
}
```

Create `web/src/hooks/useUnread.ts`:

```ts
import { useEffect, useMemo, useState } from "react";
import { useMatch } from "react-router-dom";
import type { ChatRowOut } from "../api/types";
import { markSeen, readSeen, unreadChats, writeSeen, type SeenTimes } from "../lib/unread";

// The chat on screen: a bot's chat or a room, by its id.
function useOpenChatId(): string | null {
  const bot = useMatch("/bots/:botId")?.params.botId;
  const room = useMatch("/rooms/:roomId")?.params.roomId;
  return bot ?? room ?? null;
}

// The chats with a message you have not seen (redesign P2), remembered in this browser (lib/unread.ts).
export function useUnread(rows: readonly ChatRowOut[]): ReadonlySet<string> {
  const openId = useOpenChatId();
  const [seen, setSeen] = useState<SeenTimes>(() => readSeen());
  useEffect(() => {
    const next = markSeen(rows, seen, openId);
    if (next === seen) return;
    setSeen(next);
    writeSeen(next);
  }, [rows, seen, openId]);
  return useMemo(() => unreadChats(rows, seen, openId), [rows, seen, openId]);
}
```

`web/src/lib/attention.ts`. Find:

```ts
import type { BotOut, ServerFrame } from "../api/types";
```

Replace with:

```ts
import type { BotOut, ServerFrame } from "../api/types";
import { plainText } from "./plainText";
```

`web/src/lib/attention.ts`. Find:

```ts
    return { botId: bot.id, title: `${bot.name} replied`, body: oneLine(message.body) };
```

Replace with:

```ts
    return { botId: bot.id, title: `${bot.name} replied`, body: oneLine(plainText(message.body)) };
```

- [ ] **Step 5: The list and Home**

`web/src/components/ChatList.tsx`. Find:

```tsx
import { formatChatTime } from "../lib/chatTime";
import { clearAttention } from "../lib/attention";
import type { BotOut, BotStatus, ChatRowOut } from "../api/types";
```

Replace with:

```tsx
import { formatChatTime } from "../lib/chatTime";
import { clearAttention } from "../lib/attention";
import { plainText } from "../lib/plainText";
import { cx } from "../ui/cx";
import type { BotOut, BotStatus, ChatRowOut } from "../api/types";
```

`web/src/components/ChatList.tsx`. Find:

```tsx
  attention: ReadonlySet<string>;
  now?: Date;
}

export function filterChats(rows: readonly ChatRowOut[], query: string): ChatRowOut[] {
  const wanted = query.trim().toLowerCase();
  if (!wanted) return [...rows];
  return rows.filter((row) => row.name.toLowerCase().includes(wanted) || (row.preview ?? "").toLowerCase().includes(wanted));
}
```

Replace with:

```tsx
  attention: ReadonlySet<string>;
  // Chats with a message you have not seen (hooks/useUnread): each gets a dot.
  unread?: ReadonlySet<string>;
  now?: Date;
}

const NOTHING_UNREAD: ReadonlySet<string> = new Set();

export function filterChats(rows: readonly ChatRowOut[], query: string): ChatRowOut[] {
  const wanted = query.trim().toLowerCase();
  if (!wanted) return [...rows];
  return rows.filter((row) => row.name.toLowerCase().includes(wanted) || plainText(row.preview ?? "").toLowerCase().includes(wanted));
}

// The main bot sits first, wearing its star (redesign P2: no hero above the list); the rest stay newest first.
export function mainFirst(rows: readonly ChatRowOut[], bots: Readonly<Record<string, BotOut>>): ChatRowOut[] {
  const isMain = (row: ChatRowOut) => row.kind === "bot" && bots[row.id]?.is_primary === true;
  return [...rows.filter(isMain), ...rows.filter((row) => !isMain(row))];
}
```

`web/src/components/ChatList.tsx`. Find:

```tsx
  const mark = row.preview_kind ? KIND_MARK[row.preview_kind] ?? "" : "";
  return <span className="chat-row__preview">{mark}{row.from_you ? `You: ${row.preview}` : row.preview}</span>;
}

function ChatRow({ row, bot, highlighted, now }: { row: ChatRowOut; bot?: BotOut; highlighted: boolean; now?: Date }) {
  const href = row.kind === "bot" ? `/bots/${row.id}` : `/rooms/${row.id}`;
  return (
    <li className={`chat-row${highlighted ? " chat-row--attention" : ""}`}>
      <NavLink to={href} className="chat-row__link" onClick={() => clearAttention(row.id)}>
        {bot ? (
          <Avatar avatar={bot.avatar} status={bot.status} size={44} label={false} decorative star={bot.is_primary} />
        ) : (
          <span className="chat-row__room" aria-hidden="true">#</span>
        )}
        <span className="chat-row__text">
          <span className="chat-row__top">
            <span className="chat-row__name">{row.name}</span>
            <time className="chat-row__time" dateTime={row.last_at}>{formatChatTime(row.last_at, now)}</time>
          </span>
          {bot && BUSY.has(bot.status) ? <StatusLine bot={bot} /> : <Preview row={row} />}
        </span>
      </NavLink>
    </li>
  );
}
```

Replace with:

```tsx
  const mark = row.preview_kind ? KIND_MARK[row.preview_kind] ?? "" : "";
  const words = plainText(row.preview);
  return <span className="chat-row__preview">{mark}{row.from_you ? `You: ${words}` : words}</span>;
}

interface ChatRowProps {
  row: ChatRowOut;
  bot?: BotOut;
  highlighted: boolean;
  unread: boolean;
  now?: Date;
}

// The active row (NavLink's aria-current="page") has a soft fill; its robot's screen shows the status.
function ChatRow({ row, bot, highlighted, unread, now }: ChatRowProps) {
  const href = row.kind === "bot" ? `/bots/${row.id}` : `/rooms/${row.id}`;
  return (
    <li className={cx("chat-row", highlighted && "chat-row--attention", unread && "chat-row--unread")}>
      <NavLink to={href} className="chat-row__link" onClick={() => clearAttention(row.id)}>
        {bot ? (
          <Avatar avatar={bot.avatar} status={bot.status} size={44} label={false} decorative star={bot.is_primary} />
        ) : (
          <span className="chat-row__room" aria-hidden="true">#</span>
        )}
        <span className="chat-row__text">
          <span className="chat-row__top">
            <span className="chat-row__name">
              {row.name}{bot?.is_primary ? <span className="sr-only">, your main bot</span> : null}
            </span>
            <time className="chat-row__time" dateTime={row.last_at}>{formatChatTime(row.last_at, now)}</time>
          </span>
          <span className="chat-row__bottom">
            {bot && BUSY.has(bot.status) ? <StatusLine bot={bot} /> : <Preview row={row} />}
            {unread ? <span className="chat-row__unread"><span className="sr-only">Unread</span></span> : null}
          </span>
        </span>
      </NavLink>
    </li>
  );
}
```

`web/src/components/ChatList.tsx`. Find:

```tsx
export function ChatList({ rows, bots, query, attention, now }: ChatListProps) {
  const shown = filterChats(withLiveNames(rows, bots), query);
  if (shown.length === 0) return <p className="chat-list__empty">{query.trim() ? "No chats match." : "No chats yet."}</p>;
  return (
    <ul className="chat-list" aria-label="Chats">
      {shown.map((row) => (
        <ChatRow key={`${row.kind}-${row.id}`} row={row} bot={row.kind === "bot" ? bots[row.id] : undefined}
          highlighted={attention.has(row.id)} now={now} />
      ))}
    </ul>
  );
}
```

Replace with:

```tsx
export function ChatList({ rows, bots, query, attention, unread = NOTHING_UNREAD, now }: ChatListProps) {
  const shown = filterChats(mainFirst(withLiveNames(rows, bots), bots), query);
  if (shown.length === 0) return <p className="chat-list__empty">{query.trim() ? "No chats match." : "No chats yet."}</p>;
  return (
    <ul className="chat-list" aria-label="Chats">
      {shown.map((row) => (
        <ChatRow key={`${row.kind}-${row.id}`} row={row} bot={row.kind === "bot" ? bots[row.id] : undefined}
          highlighted={attention.has(row.id)} unread={unread.has(row.id)} now={now} />
      ))}
    </ul>
  );
}
```

`web/src/pages/Home.tsx`. Find:

```tsx
import { Link, useNavigate } from "react-router-dom";
import { Avatar } from "../components/Avatar";
import { ChatList } from "../components/ChatList";
```

Replace with:

```tsx
import { Link, useNavigate } from "react-router-dom";
import { ChatList } from "../components/ChatList";
```

`web/src/pages/Home.tsx`. Find:

```tsx
import { useLiveState } from "../hooks/useLiveStore";
```

Replace with:

```tsx
import { useLiveState } from "../hooks/useLiveStore";
import { useUnread } from "../hooks/useUnread";
```

`web/src/pages/Home.tsx`. Find:

```tsx
function MainBotHero({ bot }: { bot: BotOut }) {
  return (
    <Link to={`/bots/${bot.id}`} className="main-bot" aria-label={`${bot.name}, your main bot`}>
      <Avatar avatar={bot.avatar} status={bot.status} activity={bot.activity} size={120} label={false} decorative star />
      <span className="main-bot__name">{bot.name}</span>
    </Link>
  );
}

```

Delete it.

`web/src/pages/Home.tsx`. Find:

```tsx
  const attention = useAttention();
  const navigate = useNavigate();
  const byId: Record<string, BotOut> = Object.fromEntries((bots ?? []).map((bot) => [bot.id, live.bots[bot.id] ?? bot]));
  const main = Object.values(byId).find((bot) => bot.is_primary);
  const waiting = openStuckCards(mergeStuck(stuckList.cards, live.stuckCards));
```

Replace with:

```tsx
  const attention = useAttention();
  const unread = useUnread(rows);
  const navigate = useNavigate();
  const byId: Record<string, BotOut> = Object.fromEntries((bots ?? []).map((bot) => [bot.id, live.bots[bot.id] ?? bot]));
  const waiting = openStuckCards(mergeStuck(stuckList.cards, live.stuckCards));
```

`web/src/pages/Home.tsx`. Find:

```tsx
      {error ? <ErrorNotice message={error} onRetry={reload} /> : null}
      {main && !query.trim() ? <MainBotHero bot={main} /> : null}
      {!query.trim() ? (
```

Replace with:

```tsx
      {error ? <ErrorNotice message={error} onRetry={reload} /> : null}
      {!query.trim() ? (
```

`web/src/pages/Home.tsx`. Find:

```tsx
      {bots !== null ? <ChatList rows={rows} bots={byId} query={query} attention={attention} /> : null}
```

Replace with:

```tsx
      {bots !== null ? <ChatList rows={rows} bots={byId} query={query} attention={attention} unread={unread} /> : null}
```

- [ ] **Step 6: The styles**

`web/src/styles/home.css`. Find:

```css
/* ---------------------------------------------------------------------
   Home (S1.4) — the list pane, laid out like a chat app: a header (your
   initials · search · Board · +), the main bot big and centred, then one
   row per bot and per room, newest first. Plus the pop-up Menu, the
   working dots and the desktop's empty detail pane.
   --------------------------------------------------------------------- */
```

Replace with:

```css
/* ---------------------------------------------------------------------
   Home (S1.4) — the list pane, laid out like a chat app: a header (your
   initials · search · Board · +), then one row per bot and per room: the
   main bot first, wearing its star, the rest newest first (redesign P2).
   Plus the working dots and the desktop's empty detail pane.
   --------------------------------------------------------------------- */
```

`web/src/styles/home.css`. Find:

```css
/* ---- The main bot ---------------------------------------------------- */

.main-bot {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  align-self: center;
  margin: 4px 0 12px;
  padding: 12px 24px 14px;
  border-radius: var(--radius-lg);
  color: var(--color-text);
  text-decoration: none;
  transition: background-color var(--duration-fast) var(--ease-standard);
}

.main-bot:hover {
  background: var(--color-raised);
}

.main-bot__name {
  font-family: var(--font-sans);
  font-size: var(--fs-heading);
  font-weight: 600;
  letter-spacing: -0.015em;
  line-height: 1.2;
}

```

Delete it.

`web/src/styles/home.css`. Find:

```css
.chat-row__link.active {
  background: var(--color-raised);
  box-shadow: inset 0 0 0 1px var(--color-border-strong);
}
```

Replace with:

```css
/* The open chat: a soft fill, no outline (redesign P2). */
.chat-row__link.active {
  background: var(--color-accent-tint);
}
```

`web/src/styles/home.css`. Find:

```css
.chat-row__room {
  display: grid;
  flex: none;
  place-items: center;
  width: 44px;
  height: 44px;
  border: 1px solid var(--color-border-strong);
  border-radius: var(--radius-md);
  color: var(--color-text-secondary);
  font-family: var(--font-mono);
  font-size: var(--fs-lead);
}
```

Replace with:

```css
.chat-row__room {
  display: grid;
  flex: none;
  place-items: center;
  width: 44px;
  height: 44px;
  border: 1px solid var(--color-border-strong);
  border-radius: var(--radius-md);
  color: var(--color-text-secondary);
  font-size: var(--fs-lead);
}
```

`web/src/styles/home.css`. Find:

```css
.chat-row__preview--empty {
  color: var(--color-text-faint);
}
```

Replace with:

```css
.chat-row__preview--empty {
  color: var(--color-text-faint);
}

/* The preview or status line, and the unread dot at its end. */
.chat-row__bottom {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-width: 0;
}

.chat-row__bottom > :first-child {
  flex: 1;
  min-width: 0;
}

.chat-row__unread {
  flex: none;
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: var(--color-accent-strong);
}

.chat-row--unread .chat-row__name,
.chat-row--unread .chat-row__preview {
  color: var(--color-text);
}
```

- [ ] **Step 7: Run the tests to see them pass**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && cd web && npx vitest run tests/plainText.test.ts tests/unread.test.ts tests/attention.test.ts tests/chatLook.test.ts tests/ChatList.test.tsx tests/Home.test.tsx tests/Layout.test.tsx tests/tokens.test.ts`
Expected: PASS. `unread.test.ts`'s refusal test logs nothing: it mutes the warnings it checks for.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && cd web && npm test && npm run build && npm run size`
Expected: every vitest file passes; the build succeeds; the entry stays within budget (about 202 KB gzip).

- [ ] **Step 8: Commit**

Run:

```bash
cd /Users/blckit/Desktop/Code_Projects/roost && \
git add web/src/lib/plainText.ts web/src/lib/unread.ts web/src/hooks/useUnread.ts web/src/lib/attention.ts \
  web/src/components/ChatList.tsx web/src/pages/Home.tsx web/src/styles/home.css web/tests/plainText.test.ts \
  web/tests/unread.test.ts web/tests/attention.test.ts web/tests/chatLook.test.ts web/tests/ChatList.test.tsx \
  web/tests/Home.test.tsx web/tests/setup.ts web/e2e/main-bot.spec.ts && \
git commit -m "feat: Home lists the main bot first with its star, unread dots, a soft active row and plain previews"
```

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && git status --short`
Expected: none of the files above is listed.

---

### Task 6: E2E for the chat, the docs, and the final checks

The design's testing list and Review Focus 4. Tasks 1–5 built and unit-tested everything; this task proves the layout in a real browser, where jsdom cannot measure: wide content scrolls inside the reply, Copy reaches the clipboard, the composer grows and keeps the last message in view. Then it records P2 in CLAUDE.md and runs every gate once more.
- **`web/e2e/fixtures/team-script.json`** gains "Writer": one step that adds a task ("Water the ferns"), then a markdown reply with a heading, a list with a `[[Garden plan]]` chip, a table of long file names, a 190-character code line, a 100-character word and a link.
- **`web/e2e/chat.spec.ts`**:
  - the reply is a card with its heading, its step line "Added a task", the chip and the link (`noopener noreferrer`); the table and the code scroll sideways inside it while the chat and the page do not; Copy code puts the code on the clipboard and says "Copied";
  - on a 560 px tall window, with the chat long enough to scroll, five lines grow the composer past two and a half lines, every line shows, its corners are square, and the last message stays inside the scroll box.
- **Spec order** (alphabetical, one worker): `chat` now runs first, so its `signIn` creates the account and it makes Writer; no later spec counts bots or tasks ("Water the ferns" joins the shared Board).
- **Docs.** The CLAUDE.md Documentation Map gains this plan (after P1's line), and the Architecture section a paragraph on the chat. `tests/test_docs.py` pins both; its existing check keeps every map entry pointing at a file that exists, so this plan is committed in this task.

**Files:**
- Create: `web/e2e/chat.spec.ts`
- Modify: `web/e2e/fixtures/team-script.json`, `CLAUDE.md`, `tests/test_docs.py`
- Commit also: `docs/plans/2026-10-15-roost-redesign-p2-chat.md` (this plan, untracked until now)
- Test: `web/e2e/chat.spec.ts`, `tests/test_docs.py`, and every suite once more

**Interfaces:**
- Consumes: `signIn`, `createBot`, `openChat`, `say`, `detailPane` (`web/e2e/helpers.ts`); the names and classes under Tasks 1–5's "Produces".
- Produces: `tests/test_docs.py` `REDESIGN_DOCS` and `LOOK_PLACES` with P2's places, so P3–P5 keep pointing at real files. No code interface.

- [ ] **Step 1: Path guard**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && git -C /Users/blckit/Desktop/Code_Projects/roost rev-parse --show-toplevel && git -C /Users/blckit/Desktop/Code_Projects/roost branch --show-current`
Expected: `/Users/blckit/Desktop/Code_Projects/roost` then `night-1`. If either differs, stop.

Then confirm Task 5 has landed and this task has not:

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && test -f web/src/lib/unread.ts && test ! -f web/e2e/chat.spec.ts && grep -c "roost-redesign-p2" CLAUDE.md`
Expected: `0`. Otherwise stop.

Then check that the names the spec uses are in the code:

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && for text in 'message--card' 'aria-label="Steps"' 'wikilink-chip' 'aria-label="Table"' 'md__code' 'Copy code' '"Copied"' 'chat-page__scroll' 'message-list' 'noopener noreferrer'; do grep -rqF -- "$text" web/src || echo "missing: $text"; done`
Expected: no output. If something is listed, stop and reconcile Tasks 1–5 with their "Produces" before writing the spec. Never loosen a spec to fit.

- [ ] **Step 2: Write the spec, its script and the docs test**

`web/e2e/fixtures/team-script.json`. Find:

```json
    [{ "text": "Signed in and done." }]
  ]
}
```

Replace with:

```json
    [{ "text": "Signed in and done." }]
  ],
  "Writer": [
    [{ "tool": "add_task", "args": { "title": "Water the ferns" } }],
    [{ "text": "## Your week\n\n- **Monday**: water the ferns\n- **Tuesday**: see [[Garden plan]]\n- **Wednesday**: call the plumber\n\n| Day | Morning | Afternoon | File |\n| --- | --- | --- | --- |\n| Mon | Ferns | Market | `balcony_ferns_watering_schedule_for_october_and_november_v2_final.xlsx` |\n| Tue | Garden plan | Shop | `garden_plan_with_every_bed_and_every_pot_drawn_to_scale_v3.pdf` |\n| Wed | Plumber | Laundry | `plumber_quote_for_the_kitchen_tap_and_the_bathroom_pipes_2026.pdf` |\n\n```js\nconst plan = [\"water the ferns\", \"see the garden plan\", \"call the plumber\", \"laundry\", \"cinema\", \"market\", \"rest\"].map((step, day) => `${day + 1}. ${step}`).join(\" | \");\n```\n\nSaved as balcony_ferns_watering_schedule_for_the_whole_of_october_and_november_v2_final_really_final.xlsx. More at https://docs.example/guide." }]
  ]
}
```

Create `web/e2e/chat.spec.ts`:

```ts
import { expect, test } from "@playwright/test";
import { createBot, detailPane, openChat, say, signIn } from "./helpers";

// The chat (redesign P2), against fixtures/team-script.json's "Writer": a step that adds a task, then a
// markdown reply with a heading, a list, a [[wikilink]], a wide table, a long code line and a link.
// The first spec, alphabetically: it creates the account, and Writer, whom the second test reuses.
test.use({ permissions: ["clipboard-read", "clipboard-write"] });

test("a markdown reply: its step, a heading, a chip, a table and code that scroll inside it, and Copy code", async ({ page }) => {
  await signIn(page);
  await createBot(page, "Writer", "Writes things up");
  const detail = detailPane(page);
  await say(page, "Writer", "plan my week");
  const reply = detail.locator(".message--card");
  await expect(reply.getByRole("heading", { name: "Your week" })).toBeVisible();
  await expect(reply.getByRole("list", { name: "Steps" })).toHaveText("Added a task");
  await expect(reply.locator(".wikilink-chip", { hasText: "Garden plan" })).toBeVisible();
  await expect(reply.getByRole("link", { name: "docs.example" })).toHaveAttribute("rel", "noopener noreferrer");

  // Review Focus 4: a wide table and a long code line scroll inside the reply, never the chat or the page.
  for (const wide of [reply.getByRole("region", { name: "Table" }), reply.locator(".md__code pre")]) {
    expect(await wide.evaluate((element) => element.scrollWidth > element.clientWidth)).toBe(true);
  }
  expect(await page.locator(".chat-page__scroll").evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);

  await reply.getByRole("button", { name: "Copy code" }).click();
  await expect(reply.getByRole("button", { name: "Copied" })).toBeVisible();
  expect(await page.evaluate(() => navigator.clipboard.readText())).toContain("const plan = [");
});

test.describe("on a short screen", () => {
  test.use({ viewport: { width: 1280, height: 560 } });

  test("the composer grows with its text, clips no letter and keeps the last message in view", async ({ page }) => {
    await signIn(page);
    await openChat(page, "Writer");
    const detail = detailPane(page);
    const scroller = page.locator(".chat-page__scroll");
    await expect(detail.locator(".message--card")).toBeVisible();
    expect(await scroller.evaluate((element) => element.scrollHeight > element.clientHeight)).toBe(true);

    const box = detail.getByPlaceholder("Message Writer");
    const oneLine = (await box.boundingBox())!.height;
    await box.fill(Array.from({ length: 5 }, (_, line) => `Line ${line + 1} of a longer message`).join("\n"));
    await expect.poll(async () => (await box.boundingBox())!.height).toBeGreaterThan(oneLine * 2.5);
    expect(await box.evaluate((element) => element.scrollHeight <= element.clientHeight + 1)).toBe(true);
    expect(await box.evaluate((element) => getComputedStyle(element).borderTopLeftRadius)).toBe("0px");

    const shown = (await scroller.boundingBox())!;
    await expect.poll(async () => {
      const last = (await detail.locator(".message-list > .message").last().boundingBox())!;
      return last.y + last.height <= shown.y + shown.height + 1;
    }).toBe(true);
  });
});
```

`tests/test_docs.py`. Find:

```python
REDESIGN_DOCS = (
    "docs/plans/2026-10-15-roost-look-and-feel-design.md",
    "docs/plans/2026-10-15-roost-redesign-p1-foundation.md",
)
LOOK_PLACES = ("web/src/styles/tokens.css", "web/src/ui/", "web/src/components/robot/", "/api/bots/{id}/picture")
```

Replace with:

```python
REDESIGN_DOCS = (
    "docs/plans/2026-10-15-roost-look-and-feel-design.md",
    "docs/plans/2026-10-15-roost-redesign-p1-foundation.md",
    "docs/plans/2026-10-15-roost-redesign-p2-chat.md",
)
LOOK_PLACES = (
    "web/src/styles/tokens.css", "web/src/ui/", "web/src/components/robot/", "/api/bots/{id}/picture",
    "web/src/components/markdown/", "web/src/components/chat/", "web/src/lib/unread.ts",
)
```

`tests/test_docs.py`. Find:

```python
def test_the_documentation_map_names_the_redesign_design_and_its_p1_plan():
```

Replace with:

```python
def test_the_documentation_map_names_the_redesign_design_and_its_plans():
```

- [ ] **Step 3: Run them to see them fail, and the new spec pass**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && ROOST_DATA_DIR=$(mktemp -d) ROOST_DESKS_DIR=$(mktemp -d) uv run pytest tests/test_docs.py -q`
Expected: FAIL, 2 failed and 4 passed: `test_the_documentation_map_names_the_redesign_design_and_its_plans` and `test_the_architecture_section_says_where_the_look_lives`.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && df -g /System/Volumes/Data | awk 'NR==2{print $4}'`
Expected: at least 8. Otherwise stop and report.

Run this as one shell call:

```bash
cd /Users/blckit/Desktop/Code_Projects/roost && cd web && \
port=18800 && if curl -fsS -o /dev/null --max-time 2 http://127.0.0.1:18800/api/health; then port=5173; fi && \
npm run build && ROOST_DESKS_DIR=$(mktemp -d) ROOST_E2E_PORT=$port npx playwright test e2e/chat.spec.ts e2e/main-bot.spec.ts e2e/records.spec.ts
```

Expected: 6 passed (`chat` 2, `main-bot` 2, `records` 2). The specs add no code: they are new coverage of Tasks 1–5. If one fails:
- **A name is not found**: check it against Step 1's list and the task that produces it; fix the component, never the spec.
- **A wide box does not scroll** (`scrollWidth > clientWidth` is false): the table or `pre` lost `overflow-x: auto`, or a cell lost `overflow-wrap: normal` (`markdown.css`); if the chat scrolls sideways instead, something in the message has a fixed width.
- **The last message ends below the scroll box**: `useKeepBottom`'s ref is not on `.chat-page__scroll`, or the composer grows without `useAutoGrow`.
- **Copy code never says Copied**: the page has no clipboard permission (the spec grants it), or `useCopy` reached its "failed" branch: read the browser console.

- [ ] **Step 4: The docs**

`CLAUDE.md`. Find:

```markdown
- `docs/plans/2026-10-15-roost-redesign-p1-foundation.md` — the redesign's P1 plan: `tokens.css` and its guard test, the `web/src/ui/` kit (Radix menus, selects, tabs, sheets, popovers; Madrid date pickers with a lazy calendar), robot avatars and the avatar editor, `/api/dates/parse` and `/api/bots/{id}/picture`.
```

Replace with:

```markdown
- `docs/plans/2026-10-15-roost-redesign-p1-foundation.md` — the redesign's P1 plan: `tokens.css` and its guard test, the `web/src/ui/` kit (Radix menus, selects, tabs, sheets, popovers; Madrid date pickers with a lazy calendar), robot avatars and the avatar editor, `/api/dates/parse` and `/api/bots/{id}/picture`.
- `docs/plans/2026-10-15-roost-redesign-p2-chat.md` — the redesign's P2 plan: bot replies as markdown (one lazy chunk shared with the notes preview), messages without borders, copy and time on hover, typing dots and a caret, a bot's steps as compact lines, the growing composer, and Home's main bot first, unread dots and plain previews.
```

`CLAUDE.md`. Find:

```markdown
A picture the user uploads (`/api/bots/{id}/picture`) shows on the robot's screen and is stored sealed in the avatar JSON.
```

Replace with:

```markdown
A picture the user uploads (`/api/bots/{id}/picture`) shows on the robot's screen and is stored sealed in the avatar JSON.

The chat (redesign P2): a bot's reply renders as markdown through `web/src/components/markdown/Markdown.tsx`, the one module that imports react-markdown, a lazy chunk the notes preview shares: no raw HTML, a link shows its real host, an image is never fetched, a `[[wikilink]]` is a chip, and the plain text shows while it loads or if it never does. `web/src/components/chat/` holds a message's pieces: copy and time on hover, the "from web content" mark, typing dots while a bot is On it with no text yet, a caret while text streams, and the bot's steps as compact lines ("Added a task"), built from live `bot_status` activities (`toolLines` in `store/live.ts`, gone after a reload until P4's record cards). The composers grow with their text in every browser, and the chat keeps its last message in view. Home lists the main bot first, wearing its star, with unread dots this browser remembers (`web/src/lib/unread.ts`).
```

- [ ] **Step 5: Full verification**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && ROOST_DATA_DIR=$(mktemp -d) ROOST_DESKS_DIR=$(mktemp -d) uv run pytest tests/test_docs.py tests/test_tool_lines.py tests/test_vocabulary.py -q`
Expected: PASS (`test_docs` has 6 tests, `test_tool_lines` 2).

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && ROOST_DATA_DIR=$(mktemp -d) ROOST_DESKS_DIR=$(mktemp -d) uv run pytest --cov=roost --cov-fail-under=80 -q`
Expected: PASS, the whole suite, with `Required test coverage of 80% reached` (about 94%).

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && cd web && npm test && npm run build && npm run size`
Expected:
- every vitest file passes, the licence gate, the token guard, `bundleGuard` (5 tests) and `chatLook` (3 tests) included (see Global Constraints for P1's picker tests on a busy Mac);
- the build lists `Markdown-*.js` (about 49 KB gzip) and `Calendar-*.js` apart from the entry;
- the size check prints the entry within `bundle-budget.json` (202.7 KB gzip of 257.4 KB when this plan was replayed).

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && df -g /System/Volumes/Data | awk 'NR==2{print $4}'`
Expected: at least 8. Otherwise stop and report.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && ROOST_DESKS_DIR=$(mktemp -d) make e2e`
Expected: every spec passes: `chat`, `computer`, `every-bot`, `look`, `main-bot`, `pickers`, `profile`, `projects`, `records`, `stuck` and `team` (14 tests). `make e2e` picks port 5173 when the live gateway holds 18800, and never touches `~/Roost/data`.

- [ ] **Step 6: Commit**

This plan is untracked until now; the design is already committed. The new map line must never point at an uncommitted file.

Run:

```bash
cd /Users/blckit/Desktop/Code_Projects/roost && \
git add web/e2e/chat.spec.ts web/e2e/fixtures/team-script.json CLAUDE.md tests/test_docs.py \
  docs/plans/2026-10-15-roost-redesign-p2-chat.md && \
git commit -m "test: E2E for the chat; docs: the redesign's P2 in CLAUDE.md"
```

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && git status --short`
Expected: none of the five files above is listed.
