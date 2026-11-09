# Roost Look & Feel Redesign — Design

**Status:** approved by the user in conversation on 2026-10-15. The implementation is planned and
built in five steps (P1–P5), each with its own plan file. Live control
(`docs/plans/2026-10-15-roost-live-control-design.md`) follows, built in the new style.

**Why:** in the user's words, the UI "is not friendly", "looks cheap", has "no slick typing, no
calendar or date-time picker", "chats look awful" and has "no canvas". Tasks also lack subtasks,
comments and budget/expense detail.

**Evidence:** a screen audit with 70 screenshots of every screen
(summarised here; screenshots were kept outside the repo). Its main findings:
- bot replies render as raw markdown;
- no typing indicator;
- native date inputs and selects;
- no spacing, shadow or control tokens (79 padding values, 25 hard-coded colours);
- faint text below contrast;
- the composer clips letters;
- two tab styles;
- inline forms;
- a white document editor;
- no canvas hooks.

**Quality bar:** a polished, calm, dark chat app with soft cards, a profile panel with tabs, and a
friendly avatar editor. **Clean room:** never copy another product's art, mascots or copy. Roost's
look is its own.

## Decisions (from the user, 2026-10-15)

- **V1. Bot avatars are "Boxbot".** Final pick on 2026-10-15, after several rounds of sketches.
  - **The head:** a boxy robot head with rivets and an antenna, and **no face**: no eyes, no mouth.
  - **Six head shapes:** Classic, Tall, Wide (TV with two antennas), Soft (rounded), Cube (3D) and Monitor (on a stand).
  - **The screen:** a dark screen that shows animated **signals** for what the bot is doing:
    - the five statuses: Resting, On it, Asking you, Stuck, Off duty;
    - three moments: Thinking, New message, Done.
  - **Three screen styles**, all available. Each bot picks one in the avatar editor:
    - **Glow icons** (the default): breathing wave, orbiting spinner, "?" bubble, warning sign, moon, thinking dots, envelope, tick;
    - **Pixel icons**: pixel heart, loading bar, pixel ?, !, moon, bubble, tick;
    - **Signals**: breathing ring, equaliser, prompt cursor, glitch, dim dot, spinner arc, ripple, filled tick.
  - **Colour:** signals are drawn in the bot's colour, lightened to glow on the screen.
  - **Main bot:** wears the star.
  - **Motion:** animations respect `prefers-reduced-motion`.
  - **The avatar JSON** gains an optional `screen` field (`glow` | `pixel` | `signal`; default `glow`), and its `shape` takes the six head names.
  - **Old avatars:** old shape values (the birds) map to heads in one lookup table, so nothing needs migrating.
  - **Reference sketch:** `docs/design/robot-faces-sketch.html`.
- **V2. Canvas means both:**
  - **cards in messages** (live record cards);
  - a **side panel** for documents, notes and sheets beside the chat.
- **V3. Build order:** looks first (P1 foundation → P2 chat), then P3 tasks, P4 canvas, P5 Board
  and finishing touches, then live control.
- **V4.** Dark theme only in this round. Light theme and phone polish later.

## P1 — Foundation

- **Design tokens** (`web/src/styles/tokens.css`, the single source):
  - colour: surfaces bg, panel, raised, overlay; text primary, secondary, faint (≥ 4.5:1 on
    panel); border hairline; accent violet; semantic ok, warn, danger, info;
  - spacing scale 4 · 8 · 12 · 16 · 20 · 24 · 32 · 48;
  - radius 6 · 10 · 14 · 20 · pill;
  - type scale 12 · 13 · 14 · 16 · 18 · 22 · 28, on the system font stack (`-apple-system,
    BlinkMacSystemFont, "SF Pro Text", "Segoe UI", system-ui, sans-serif`), with a mono stack only
    for code;
  - control heights 28 · 34 · 40;
  - shadows sm · md · lg;
  - motion durations;
  - focus ring.
  - Every component uses tokens. Hard-coded colours and font sizes are removed, and a test fails
    on new ones.
