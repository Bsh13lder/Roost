# Roost Polish R1, "the Grok-feel shell" — Design

**Status:** drafted on 2026-10-20 from the user's request and the Grok screenshots they shared in
conversation. The plan is `docs/plans/2026-10-20-roost-polish-r1.md`.

**Why:** the user wants Roost's web to feel as easy as Grok's app. Today the chat list is a plain
column with the account menu at the top, the Profile is a separate page that takes you away from the
chat, and the Computer tab says "asleep" in one grey line.

**Clean room:** copy the *ease* (one fixed sidebar, a side panel beside the chat, quiet lines, one
round composer), never another product's art, icons or wording. Every word below is Roost's own
(CLAUDE.md vocabulary), every colour and size comes from `tokens.css`, every control from `web/src/ui/`.

**Builds on:**
- P1's kit (Sheet, Tabs, Popover, Menu, Button, Input, Chip) and the robot avatars.
- P2's chat: markdown replies, day separators (`message-date`, S1.5), hover actions, typing dots,
  step lines, the growing composer, unread dots (`lib/unread.ts`).
- Memory (`docs/plans/2026-10-20-roost-memory.md`, Tasks 11–12): the Info tab's **What I
  remember** (`MemoryPanel`), one endless chat per bot, **Earlier conversations** read-only, the
  "Remembered: …" line with Undo. R1 moves these as they are; it changes none of their behaviour.

## What exists, and what R1 adds

| Piece | Today | R1 |
|---|---|---|
| Sidebar | `Layout` aside renders `Home`: initials · search toggle · Board · + on top, My turn, one flat list | search and + on top, a row of bot avatars, chats under group headings, initials menu and Board at the bottom |
| Bot group | none | `bots.group_label` (schema v16), set from the panel's hero |
| Profile | its own page, `/bots/:id/profile?tab=` | a right panel beside the chat, `?panel=`; the old address redirects |
| Day separators | yes (`withDays` in `MessageList`) | kept, drawn as a centred line with hairlines |
| NEW divider | none | one, above the first message you have not seen |
| Activity lines | left-aligned with a dot | centred and quiet |
| Composer | a round + beside a pill | one round pill holding +, the text and send |
| Computer asleep | one line of text | a sleeping robot, "Computer is asleep", **Open it** |
| `profile.css` / `chat.css` | 665 / 783 lines | split by feature, each file ≤ 400 lines typical, 800 max |

## Decisions

- **R1.1 One fixed sidebar.** On a desktop the sidebar is a fixed column (`--sidebar-width`, a new
  layout token) that never scrolls with the chat. It has three parts, top to bottom:
  - **Top:** a search field that is always there (no toggle) and the **+** menu (New bot, New room).
  - **Middle, scrolling:** the avatar row, My turn, then the chats.
  - **Foot, pinned to the bottom:** your initials menu (unchanged items) and **Board**.
  - On a phone (≤ 768px, the breakpoint every stylesheet already uses) the sidebar is the list view on
    `/`, as today.
- **R1.2 The avatar row.** A row of round robot avatars at the top of the middle part: the main bot
  first, wearing its star, then the other bots by latest chat activity, at most `SIDEBAR_AVATARS_MAX`
  (6). Each robot's screen shows its status (the Avatar already does); its name is its accessible
  name and its tooltip. A tap opens that bot's chat. Nothing is pinned by hand in R1: the row is
  automatic (open for the user, below). The row hides while you search.