- **Components** (`web/src/ui/`):
  - Button (primary, secondary, ghost, danger; sizes), IconButton, Input, Textarea (auto-grow),
    Field (label, hint, error);
  - **Select** (Radix), **Menu** (Radix dropdown), **Tabs** (Radix; one style everywhere),
    **Sheet** (Radix dialog as a right-side drawer), **Popover**, Tooltip, Toast, Chip, Badge,
    Meter (budget bar), Skeleton, EmptyState.
  - **DatePicker** and **DateTimePicker**: a field you can type in (with the existing
    natural-language parser's preview), a calendar popover (react-day-picker), time chips, and
    quick picks (Today, Tomorrow, Next week, No date).
  - Dependencies, all MIT: `@radix-ui/*` (only the primitives used) and `react-day-picker`. Their
    licences are checked by the existing licence gate test. The main bundle stays within
    `bundle-budget.json`; the calendar is lazy-loaded.
- **Robot avatars** (`web/src/components/Avatar.tsx` rewritten, plus `web/src/components/robot/{heads,signals}.tsx`):
  - drawn as SVG from `{shape, color, badge, screen}`;
  - status-aware (the signals above), with animations that respect `prefers-reduced-motion`;
  - the old bird shapes map to the robot heads in one lookup table, so stored avatars need no
    migration;
  - the backend's allowed shape list gains the six head names and the `screen` field, and old values are still accepted;
  - new bots get different default colours.
- **Avatar editor:** a big live preview, Head shape, Colour and Screen style pickers, Upload (the existing
  upload path), and "Surprise me".

## P2 — Chat

- **Messages:**
  - bot text renders as markdown (`react-markdown` + `remark-gfm`, already dependencies) with
    headings, lists, tables (scrollable), code blocks with copy, links and `[[wikilinks]]` as
    chips;
  - no bubble borders;
  - long bot replies are full-width cards; user messages are accent bubbles;
  - hover actions: copy and time;
  - day separators;
  - chat-list previews strip markdown.
- **Typing indicator:** while a run is "On it" with no text yet, the bot's robot (On it signal) and
  three animated dots show; a caret shows while text streams.
- **Composer:**
  - auto-grows in every browser and never clips the first or last letter;
  - Enter sends, Shift+Enter adds a new line;
  - growing never hides the last message;
  - the + menu and attachments as today.
- **Small cards for tool work:** a compact line for "Added task …", "Saved document …" and
  similar. P2 renders the existing tool-activity info; P4 makes them live record cards.
- **Sidebar:**
  - the large main-bot hero is dropped, and the main bot sits first in the list with its star;
  - the active row has a soft fill;
  - unread dots;
  - status faces on avatars.

## P3 — Tasks done properly

- **Subtasks (steps):** add, rename, tick, untick, reorder and delete, on the web and for bots.
  - Tools: `add_step`, `update_step` (title / done), `delete_step` and `move_step` (write_change;
    `add_step` is write_create).
  - Deleting a step that has expenses moves them to the task, as LazyClaw did (`step_id` cleared).
- **Comments** on a task or a step.
  - Schema: the **next free version**. Today that is v14; if live control's `site_logins` is
    built first, comments take v15, and the later plan renumbers.
  - Table `task_comments`: id, user_id, task_id (cascade), step_id (nullable), author ("user" or a
    bot id), body (`enc:v2`, AAD `task_comments:body`), created_at, edited_at, deleted_at.
  - Tools: `add_comment` (write_create) and `list_comments` (read).
  - Routes:
    - `GET` / `POST /api/tasks/{id}/comments`;
    - `PATCH` / `DELETE /api/comments/{id}`, own comments only.
  - Bot comments carry the taint rules like any record.
- **The task drawer** (Sheet) holds everything:
  - title, list, project, priority;
  - due (DateTimePicker), reminder, repeat;
  - subtasks with progress;
  - budget slice, spent and left, per task and per step;
  - the linked expenses (add an expense for this task or step right there);
  - the comments thread;
  - the activity: made by a bot, from web content.
- **Quick typing** (the Board's quick-add bar and the project page):
  - `Call plumber tomorrow 9am #Renovation €200 !high` becomes chips (date, project, budget,
    priority) as you type, before Enter.
  - Parsing is client-side for the preview, and the server stays the authority: the existing
    `nl_time` rules plus `#project` (exact or ask), `€/$/£ amount` (the budget slice, in the
    project's currency) and `!high/!low`.
- Task rows are structured: checkbox, title, chips for due, project and progress, with actions on
  hover.

## P4 — Canvas

- **Record cards in the chat:**
  - When a bot's tool creates or changes a task, expense, note, document or project, the run posts
    a `kind="record_card"` message with the body `{record, id, action}`. The backend change: domain
    tool outcomes report the record they touched, and the turn posts one card per record per run.
  - The web renders a live card that fetches the record: a task card with a checkbox and due date,
    an expense card with the amount and project, doc and note cards with a title and preview, a
    project card with its bars.
  - A deleted record shows a folded line.
  - Cards carry the record's taint mark.
- **The side panel:**
  - The Chat page gets a right panel (resizable, closable, kept in the URL as
    `?canvas=doc:<id>` / `note:<id>` / `sheet:<id>`).
  - It reuses the existing document, sheet and note editors, in a dark theme.
  - A doc, note or sheet card has **Open**. A document the bot creates in this chat opens
    automatically (via its record card).
  - A long message has **Open in canvas** (read-only markdown view, copy and save as a note).

## P5 — Board and finishing touches

- **Board:**
  - structured expense rows (amount right-aligned, project, star and void on hover);
  - create and edit in Sheets with the new pickers;
  - one tab style;
  - a project header card;
  - Delete marked as danger.
- **The document editor** gets a dark theme, and the notes editor a normal font and live preview.
- **Empty states** have a robot picture and suggested first prompts ("Ask Grok… to plan your week"
  uses the bot's real name).
- **Leftovers from the stuck and hub polish:**
  - Try again and Give it back send `how`;
  - the Holding view has Give up;
  - the chat's Stuck list has Retry;
  - closed cards fold after a reload;
  - one "is stuck" notification per stay (skip frames with null activity);
  - existing tasks, notes and documents can be moved into a project;
  - the project edit form compares with its opened values;
  - Keep is in the project header;
  - General's Money tab hides top-ups;
  - the due-before-start check runs on the client.

## Testing

- **Every step:**
  - vitest for each component and screen;
  - pytest for the backend parts (steps, comments, record cards);
  - Playwright E2E for the main flows: quick-add a task with chips, open the drawer, add a step
    and a comment, tick a task card in chat, open a bot-made doc in the canvas, edit an avatar.
- **The bundle budget** and the licence gate stay green.
- **A token test** fails on new hard-coded colours or font sizes in `web/src`.

## Out of scope (this round)

- A light theme, and phone-first layouts.
- Live control: next, with its own plan.
- Real-time co-editing between bot and user in the canvas. The bot edits through its tools, and
  the panel refreshes on `*_changed` events.