- **R1.3 Chats under group headings.** The list is split into sections:
  - first, with no heading: the bots with no group and every room, the main bot first, the rest
    newest first (P2's order, unchanged);
  - then one section per group label, headed by the label, sorted by the label (case-insensitive,
    `localeCompare`), each newest first.
  - An empty section is not drawn. Search filters every section and hides the empty ones.
  - Each row keeps P2's look: avatar, name, time, a one-line plain preview (or the busy status line)
    and the unread dot.
- **R1.4 The group label (schema v16).** A bot gets an optional `group` label.
  - Stored as `bots.group_label` (`group` is an SQL keyword), `enc:v2` under `bots:group_label`:
    the user typed it, so it is user content (CLAUDE.md). The wire name is `group`.
  - One line, at most `MAX_BOT_GROUP_LENGTH` (30) characters, checked like the name and job.
  - `PATCH /api/bots/{id}` takes `group`: a string sets it, `""` or `null` clears it, leaving it out
    keeps it. `BotOut` carries `group` (`null` when none); the `bot_updated` frame carries it too.
  - Another user's bot stays a 404. The label is never sent to a model, never in a roster line,
    and never in a Template file (it is how *you* sort your bots, not part of the bot).
  - Live control's `site_logins`, last planned as v16, takes v17.
- **R1.5 The bot side panel.** The chat header's name pill opens a panel on the right that holds the
  Profile: the hero, then the tabs **Info · Documents · Computer · Links**. It replaces the Profile page.
  - **The URL holds it:** `/bots/:id?panel=info|documents|computer|links`; no `panel` means closed.
    `?thread=` lives beside it. Opening pushes a history entry (Back closes it); changing tab
    replaces it.
  - **The pill** stays a link with the same name, "Open {name}'s profile", so every existing E2E
    still finds it; while the panel is open it reads "Close {name}'s profile" and links to the chat
    without `panel`.
  - **Desktop:** a non-modal panel (`--panel-width`) beside the chat; the chat stays usable. Wider
    than 1024px it pushes the chat; between 769px and 1024px it floats over it with a shadow. It
    slides in (`--duration-slow`; none under reduced motion). Its head has **Close**; Escape inside
    it closes it; focus goes to the panel's heading on open and back to the pill on close.
  - **Phone:** the same content in the kit's `Sheet`, full screen (a new `size="full"`), modal.
  - **One right panel at a time:** P4's canvas (`?canvas=`) will share this slot; opening one closes
    the other.
  - Rooms get no panel in R1.
- **R1.6 The old addresses.** `/bots/:id/profile?tab=x` redirects to `/bots/:id?panel=x` (Info when
  the tab is missing or unknown); `/bots/:id/desk` to `?panel=computer`. The Stuck card's
  **See its screen** and the Instructions page's Back point at the panel. `pages/Profile.tsx` goes.
- **R1.7 The hero.** At the top of the panel: the robot (96px) with the main bot's star, the
  "Main bot" mark, the status in words, the name and job editable in place (`NameJobCard`, as
  today), and the group label:
  - with no label, a quiet **Add a label** chip; with one, the label as a chip;
  - either opens a `Popover`: an `Input` (one line, 30 characters), the labels your other bots
    already use as one-tap choices, **Save**, and **Remove label** when there is one;
  - a refusal from the server shows its sentence under the field, and the field keeps your text.
- **R1.8 The Info tab is unchanged.** It still holds the look, Instructions, Notifications, Share as
  Template and **What I remember**; the panel hosts it as it is. Share as Template moves out of the
  old page header (the Info row already offers it); the ⋯ menu stays in the chat header.
- **R1.9 Quiet, centred activity lines.** Activity lines, handoff lines and the "Remembered: …" line
  sit centred in the chat, in the caption size and the secondary colour, with no dot. P2's step lines
  under a reply are unchanged.
- **R1.10 The NEW divider.** When you open a bot's main chat, Roost takes the time this browser last
  saw it (`lib/unread.ts`) once, before the list marks it read. A "New" line, centred between two
  hairlines like a day separator, sits above the first message after that time that is not yours. It
  stays until you leave the chat. No divider on a first visit, in an earlier conversation, or when
  nothing is new. It has `role="separator"` and the label "New messages".
- **R1.11 Day separators** stay where P2 put them (one per Madrid day, Today / Yesterday / a date),
  and share the NEW divider's centred-hairline look.
- **R1.12 The round composer pill.** One pill holds the round **+** (inside, on the left), the
  growing text and the round send button. It is fully round while it is one line and takes
  `--radius-lg` once it grows. A read-only earlier conversation keeps its quiet line and **Back to
  the chat** (memory Task 12), with no pill.
- **R1.13 Computer is asleep.** When the screen answers "asleep", the screen box shows the bot's own
  robot with its Off duty screen (the moon) and three small "z" marks drifting up (still under
  reduced motion), the heading "Computer is asleep", the line "{name}'s computer wakes when it
  needs it.", and **Open it** (the existing start-browser action). Loading and "Can't reach" keep
  their lines.
- **R1.14 Stylesheets stay focused.** Each stylesheet is ≤ 800 lines (typically 200–400), split by
  feature; a test fails on a longer one, and on a file in `styles/` that `styles.css` doesn't import.
  - `chat.css` → `chat.css` (messages, separators), `chat-dock.css` (header, composer, dock),
    `chat-cards.css` (fold cards, Stuck card) and `chat-sheet.css` (Earlier conversations,
    read-only line).
  - `profile.css` → `profile.css` (the tabs), `instructions.css` (the Instructions page), with the
    avatar picker moved into `avatar-studio.css`; the dead `.profile-page*` rules go once the page
    does.
  - New: `sidebar.css` (replaces `home.css`) and `panel.css`.

## Words (CLAUDE.md vocabulary)

Chat, Profile (the panel's accessible name is "{name}'s profile"), Board, main bot, Computer,
Earlier conversations, My turn. New strings: "Search chats", "Add a label", "Remove label",
"Label", "New messages" / "New", "Computer is asleep", "Open it", "Close {name}'s profile".

## Out of scope (later)

- Pinning or reordering bots by hand; collapsing a group; groups for rooms.
- P4's canvas (only its URL slot is reserved, R1.5).
- A light theme (V4 stays: dark only).

## Open for the user

- **The avatar row is automatic** (R1.2). If they want to choose the bots in it, a pin is a small
  follow-up (a plaintext `pinned` flag on `bots`, or a per-browser list like the unread dots).

## Testing

- pytest: the v16 migration (v15 frozen first), the store's encrypted label, the PATCH field
  (set, keep, clear, too long, two lines, another user's bot a 404).
- vitest: the sidebar's sections and avatar row (pure functions first), the sidebar, the panel and
  its URL, the redirects, the group label, the NEW divider, the composer pill, the asleep state,
  and the stylesheet guard. `tokens.test.ts` and the bundle budget stay green.
- Playwright: one spec for the shell (sidebar, label, panel, redirect, phone sheet), and the
  existing specs kept green.
