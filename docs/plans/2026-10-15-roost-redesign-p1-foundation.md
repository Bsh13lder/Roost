# Roost Look & Feel Redesign, P1 Foundation, Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One design-token file and a small UI kit that every screen builds from, typeable date and date-time pickers on Madrid time, and Boxbot robot avatars (six heads, three screen styles that show the five statuses) with an avatar editor that has Head, Colour, Screen, Upload and Surprise me.

**Architecture:**
- **Tokens.** `web/src/styles/tokens.css` becomes the one source of colours, font sizes, spacing, radii, control heights, shadows, durations and the focus ring. A scripted, whole-name rename moves every stylesheet onto the new names, the 25 hard-coded colours and 23 font sizes become tokens, and `web/tests/tokens.test.ts` fails on any new one (and on unreadable text).
- **The kit** (`web/src/ui/`). Button, IconButton, Input, Textarea, Field, Chip, Badge, Meter, Skeleton, EmptyState and Toast keep base.css's existing class names, so every screen restyles at once. Select, Menu, Tabs, Sheet, Popover and Tooltip are thin wrappers over Radix primitives and replace the app's native selects, its home-made menu and its two tab styles.
- **Dates.** A picker's value is the text the gateway reads: a picked Madrid day (`2026-10-16`), a picked Madrid wall time (`2026-10-16 09:00`), or the words typed. The line under the box shows how the gateway reads the words (`GET /api/dates/parse`, the same `parse_due` a task's due uses). Date-only APIs get a day (`resolveDay`) before saving. The month grid (react-day-picker) is a lazy chunk.
- **Robots.** `web/src/components/robot/` draws a Boxbot from the avatar JSON `{shape, color, badge, screen}`: one of six heads, a dark screen, and a signal for the status or moment in the bot's screen style. `Avatar.tsx` is rewritten on top. The gateway accepts the six heads, still accepts every old bird shape, stores what it is sent, and gives a new bot a colour nobody on the team wears. The web draws an old shape through one table.
- **The editor.** `AvatarStudio` (big live preview of the bot's status, Head, Colour, Screen, Surprise me, Upload) serves the profile and the New bot form. Upload shrinks the picture to 256 px in the browser and posts the raw image (`POST /api/bots/{id}/picture`, the PDF upload's pattern). The picture is stored sealed (`enc:v2`) inside the avatar JSON, so there is no schema change, and it shows on the robot's screen.

**Tech Stack:** The S1 stack, plus:
- Python 3.12 (uv), FastAPI, aiosqlite, pydantic 2, `cryptography`.
- Vite, React 19 and TypeScript, tested with vitest + Testing Library and Playwright.
- New, all MIT: `@radix-ui/react-select` 2.3.7, `@radix-ui/react-dropdown-menu` 2.1.24, `@radix-ui/react-tabs` 1.1.21, `@radix-ui/react-dialog` 1.1.23, `@radix-ui/react-popover` 1.1.23 and `@radix-ui/react-tooltip` 1.2.16 (all released 2026-07-24), and `react-day-picker` 9.13.2 (2026-02-10; it brings `date-fns` 4, `@date-fns/tz` and `date-fns-jalali`, all MIT, all in the lazy calendar chunk).
- Removed: `@fontsource/inter`, `@fontsource/bricolage-grotesque` and `@fontsource/jetbrains-mono`. Type is the system stack.

**Spec:** `docs/plans/2026-10-15-roost-look-and-feel-design.md`, section "P1 — Foundation" and decisions V1 (Boxbot, final) and V4 (dark only). The robot reference is `docs/design/robot-faces-sketch.html` (its `HEADS` and `STYLES` are ported in Task 5). Where the design and the code disagree, the "Design meets code" list below says what this plan does.

> **Status (2026-10-15): ready to execute.** Every task's code and tests were replayed in order on a copy of `night-1`: vitest 479 tests, pytest 1,780 tests (94% coverage), `npm run build`, and all 12 Playwright specs passed. The entry chunk went from 119.3 KB to 198.6 KB gzip, within the 257.4 KB budget.

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
  - `make e2e` starts its own throwaway gateway with `ROOST_DATA_DIR=$(mktemp -d)`. It picks port 5173 by itself while the live gateway holds 18800. Never point a test at 18800.
- **Clean room (spec §10.3):**
  - Roost's look is its own: no other product's art, mascots, icons or copy. The robot heads and signals come from Roost's own sketch.
  - Never open, fetch or search for the open-dot repos, `~/Roost-review/` or `~/.claude/projects/**`. Do not use browser MCP tools.
- **Licences:**
  - Only MIT, Apache-2.0, BSD, ISC or MPL-2.0 dependencies.
  - Today `web/tests/licenseGate.test.ts` checks three things: no `@univerjs-pro` package, not the `@univerjs/presets` meta package, and that every installed package names a licence (or has a reviewed entry). It does not check which licence. Task 2 adds that: every runtime package (not `dev`) must carry MIT, Apache-2.0, BSD-2-Clause, BSD-3-Clause, 0BSD, ISC or MPL-2.0. `tslib` (0BSD, a BSD licence) is already a runtime dependency today.
- **Disk guard:** before `npm install`, `npm uninstall` or `make e2e`, run `df -g /System/Volumes/Data | awk 'NR==2{print $4}'`. If it shows fewer than 8 GB free, stop and report.
- **Tests:**
  - Tests first: red, then green.
  - At least 80% line coverage on new code (`uv run pytest --cov=roost --cov-fail-under=80`).
  - Tests never call a real LLM and never launch a real browser (`tests/conftest.py` forces scripted and fake). Web tests run in jsdom; `web/tests/setup.ts` gives Radix the browser APIs jsdom lacks (Task 3).
- **Code rules:**
  - Files at most 800 lines (typically 200–400); functions under 50 lines.
  - Frozen dataclasses; no mutation of shared state.
  - Pydantic validation at every boundary; the gateway checks a picture's bytes, never only its Content-Type.
  - Explicit error handling with user-friendly messages.
  - No magic values: Python ones go in `roost/constants.py`, in the **Bots** section; the web kit's go in `web/src/ui/constants.ts`.
- **Tokens:** no colour and no font size is written anywhere in `web/src` but `web/src/styles/tokens.css` and the two colour-data files (`web/src/components/projects/projects.ts`, `web/src/components/robot/palette.ts`). `web/tests/tokens.test.ts` enforces it from Task 1.
- **Dark only (V4):** there is no light theme in this round, so `tokens.css` has one `:root` block.
- **Encryption and queries:**
  - A bot's picture is user content: sealed `enc:v2` with AAD `user_aad(user_id, "bots:avatar_picture")`, inside the avatar JSON. The rest of the avatar JSON (`shape`, `color`, `badge`, `screen`) stays plaintext, as CLAUDE.md allows.
  - Every query on a bot has `user_id` in its `WHERE`. Another user's bot is a **404**, never the object.
- **Vocabulary** (the CLAUDE.md table and `tests/test_vocabulary.py`):
  - Avatar; the main bot wears a star; Board; Profile; Retire this bot.
  - The statuses, verbatim: Resting · On it · Asking you · Stuck · Off duty.
  - Never "Take the wheel", ">Desk<", "Talk ·", " in Talk", "Category", "By category" or "categories" in `web/src`.
- **Git:**
  - Commit after each task's green tests. Stage files **by name**, never `git add -A`, `-a` or `.`.
  - Messages are conventional, with **no Co-Authored-By or any AI attribution line** (CLAUDE.md overrides any default).
- **Commands:**
  - Prefix every command with `cd /Users/blckit/Desktop/Code_Projects/roost &&`.
  - `uv run pytest tests/<file>.py -q` runs one file; `uv run pytest -q` runs the suite.
  - `cd web && npx vitest run tests/<file>` runs one web test; `npm test` runs them all; `npm run build && npm run size` checks the types, the build and the entry chunk's budget.

## Design meets code

What the design says, what the code holds today, and what this plan does:

1. **"Upload (the existing upload path)".** No avatar upload exists. The only upload is a PDF: `apiUpload` in `web/src/api/client.ts` and the raw-body checks in `POST /api/documents/pdf`. This plan reuses both for `POST /api/bots/{id}/picture`. The picture is stored sealed in the avatar JSON, so P1 takes no schema version (v14 is live control's `site_logins`, v15 P3's comments).
2. **The bird-to-head table.** The gateway only stores a shape; it never draws one. So the table lives once, in `web/src/components/robot/look.ts`. Python keeps the list of accepted names (`roost/constants.py`), and `tests/test_bot_look.py` reads `look.ts` to prove every accepted name has a head.
3. **"The existing natural-language parser's preview".** The parser is Python (`roost/tasks/due.py` `parse_due`), so the preview asks the gateway: a new read-only `GET /api/dates/parse`. A task's due takes words as it does today. A project's dates take only `YYYY-MM-DD`, and an expense's day is read by a different parser (`parse_spent_at`), so both forms turn words into a day with the preview's own reading before they save (`resolveDay`). What the user saw is what is saved.
4. **"Meter (budget bar)".** `BudgetBar` stays as it is: `web/e2e/projects.spec.ts` pins its classes. `Meter` is the kit's bar for new screens; P5 can move `BudgetBar` onto it.
5. **"A mono stack only for code".** P1 sets the two stacks (`--font-sans` is the system stack) and drops the bundled fonts. The 35 existing rules that set small meta text in `--font-mono` keep it until their screens are redone in P2–P5.
6. **Spacing.** The scale is defined and the kit uses it. The 79 existing padding values move to it as their screens are redone; the test pins colours and font sizes only, as the design says.
7. **Menus are not modal.** Radix's default (modal) menu traps focus while it closes, so New room's dialog lost its name field's focus. `ui/Menu` passes `modal={false}` and leaves focus where an item's action put it. Keyboard use is unchanged.
8. **The templates' looks.** Chief is a violet Classic with the glow screen, Life admin a teal Soft with pixel icons, Researcher a blue Monitor with signals, so the three styles show from the first New bot form.

## Review Focus

These are the input classes the design implies but the main tests do not exercise. The test for each one is added to the task named.

1. **An avatar stored before the robots:** a bird shape (`round`, `egg`, `pear`, `plump`, `crest`, or `tall` and `wide`, which are now head names), and no `screen`.
   - Expected: it draws one of the six heads with the glow screen, the gateway still accepts every old value, and a shape the web has never heard of still draws (Classic) rather than a blank.
   - Tests: Task 5, `it("draws every stored shape, old bird shapes included, as one of the six heads")` (`web/tests/Avatar.test.tsx`) and `test_every_shape_the_gateway_accepts_has_a_head_on_the_web` (`tests/test_bot_look.py`).
2. **A browser far from Madrid, late in its evening.** At 22:30 UTC on 15 October it is already the 16th in Madrid and still the 15th in Los Angeles.
   - Expected: Tomorrow sends Madrid's tomorrow, `2026-10-17`; a time chip sends Madrid wall time, `2026-10-17 09:00`, never `Z` or an offset; a stored `2026-10-14T23:30:00+02:00` shows `2026-10-14 23:30`; the gateway reads a picked wall time on Madrid's clock in summer and winter.
   - Tests: Task 4, `it("sends Madrid's day and Madrid wall time from a browser in Los Angeles, never a UTC instant")` (`web/tests/DateTimePicker.test.tsx`) and `test_a_picked_wall_time_is_read_on_madrid_time` (`tests/test_dates_api.py`). Task 7's `pickers.spec.ts` runs the browser on `America/Los_Angeles`.
3. **Keyboard and screen-reader use of the Radix controls.**
   - Expected: a select opens with Enter, moves with the arrows, picks with Enter and gives focus back to its button; Escape closes only the topmost layer (the open Coordinator list, not the New room dialog under it); a menu item that opens a dialog leaves the focus in that dialog.
   - Tests: Task 3, `it("works from the keyboard alone: open, arrows, Enter, and focus back on the trigger")` (`web/tests/Select.test.tsx`), `it("Escape closes the open Coordinator list, not the dialog")` (`web/tests/NewRoomDialog.test.tsx`) and `it("leaves focus where the chosen item's action put it")` (`web/tests/Menu.test.tsx`).
4. **The bundle budget.** One static import of the calendar would pull react-day-picker and date-fns into the entry chunk.
   - Expected: only `ui/date/Calendar.tsx` imports react-day-picker, nothing imports it but through `React.lazy`, and `npm run size` refuses an entry chunk that holds react-day-picker's `rdp-` class prefix.
   - Test: Task 4, `it("imports react-day-picker only in the lazy calendar chunk")` (`web/tests/bundleGuard.test.ts`), plus the `LAZY_ONLY_MARKERS` check in `web/scripts/check-bundle.mjs`.
5. **A token change that makes text unreadable.** Today's faint grey is 3.4:1 on the panel.
   - Expected: every text colour, the statuses and the meaning colours included, is 4.5:1 or more on the bg, panel, raised and overlay surfaces, and white is 4.5:1 or more on the accent and its hover.
   - Test: Task 1, `it("keeps every text colour at 4.5:1 or more on every surface")` (`web/tests/tokens.test.ts`).

---

## Shared Contract (every task uses these exact names)

### Tokens (`web/src/styles/tokens.css`, Task 1)

One `:root` block. Task 1 writes the values; `web/tests/tokens.test.ts` pins the names.

| Group | Names |
|---|---|
| Surfaces | `--color-bg`, `--color-panel`, `--color-raised`, `--color-overlay`, `--color-sunken`, `--color-scrim` |
| Text (each ≥ 4.5:1 on every surface) | `--color-text`, `--color-text-secondary`, `--color-text-faint` |
| Lines | `--color-border` (the hairline), `--color-border-strong`, `--avatar-outline` (kept) |
| Accent (violet) | `--color-accent`, `--color-accent-hover`, `--color-accent-strong`, `--color-accent-soft`, `--color-accent-tint`, `--color-accent-edge`, `--color-on-accent`, `--color-selection` |
| Meaning | `--color-ok`, `--color-warn`, `--color-danger`, `--color-danger-text`, `--color-danger-tint`, `--color-danger-edge`, `--color-info`, `--color-off` |
| Statuses | `--status-on-it`, `--status-asking`, `--status-stuck`, `--status-off` |
| Robots | `--robot-screen`, `--robot-glare`, `--robot-star`, `--robot-star-mark`, `--robot-alert` |
| Spacing (n × 4px) | `--space-1` 4, `--space-2` 8, `--space-3` 12, `--space-4` 16, `--space-5` 20, `--space-6` 24, `--space-8` 32, `--space-12` 48 |
| Corners | `--radius-xs` 6, `--radius-sm` 10, `--radius-md` 14, `--radius-lg` 20, `--radius-pill` |
| Type | `--font-sans` (system stack), `--font-mono`; `--fs-caption` 12, `--fs-label` 13, `--fs-body` 14, `--fs-lead` 16, `--fs-heading` 18, `--fs-title` 22, `--fs-display` 28 |
| Controls | `--control-sm` 28, `--control-md` 34, `--control-lg` 40 |
| Depth | `--shadow-sm`, `--shadow-md`, `--shadow-lg` |
| Motion | `--ease-standard`, `--duration-fast`, `--duration-base`, `--duration-slow` |
| Focus | `--focus-ring` |
| Kept | `--gutter`, `--reading-width`, `--talk-width`, `--bark` |

The old names go, one pass, whole names only: `--night` → `--color-bg`, `--surface` → `--color-panel`, `--raised` → `--color-raised`, `--sunken` → `--color-sunken`, `--line` → `--color-border`, `--line-strong` → `--color-border-strong`, `--text` → `--color-text`, `--muted` → `--color-text-secondary`, `--faint` → `--color-text-faint`, `--emerald` → `--color-accent`, `--emerald-bright` → `--color-accent-strong`, `--emerald-soft` → `--color-accent-soft`, `--emerald-tint` → `--color-accent-tint`, `--emerald-edge` → `--color-accent-edge`, `--on-emerald` → `--color-on-accent`, `--amber` → `--color-warn`, `--coral` → `--color-danger`, `--coral-tint` → `--color-danger-tint`, `--coral-edge` → `--color-danger-edge`, `--slate` → `--color-off`, `--font-display` and `--font-body` → `--font-sans`, `--fs-xs` → `--fs-caption`, `--fs-sm` → `--fs-label`, `--fs-base` → `--fs-body`, `--fs-md` → `--fs-lead`, `--fs-lg` → `--fs-title`, `--fs-xl` and `--fs-2xl` → `--fs-display`, `--radius-xl` → `--radius-lg`, `--pill` → `--radius-pill`, `--ease` → `--ease-standard`, `--fast` → `--duration-fast`, `--slow` → `--duration-slow`. `--twig` (unused) goes.

### The kit (`web/src/ui/`)

Every control that sits in a `Field` takes its `id`, `aria-describedby` and `aria-invalid` from it (`useFieldControl`, `controlA11y`). Outside a Field, a control's `label` prop is its accessible name.

| File | Task | Export and props |
|---|---|---|
| `cx.ts` | 2 | `cx(...parts: ReadonlyArray<string \| false \| null \| undefined>): string` |
| `constants.ts` | 2–4 | `TOAST_MS = 4000`, `TEXTAREA_MAX_ROWS = 12` (Task 2); `TOOLTIP_DELAY_MS = 400` (Task 3); `DATE_PREVIEW_DELAY_MS = 300`, `MAX_DATE_TEXT = 100` (Task 4) |
| `Button.tsx` | 2 | `Button(ButtonProps)`; `ButtonProps extends Omit<ComponentPropsWithRef<"button">, "type">` + `variant?: "primary" \| "secondary" \| "ghost" \| "danger"` (default `"secondary"`), `size?: ControlSize` (`"sm" \| "md" \| "lg"`, default `"md"`), `type?` (default `"button"`), `block?`, `loading?`. Classes `btn btn--{variant} btn--{size}`. |
| `IconButton.tsx` | 2, 3 | `IconButton({ label, icon, size = "md", variant = "ghost", pressed?, tooltip = true (Task 3), ...button props })`. Classes `icon-btn icon-btn--{size} icon-btn--{variant}`; Task 3 wraps it in a `Tooltip` that says `label`. |
| `Field.tsx` | 2 | `Field({ label, hint?, error?, optional?, className?, children })`; `useFieldControl(): FieldControl \| null`; `FieldControl { id; labelId; describedBy; invalid }`; `controlA11y(field, own?) → { id, "aria-describedby", "aria-invalid" }` |
| `Input.tsx` | 2 | `Input({ controlSize = "lg", invalid?, ...input props })` → `input input--{controlSize}` |
| `Textarea.tsx` | 2 | `Textarea({ autoGrow = true, maxRows = TEXTAREA_MAX_ROWS, invalid?, ...textarea props })`; `fitHeight(box, maxRows)` |
| `Chip.tsx` | 2 | `Chip({ selected?, size = "md", ...button props })` → `chip chip--{size}`, `aria-pressed` |
| `Badge.tsx` | 2 | `Badge({ tone = "neutral", className?, children })`; tones `neutral \| accent \| ok \| warn \| danger \| info` |
| `Meter.tsx` | 2 | `Meter({ label, value, max = 100, tone = "accent", valueText?, className? })`; `role="meter"`, value clamped to 0..max |
| `Skeleton.tsx` | 2 | `Skeleton({ lines = 1, label = "Loading", className? })`; one `role="status"` |
| `EmptyState.tsx` | 2 | `EmptyState({ title, hint?, art?, action?, className? })` |
| `Toast.tsx` | 2 | `ToastProvider({ children })` (mounted in `App.tsx`); `useToast(): { show(message, { tone?: "info" \| "ok" \| "danger", duration? }) }`; throws outside the provider |
| `Select.tsx` | 3 | `Select<T extends string>({ value, onChange, options: ReadonlyArray<SelectOption<T>>, label?, id?, disabled?, placeholder?, size = "lg" })`; `SelectOption<T> { value: T; label: string; disabled? }`. A value is never `""`. |
| `Menu.tsx` | 3 | `Menu({ label, trigger, children, side = "bottom", align = "end" })`, `MenuItem({ onSelect, disabled?, title?, children })`, `MenuLink({ to, children })`, `MenuNote({ children })` (replaces `web/src/components/Menu.tsx`, same exports) |
| `Tabs.tsx` | 3 | `Tabs<T extends string>({ label, tabs: ReadonlyArray<TabItem<T>>, value, onChange, children, panelClassName? })`; `TabItem<T> { id: T; label: string }` |
| `Sheet.tsx` | 3 | `Sheet({ open, onOpenChange, title, description?, children, footer? })`: a right-side drawer, focus back to its opener |
| `Popover.tsx` | 3 | `Popover({ trigger: ReactElement, label, children, open?, onOpenChange?, side = "bottom", align = "end" })` |
| `Tooltip.tsx` | 3 | `Tooltip({ content, children: ReactElement, side = "top" })` |

### Dates (`web/src/ui/date/`, `web/src/api/dates.ts`, `roost/gateway/routes/dates.py`, Task 4)

- **What the API sends and expects today:**
  - `TaskOut.due_date`: `"YYYY-MM-DD"`, or a Madrid-local ISO datetime with its offset (`"2026-10-14T09:00:00+02:00"`). `TaskIn.due_date` and `TaskPatchIn.due_date`: words or ISO, read on Madrid time (`parse_due`); a naive ISO time is Madrid wall time.
  - `ProjectOut.start_date` / `due_date` and `ProjectIn` / `ProjectPatchIn`: `"YYYY-MM-DD"` or `null` only (`_day` in `roost/gateway/routes/projects.py`).
  - `ExpenseIn.spent_at` (optional): words or `"YYYY-MM-DD"` (`parse_spent_at`); none is Madrid's today; a future day is refused.
- **A picker's value** (`string`, `""` is no date) is the text the gateway reads:
  - a picked day: `"2026-10-16"` (Madrid's calendar);
  - a picked day and time: `"2026-10-16 09:00"` (Madrid wall time, a space, no offset);
  - or the words typed (`"tomorrow at 9"`).
- `DatePicker({ value, onChange, label?, placeholder?, picks = FUTURE_PICKS, max?, disabled? })` and `DateTimePicker({ value, onChange, label?, placeholder?, picks = FUTURE_PICKS, disabled? })`, both on `DateField`.
- `picks.ts`: `QuickPick { label; day(today: IsoDay): IsoDay | null }`; `FUTURE_PICKS` = Today, Tomorrow, Next week (the next Monday), No date; `PAST_PICKS` = Today, Yesterday; `TIME_CHIPS` = `09:00`, `12:00`, `15:00`, `18:00` (plus No time once a time is set).
- `dates.ts`: `APP_TIME_ZONE = "Europe/Madrid"`, `IsoDay`, `WallTime`, `DueParts { day; time }`, `isIsoDay`, `todayIn(now?)`, `addDays`, `nextMonday`, `dueParts`, `joinDue`, `pickerText(due)` (a stored due as the picker's text), `friendlyDue(parts, withTime?)` (`"Fri 16 Oct 2026, 09:00"`), `dayToDate` / `dateToDay` (the calendar grid only).
- `useDateReading(text): DateReading` (`empty | reading | read | error`); `resolveDay(value): Promise<IsoDay | null>`; `parseDate(text): Promise<{ due_date: string | null }>`.
- `GET /api/dates/parse?text=` (`CurrentUser`, `text` at most `MAX_DUE_TEXT_LENGTH`): `{"due_date": parse_due(text).due_date}`, or 422 with the parser's sentence.
- `Calendar.tsx` (default export) is reached only through `lazy(() => import("./Calendar"))` in `CalendarPopover.tsx`.

### Robots (Task 5) and the picture (Task 6)

**The avatar JSON** is `{shape, color, badge, screen}` (plus the sealed `picture` key, Task 6, never sent to the web):

| | Python (`roost/constants.py`, `roost/bots/models.py`) | TypeScript (`web/src/api/types.ts`, `web/src/components/robot/look.ts`) |
|---|---|---|
| Heads | `ROBOT_HEADS = ("classic", "tall", "wide", "soft", "cube", "monitor")` | `RobotHead`, `ROBOT_HEADS`, `ROBOT_HEAD_LABELS` (Classic, Tall, Wide, Soft, Cube, Monitor) |
| Old shapes still accepted | `LEGACY_AVATAR_SHAPES = ("round", "egg", "pear", "plump", "crest")` | `LegacyAvatarShape` |
| Every accepted shape | `AVATAR_SHAPES = ROBOT_HEADS + LEGACY_AVATAR_SHAPES`; `AvatarShape` is the same 11 `Literal`s | `AvatarShape = RobotHead \| LegacyAvatarShape`, `AVATAR_SHAPES` |
| Old shape → head | not in Python: the gateway stores the shape as sent | `LEGACY_SHAPE_TO_HEAD`: round → soft, egg → soft, pear → monitor, plump → cube, crest → classic (`tall` and `wide` are heads) |
| Default head | `DEFAULT_ROBOT_HEAD: Final = "classic"` | `DEFAULT_ROBOT_HEAD`, `robotHead(shape)` (unknown → classic) |
| Screens | `ROBOT_SCREENS = ("glow", "pixel", "signal")`, `AvatarScreen`, `DEFAULT_ROBOT_SCREEN: Final = "glow"`; `Avatar.screen = "glow"` | `RobotScreen`, `ROBOT_SCREENS`, `ROBOT_SCREEN_LABELS` (Glow icons, Pixel icons, Signals), `ROBOT_SIGNAL_STYLE = "glow"` (the default for a missing screen), `robotScreen(screen)` |
| New bots' colours | `BOT_DEFAULT_COLORS` (ten), `roost/bots/look.py next_bot_color(used)` | `robot/palette.ts BOT_DEFAULT_COLORS` (the same ten), `nextBotColor(used)`, `ROBOT_COLORS` (twelve swatches), `tint`, `shade`, `surpriseLook` |
| On the wire | `look.py avatar_dict(avatar)`; `bot_out` adds `"picture"` (Task 6) | `AvatarOut { shape; color; badge; screen?; picture? }`; `lookOf(avatar)` (what an editor saves: no picture, badge "none") |

- **Moments** (`robot/moments.ts`): `RobotMoment = "rest" | "onit" | "ask" | "stuck" | "off" | "think" | "msg" | "done"`, `ROBOT_MOMENTS`, `STATUS_MOMENT` (resting → rest, on_it → onit, asking_you → ask, stuck → stuck, off_duty → off).
- **Heads** (`robot/heads.tsx`): `ScreenBox { x; y; width; height }`, `HEAD_SCREENS`, `RobotHeadShape({ head, color })`.
- **Signals** (`robot/signals.tsx`): `RobotSignal({ style: RobotScreen, moment: RobotMoment, color })`, drawn around (0, 0); `signalGlow.tsx`, `signalPixel.tsx` and `signalWave.tsx` draw the three styles.
- **`RobotFace({ head, color, screen = ROBOT_SIGNAL_STYLE, moment = "rest", star = false, size = 96, title?, still = false, picture = null (Task 6), className? })`**: an `svg.robot` with `data-head`, `data-screen` and `data-moment`; `role="img"` named by `title`, else `aria-hidden`.
- **`Avatar({ avatar, status, activity = null, size = 96, label = true, decorative = false, star = false, moment? })`**: `svg.avatar.avatar--{status}` (`avatar--reduced-motion` and `robot--still` when the OS asks for reduced motion), named by the status, `StatusLabel` beside it unless `label={false}`. The `perch` prop is gone.
- **`AvatarPicker({ value, onChange })`**: fieldsets Shape (six radios named by the head), Colour (twelve radios named by the colour) and, from Task 6, Screen (three radios: Glow icons, Pixel icons, Signals).
- **`AvatarStudio({ value, onChange, status = "resting", star = false, preview = true, onUpload?, onRemovePicture?, busy = false })`** (`web/src/components/avatar/AvatarStudio.tsx`, Task 6): the big preview (`role="group"` named "Preview"), `AvatarPicker`, Surprise me, and, when `onUpload` is given, Upload a picture (a file input named "Upload a picture") and Remove picture.
- **`newBotValues(usedColors)`** (`BotForm.tsx`, Task 5) replaces `DEFAULT_BOT_VALUES`.
- **The picture** (Task 6):
  - `roost/bots/picture.py`: `Picture(media_type, data)`, `read_picture(content_type, data)` (raises `PictureTooBig` / `NotAPicture`), `seal_picture`, `open_picture`, `picture_tag`; `AVATAR_PICTURE_MAX_BYTES = 512 * 1024`.
  - `BotStore.set_picture(user_id, bot_id, picture | None) -> Bot | None`, `BotStore.get_picture(user_id, bot_id) -> Picture | None`; `Avatar.picture` is the version tag.
  - `roost/gateway/routes/bot_picture.py`: `POST /api/bots/{id}/picture` (raw PNG, JPEG or WebP; 413, 415, 404), `DELETE /api/bots/{id}/picture`, `GET /api/bots/{id}/picture` (cached for good, `nosniff`). Each change publishes `bot_updated`.
  - Web: `uploadPicture(botId, blob)`, `removePicture(botId)` in `api/bots.ts`; `shrinkPicture(file)`, `PictureError`, `PICTURE_ACCEPT` in `web/src/lib/picture.ts`.

### File structure

| File | Task | Responsibility |
|---|---|---|
| `web/src/styles/tokens.css`, every other `web/src/styles/*.css`, `web/src/main.tsx`, `web/package.json`, `web/package-lock.json`, `THIRD_PARTY_NOTICES.md`, `web/tests/{tokens.test.ts,tokenScan.ts}` | 1 | tokens, the rename, the guard, the system font stack |
| `web/src/ui/{cx,constants,Button,IconButton,Field,Input,Textarea,Chip,Badge,Meter,Skeleton,EmptyState,Toast}.ts(x)`, `web/src/styles/{ui.css,base.css}`, `web/src/styles.css`, `web/src/App.tsx`, `web/src/components/icons.tsx`, `web/tests/{licenseGate.ts,licenseGate.test.ts,uiBasics.test.tsx,Toast.test.tsx}`, `web/package.json`, `web/package-lock.json` | 2 | the dependencies, the licence check, the base kit |
| `web/src/ui/{Select,Menu,Tabs,Sheet,Popover,Tooltip,IconButton}.tsx`, `web/src/styles/ui-overlays.css`, `web/src/components/Menu.tsx` (deleted), `web/src/pages/{Board,Project,Profile,Home,Chat}.tsx`, `web/src/components/{BotMenu,NewRoomDialog}.tsx`, `web/src/components/board/TaskEditForm.tsx`, `web/src/components/projects/ProjectEditForm.tsx`, the CSS they leave behind, `web/tests/setup.ts` and the tests named in the task, `web/e2e/team.spec.ts` | 3 | Radix controls, one tab style, no native select |
| `roost/gateway/routes/dates.py`, `roost/gateway/app.py`, `web/src/api/{dates,money}.ts`, `web/src/ui/date/*`, `web/src/styles/{date-field,calendar}.css`, the task, project and expense forms, `web/scripts/check-bundle.mjs`, the tests named in the task | 4 | date pickers on Madrid time, a lazy calendar |
| `roost/constants.py`, `roost/bots/{models,look,store,service,templates,template_file}.py`, `roost/gateway/routes/{bots,templates}.py`, `roost/talk/{team_tools,tool_catalog}.py`, `web/src/api/types.ts`, `web/src/components/robot/*`, `web/src/components/{Avatar,AvatarPicker,BotForm,ShareTemplateDialog}.tsx`, the avatar call sites, `web/src/lib/team.ts`, `web/src/pages/{Login,NewBot}.tsx`, `web/src/styles/{robot,avatar,bot-form,profile}.css`, the tests named in the task | 5 | robot avatars, the shape list, default colours |
| `roost/bots/picture.py`, `roost/gateway/routes/bot_picture.py`, `roost/bots/{models,store,service}.py`, `roost/constants.py`, `roost/gateway/app.py`, `web/src/lib/picture.ts`, `web/src/api/{types,bots}.ts`, `web/src/components/avatar/AvatarStudio.tsx`, `web/src/components/{AvatarPicker,BotForm}.tsx`, `web/src/components/robot/RobotFace.tsx`, `web/src/components/profile/AvatarEditor.tsx`, `web/src/styles/avatar-studio.css`, the tests named in the task, `web/e2e/profile.spec.ts` | 6 | the avatar editor and the picture |
| `web/e2e/{look,pickers}.spec.ts`, `CLAUDE.md`, `tests/test_docs.py` | 7 | E2E, docs, the final checks |

---

### Task 1: Design tokens: one file, the old names moved onto it, and a guard test

Design P1 "Design tokens" and Review Focus 5. Today `web/src/styles/tokens.css` holds an emerald palette under loose names (`--night`, `--muted`, `--fs-sm`, …), 25 colours and 23 font sizes are written straight into other stylesheets, the faint text is 3.4:1 on the panel, and the app ships three font families.
- **The token file** is rewritten with the design's groups: surfaces bg, panel, raised and overlay; text primary, secondary and faint (every one at least 4.5:1 on every surface); the hairline border; the violet accent; ok, warn, danger and info; the status and robot colours; spacing 4–48; radii 6, 10, 14, 20 and pill; the system font stack and the type scale 12–28; control heights 28, 34 and 40; three shadows; durations; the focus ring.
- **One scripted rename** moves every other stylesheet onto the new names: one `perl` pass, whole names only (`--line` never touches `--line-strong`), every file but `tokens.css`. The script is exact and its result is checked by the guard test, so no per-line edit is needed for the ~700 uses.
- **A second script** replaces each hard-coded colour and font size with its token, and the four places that used the accent as *text* with `--color-accent-strong` (the new violet is a fill colour: as text it would be 3.2:1). A bar in budget turns green (`--color-ok`), the meaning colour.
- **The guard**: `web/tests/tokens.test.ts` (with its scanner, `web/tests/tokenScan.ts`) fails on a hard-coded colour or font size in any stylesheet or component, on a CSS variable nobody defines, and on any text colour under 4.5:1. Until Task 5 draws the robot, the five files that draw or hold the bird's colours are allowed.
- **Fonts:** the design asks for the system stack, so `main.tsx` stops importing the three `@fontsource` families and they are uninstalled. `THIRD_PARTY_NOTICES.md` drops their section.
- Nothing else changes: the components keep their class names, so this task is a restyle only.

**Files:**
- Create: `web/tests/tokenScan.ts`, `web/tests/tokens.test.ts`
- Modify:
  - `web/src/styles/tokens.css` (rewritten)
  - every other `web/src/styles/*.css` (the two scripts; `projects.css` also by hand)
  - `web/src/main.tsx`, `THIRD_PARTY_NOTICES.md`
  - `web/package.json`, `web/package-lock.json` (`npm uninstall`)
- Test: `web/tests/tokens.test.ts`

**Interfaces:**
- Consumes: today's `web/src/styles/*.css` and `web/src/main.tsx`.
- Produces:
  - Every token name in the Shared Contract, defined in `tokens.css`. Later tasks' CSS uses only these.
  - `web/tests/tokenScan.ts`: `declarations`, `hardCodedColours`, `hardCodedFontSizes`, `usedVariables`, `definedVariables`, `componentLiterals`, `readTokens`, `resolveToken`, `contrastRatio`.
  - `web/tests/tokens.test.ts` with `COLOUR_DATA_FILES` and `PENDING_ROBOT` (Task 5 empties the second) and `TOKEN_NAMES`. Task 3 teaches it Radix's run-time variables.

- [ ] **Step 1: Path guard**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && git -C /Users/blckit/Desktop/Code_Projects/roost rev-parse --show-toplevel && git -C /Users/blckit/Desktop/Code_Projects/roost branch --show-current`
Expected: `/Users/blckit/Desktop/Code_Projects/roost` then `night-1`. If either differs, stop.

Then confirm this task has not run:

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && test ! -f web/tests/tokens.test.ts && grep -c '"@fontsource/' web/package.json`
Expected: `3`. Otherwise stop: the task already ran.

- [ ] **Step 2: Write the failing tests**

Create `web/tests/tokenScan.ts`:

```ts
// The token guard's scanner (look & feel redesign P1). It reads stylesheets and component sources as
// text and reports what tokens.test.ts refuses: a colour or a font size written anywhere but the
// token file, and a CSS variable nobody defines. Pure functions, so the test can prove they catch.

export interface Declaration {
  property: string;
  value: string;
  line: number;
}

export interface Finding {
  line: number;
  text: string;
}

const COMMENT = /\/\*[\s\S]*?\*\//g;
const DECLARATION = /([\w-]+)\s*:\s*([^;{}]+)/g;
const HEX = /(?<![\w&-])#[0-9a-f]{3,8}\b/i;
const COLOUR_FUNCTION = /\b(?:rgba?|hsla?|hwb|lab|lch|oklab|oklch|color-mix)\(/i;
const NAMED_COLOUR = /(?<![\w-])(?:white|black)(?![\w-])/i;
const SIZE_TOKEN = /^(?:var\(--fs-[a-z]+\)|inherit)$/;
const LENGTH = /(?<![\w-])\d*\.?\d+(?:px|rem|em|pt|%)/;
const VAR_USE = /var\(\s*(--[\w-]+)/g;
const VAR_DEFINITION = /(--[\w-]+)\s*:/g;
const FONT_SIZE_PROP = /\bfontSize\s*[=:]/;

// Comments become spaces of the same length, so line numbers stay true.
function withoutComments(css: string): string {
  return css.replace(COMMENT, (comment) => comment.replace(/[^\n]/g, " "));
}

export function declarations(css: string): Declaration[] {
  const source = withoutComments(css);
  return [...source.matchAll(DECLARATION)].map((match) => ({
    property: match[1].toLowerCase(),
    value: match[2].trim(),
    line: source.slice(0, match.index).split("\n").length,
  }));
}

export function hardCodedColours(css: string): Declaration[] {
  return declarations(css).filter(({ value }) => HEX.test(value) || COLOUR_FUNCTION.test(value) || NAMED_COLOUR.test(value));
}

export function hardCodedFontSizes(css: string): Declaration[] {
  return declarations(css).filter(({ property, value }) => {
    if (property === "font-size") return !SIZE_TOKEN.test(value);
    if (property === "font") return value !== "inherit" && LENGTH.test(value.replace(/var\([^)]*\)/g, ""));
    return false;
  });
}

export function usedVariables(source: string): Set<string> {
  return new Set([...withoutComments(source).matchAll(VAR_USE)].map((match) => match[1]));
}

export function definedVariables(css: string): Set<string> {
  return new Set([...withoutComments(css).matchAll(VAR_DEFINITION)].map((match) => match[1]));
}

// A component may not carry a colour literal or a fontSize: they belong in the stylesheets.
export function componentLiterals(source: string): Finding[] {
  return source.split("\n").flatMap((text, index) =>
    HEX.test(text) || FONT_SIZE_PROP.test(text) ? [{ line: index + 1, text: text.trim() }] : []);
}

export function readTokens(css: string): Map<string, string> {
  const block = withoutComments(css).split(":root {")[1]?.split("\n}")[0] ?? "";
  return new Map(declarations(block).filter(({ property }) => property.startsWith("--")).map(({ property, value }) => [property, value]));
}

export function resolveToken(tokens: ReadonlyMap<string, string>, name: string, seen: readonly string[] = []): string {
  const value = tokens.get(name);
  if (value === undefined) throw new Error(`${name} is not a token`);
  if (seen.includes(name)) throw new Error(`${name} refers to itself`);
  const reference = /^var\((--[\w-]+)\)$/.exec(value);
  return reference ? resolveToken(tokens, reference[1], [...seen, name]) : value;
}

function channel(value: number): number {
  const scaled = value / 255;
  return scaled <= 0.03928 ? scaled / 12.92 : ((scaled + 0.055) / 1.055) ** 2.4;
}

function luminance(hex: string): number {
  const match = /^#([0-9a-f]{6})$/i.exec(hex);
  if (!match) throw new Error(`${hex} is not a #rrggbb colour`);
  const number = parseInt(match[1], 16);
  const [red, green, blue] = [(number >> 16) & 255, (number >> 8) & 255, number & 255].map(channel);
  return 0.2126 * red + 0.7152 * green + 0.0722 * blue;
}

// WCAG 2.1 contrast ratio between two #rrggbb colours.
export function contrastRatio(foreground: string, background: string): number {
  const [light, dark] = [luminance(foreground), luminance(background)].sort((a, b) => b - a);
  return (light + 0.05) / (dark + 0.05);
}
```

Create `web/tests/tokens.test.ts`:

```ts
// @vitest-environment node
import { readdirSync, readFileSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import {
  componentLiterals, contrastRatio, definedVariables, hardCodedColours, hardCodedFontSizes, readTokens, resolveToken,
  usedVariables,
} from "./tokenScan";

// Look & feel redesign P1: tokens.css is the one place for colours and font sizes.
const SRC = fileURLToPath(new URL("../src/", import.meta.url));
const TOKEN_FILE = "styles/tokens.css";
// Colour data, not styling: the swatches a user picks from. Nothing else in web/src may hold a colour.
const COLOUR_DATA_FILES = ["components/projects/projects.ts"];
// Drawn with hard-coded colours until Task 5 replaces the bird with the robot. Task 5 empties this list.
const PENDING_ROBOT = [
  "components/Avatar.tsx", "components/AvatarPicker.tsx", "components/BotForm.tsx",
  "components/profile/AvatarEditor.tsx", "pages/Login.tsx",
];

const TOKEN_NAMES = [
  "--color-bg", "--color-panel", "--color-raised", "--color-overlay", "--color-sunken", "--color-scrim",
  "--color-text", "--color-text-secondary", "--color-text-faint", "--color-border", "--color-border-strong",
  "--color-accent", "--color-accent-hover", "--color-accent-strong", "--color-accent-soft", "--color-accent-tint",
  "--color-accent-edge", "--color-on-accent", "--color-selection",
  "--color-ok", "--color-warn", "--color-danger", "--color-danger-text", "--color-danger-tint", "--color-danger-edge",
  "--color-info", "--color-off",
  "--status-on-it", "--status-asking", "--status-stuck", "--status-off",
  "--robot-screen", "--robot-glare", "--robot-star", "--robot-star-mark", "--robot-alert",
  "--space-1", "--space-2", "--space-3", "--space-4", "--space-5", "--space-6", "--space-8", "--space-12",
  "--radius-xs", "--radius-sm", "--radius-md", "--radius-lg", "--radius-pill",
  "--font-sans", "--font-mono",
  "--fs-caption", "--fs-label", "--fs-body", "--fs-lead", "--fs-heading", "--fs-title", "--fs-display",
  "--control-sm", "--control-md", "--control-lg",
  "--shadow-sm", "--shadow-md", "--shadow-lg",
  "--ease-standard", "--duration-fast", "--duration-base", "--duration-slow",
  "--focus-ring",
];
const SURFACES = ["--color-bg", "--color-panel", "--color-raised", "--color-overlay"];
const TEXT_COLOURS = [
  "--color-text", "--color-text-secondary", "--color-text-faint", "--color-accent-strong", "--color-accent-soft",
  "--color-ok", "--color-warn", "--color-danger", "--color-danger-text", "--color-info", "--color-off",
  "--status-on-it", "--status-asking", "--status-stuck", "--status-off",
];
const READABLE = 4.5;

function filesUnder(dir: string, extensions: readonly string[]): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return filesUnder(path, extensions);
    return extensions.some((extension) => entry.name.endsWith(extension)) ? [path] : [];
  });
}

const name = (path: string) => relative(SRC, path);
const read = (path: string) => readFileSync(path, "utf8");
const stylesheets = filesUnder(SRC, [".css"]);
const components = filesUnder(SRC, [".ts", ".tsx"]);
const tokens = readTokens(read(join(SRC, TOKEN_FILE)));

describe("design tokens (redesign P1)", () => {
  it("defines every token the design names", () => {
    expect(TOKEN_NAMES.filter((token) => !tokens.has(token))).toEqual([]);
  });

  it("keeps hard-coded colours out of every stylesheet but the token file", () => {
    const found = stylesheets.filter((path) => name(path) !== TOKEN_FILE)
      .flatMap((path) => hardCodedColours(read(path)).map(({ line, value }) => `${name(path)}:${line} ${value}`));
    expect(found).toEqual([]);
  });

  it("keeps hard-coded font sizes out of every stylesheet", () => {
    const found = stylesheets.filter((path) => name(path) !== TOKEN_FILE)
      .flatMap((path) => hardCodedFontSizes(read(path)).map(({ line, value }) => `${name(path)}:${line} ${value}`));
    expect(found).toEqual([]);
  });

  it("keeps colour literals and font sizes out of components", () => {
    const allowed = new Set([...COLOUR_DATA_FILES, ...PENDING_ROBOT]);
    const found = components.filter((path) => !allowed.has(name(path)))
      .flatMap((path) => componentLiterals(read(path)).map(({ line, text }) => `${name(path)}:${line} ${text}`));
    expect(found).toEqual([]);
  });

  it("uses only CSS variables that a stylesheet defines", () => {
    const defined = new Set(stylesheets.flatMap((path) => [...definedVariables(read(path))]));
    const used = [...stylesheets, ...components].flatMap((path) => [...usedVariables(read(path))].map((v) => `${name(path)} ${v}`));
    expect(used.filter((entry) => !defined.has(entry.split(" ")[1]))).toEqual([]);
  });

  it("keeps every text colour at 4.5:1 or more on every surface", () => {
    const low = TEXT_COLOURS.flatMap((text) => SURFACES.flatMap((surface) => {
      const ratio = contrastRatio(resolveToken(tokens, text), resolveToken(tokens, surface));
      return ratio < READABLE ? [`${text} on ${surface}: ${ratio.toFixed(2)}`] : [];
    }));
    const onAccent = ["--color-accent", "--color-accent-hover"].flatMap((fill) => {
      const ratio = contrastRatio(resolveToken(tokens, "--color-on-accent"), resolveToken(tokens, fill));
      return ratio < READABLE ? [`--color-on-accent on ${fill}: ${ratio.toFixed(2)}`] : [];
    });
    expect([...low, ...onAccent]).toEqual([]);
  });

  it("catches a new hard-coded colour, font size or unknown variable (the scanner works)", () => {
    const css = ".x {\n  color: #fff;\n  background: rgb(0 0 0 / 0.5);\n  font-size: 13px;\n  font: 600 14px var(--font-sans);\n}";
    expect(hardCodedColours(css).map(({ line }) => line)).toEqual([2, 3]);
    expect(hardCodedFontSizes(css).map(({ line }) => line)).toEqual([4, 5]);
    expect(componentLiterals('const a = "#10b981";\n<text fontSize={11} />\n&#8230;').map(({ line }) => line)).toEqual([1, 2]);
    expect([...usedVariables("a { color: var(--nope); }")]).toEqual(["--nope"]);
    expect(contrastRatio("#ffffff", "#000000")).toBeCloseTo(21, 5);
  });
});
```

- [ ] **Step 3: Run them to see them fail**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && cd web && npx vitest run tests/tokens.test.ts`
Expected: FAIL, 4 failed and 3 passed:
- `defines every token the design names`: 64 names missing.
- `keeps hard-coded colours out of every stylesheet but the token file`: 25 findings.
- `keeps hard-coded font sizes out of every stylesheet`: 24 findings (the 23 literal sizes, and `login.css`'s `var(--fs-2xl)`, a name the new scale does not have).
- `keeps every text colour at 4.5:1 or more on every surface`: `Error: --color-text is not a token`.
- The scanner's own test, the component check (the bird's files are allowed for now) and the variables check pass.

- [ ] **Step 4: Rewrite the token file**

Replace the whole of `web/src/styles/tokens.css` with:

```css
/* ---------------------------------------------------------------------
   Design tokens (look & feel redesign P1): the one place for every
   colour, font size, space, radius, control height, shadow, duration and
   the focus ring of the web face. Every stylesheet and component takes
   its values from here; web/tests/tokens.test.ts fails on a hard-coded
   colour or font size anywhere else in web/src, and keeps every text
   colour at 4.5:1 or more on every surface. Dark only for now (V4).
   --------------------------------------------------------------------- */

:root {
  color-scheme: dark;

  /* Surfaces, darkest first */
  --color-bg: #0e0e12; /* the page */
  --color-panel: #16161b; /* lists, cards, the chat */
  --color-raised: #1f1f26; /* inputs, chips, bubbles */
  --color-overlay: #26262f; /* menus, popovers, sheets, toasts */
  --color-sunken: #09090c; /* the computer's terminal */
  --color-scrim: rgb(0 0 0 / 0.55); /* behind a sheet or a dialog */

  /* Text: each one 4.5:1 or more on every surface above */
  --color-text: #ededf2;
  --color-text-secondary: #a9a9b6;
  --color-text-faint: #9292a0;

  /* Lines */
  --color-border: #2a2a33; /* the hairline */
  --color-border-strong: #3a3a45;
  --avatar-outline: rgb(0 0 0 / 0.18); /* a faint edge on light swatches */

  /* Accent: violet, for actions, selection and focus */
  --color-accent: #7c3aed;
  --color-accent-hover: #6d28d9;
  --color-accent-strong: #a78bfa; /* links, the focus ring, accent text */
  --color-accent-soft: #c4b5fd; /* text on an accent tint */
  --color-accent-tint: rgb(124 58 237 / 0.18);
  --color-accent-edge: rgb(167 139 250 / 0.42);
  --color-on-accent: #ffffff;
  --color-selection: rgb(124 58 237 / 0.4);

  /* Meaning, never decoration */
  --color-ok: #34d399;
  --color-warn: #f5a524;
  --color-danger: #f87171;
  --color-danger-text: #fecaca;
  --color-danger-tint: rgb(248 113 113 / 0.1);
  --color-danger-edge: rgb(248 113 113 / 0.38);
  --color-info: #60a5fa;
  --color-off: #9ca3af;

  /* The five statuses (Resting is the plain secondary text) */
  --status-on-it: var(--color-accent-strong);
  --status-asking: var(--color-warn);
  --status-stuck: var(--color-danger);
  --status-off: var(--color-off);

  /* Robot avatars (components/robot) */
  --robot-screen: #0b0a11;
  --robot-glare: rgb(255 255 255 / 0.05);
  --robot-star: #f59e0b;
  --robot-star-mark: #ffffff;
  --robot-alert: var(--color-danger);

  /* Spacing: n x 4px */
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 20px;
  --space-6: 24px;
  --space-8: 32px;
  --space-12: 48px;

  /* Corners */
  --radius-xs: 6px;
  --radius-sm: 10px;
  --radius-md: 14px;
  --radius-lg: 20px;
  --radius-pill: 999px;

  /* Type: the system stack; mono for code */
  --font-sans: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", system-ui, sans-serif;
  --font-mono: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
  --fs-caption: 0.75rem; /* 12 */
  --fs-label: 0.8125rem; /* 13 */
  --fs-body: 0.875rem; /* 14 */
  --fs-lead: 1rem; /* 16 */
  --fs-heading: 1.125rem; /* 18 */
  --fs-title: 1.375rem; /* 22 */
  --fs-display: 1.75rem; /* 28 */

  /* Control heights */
  --control-sm: 28px;
  --control-md: 34px;
  --control-lg: 40px;

  /* Depth */
  --shadow-sm: 0 1px 2px rgb(0 0 0 / 0.4);
  --shadow-md: 0 8px 24px rgb(0 0 0 / 0.45), 0 1px 3px rgb(0 0 0 / 0.3);
  --shadow-lg: 0 18px 48px rgb(0 0 0 / 0.55), 0 2px 6px rgb(0 0 0 / 0.35);

  /* Motion */
  --ease-standard: cubic-bezier(0.2, 0.7, 0.2, 1);
  --duration-fast: 140ms;
  --duration-base: 180ms;
  --duration-slow: 220ms;

  /* Focus */
  --focus-ring: 0 0 0 2px var(--color-bg), 0 0 0 4px var(--color-accent-strong);

  /* Layout */
  --gutter: 40px;
  --reading-width: 760px;
  --talk-width: 960px;

  /* The login card's top edge */
  --bark: linear-gradient(180deg, #8b7a69 0%, #6a5a4b 55%, #4c4037 100%);
}

@media (max-width: 768px) {
  :root {
    --gutter: 16px;
  }
}
```

- [ ] **Step 5: Move every stylesheet onto the tokens**

Run the two scripts as written (each is one shell call), then the one edit by hand. Afterwards nothing in `web/src/styles` but `tokens.css` names an old variable or a literal colour:

Rename every old variable to its token, in every stylesheet but tokens.css (one pass, whole names only).

Run:

```bash
cd /Users/blckit/Desktop/Code_Projects/roost/web/src/styles && \
perl -pi -e 'BEGIN { %m = ("night"=>"color-bg", "surface"=>"color-panel", "raised"=>"color-raised", "sunken"=>"color-sunken", "line-strong"=>"color-border-strong", "line"=>"color-border", "text"=>"color-text", "muted"=>"color-text-secondary", "faint"=>"color-text-faint", "emerald-bright"=>"color-accent-strong", "emerald-soft"=>"color-accent-soft", "emerald-tint"=>"color-accent-tint", "emerald-edge"=>"color-accent-edge", "on-emerald"=>"color-on-accent", "emerald"=>"color-accent", "amber"=>"color-warn", "coral-tint"=>"color-danger-tint", "coral-edge"=>"color-danger-edge", "coral"=>"color-danger", "slate"=>"color-off", "font-display"=>"font-sans", "font-body"=>"font-sans", "fs-xs"=>"fs-caption", "fs-sm"=>"fs-label", "fs-base"=>"fs-body", "fs-md"=>"fs-lead", "fs-lg"=>"fs-title", "fs-xl"=>"fs-display", "fs-2xl"=>"fs-display", "radius-xl"=>"radius-lg", "pill"=>"radius-pill", "ease"=>"ease-standard", "fast"=>"duration-fast", "slow"=>"duration-slow") } s/(?<![\w-])--(night|surface|raised|sunken|line-strong|line|text|muted|faint|emerald-bright|emerald-soft|emerald-tint|emerald-edge|on-emerald|emerald|amber|coral-tint|coral-edge|coral|slate|font-display|font-body|fs-xs|fs-sm|fs-base|fs-md|fs-lg|fs-xl|fs-2xl|radius-xl|pill|ease|fast|slow)(?![\w-])/"--".$m{$1}/ge' $(ls *.css | grep -v '^tokens\.css$')
```

Replace each hard-coded colour and font size, and the accent used as text, with its token.

Run:

```bash
cd /Users/blckit/Desktop/Code_Projects/roost/web/src/styles && \
while IFS='|' read -r from to; do
  [ -z "$from" ] && continue
  FROM="$from" TO="$to" perl -pi -e 's/\Q$ENV{FROM}\E/$ENV{TO}/g' $(ls *.css | grep -v '^tokens\.css$')
done <<'PAIRS'
box-shadow: 0 2px 0 rgba(0, 0, 0, 0.45);|box-shadow: var(--shadow-sm);
rgba(0, 0, 0, 0.25)|var(--avatar-outline)
box-shadow: 0 12px 24px rgba(0, 0, 0, 0.5);|box-shadow: var(--shadow-md);
border: 1px solid #222;|border: 1px solid var(--color-border);
border-bottom: 1px solid #1c1c1c;|border-bottom: 1px solid var(--color-border);
color: #4a4a4a;|color: var(--color-text-faint);
color: #565656;|color: var(--color-text-faint);
color: #d6d6d6;|color: var(--color-text);
color: #fca5a5;|color: var(--color-danger);
color: #e6fbf2;|color: var(--color-text);
box-shadow: 0 0 0 3px rgba(16, 185, 129, 0.2);|box-shadow: var(--focus-ring);
box-shadow: 0 0 0 3px rgba(16, 185, 129, 0.25);|box-shadow: var(--focus-ring);
background: rgba(0, 0, 0, 0.5);|background: var(--color-scrim);
background: rgba(0, 0, 0, 0.6);|background: var(--color-scrim);
box-shadow: 0 24px 60px rgba(0, 0, 0, 0.5);|box-shadow: var(--shadow-lg);
box-shadow: 0 12px 32px rgba(0, 0, 0, 0.45);|box-shadow: var(--shadow-md);
box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.55);|box-shadow: 0 0 0 0 var(--color-accent-edge);
box-shadow: 0 0 0 4px rgba(16, 185, 129, 0);|box-shadow: 0 0 0 4px transparent;
background: rgba(16, 185, 129, 0.35);|background: var(--color-selection);
background: rgba(248, 113, 113, 0.12);|background: var(--color-danger-tint);
color: #fecaca;|color: var(--color-danger-text);
font-size: 0.875rem;|font-size: var(--fs-body);
font-size: 0.9375rem;|font-size: var(--fs-body);
font-size: 1rem;|font-size: var(--fs-lead);
font-size: 1.25rem;|font-size: var(--fs-heading);
font-size: 1.3125rem;|font-size: var(--fs-title);
font-size: 1.375rem;|font-size: var(--fs-title);
.kind-icon { flex: none; color: var(--color-accent); }|.kind-icon { flex: none; color: var(--color-accent-strong); }
.message__handoff-arrow { flex: none; color: var(--color-accent);|.message__handoff-arrow { flex: none; color: var(--color-accent-strong);
  color: var(--color-accent);|  color: var(--color-accent-strong);
  --status-color: var(--color-accent);|  --status-color: var(--status-on-it);
PAIRS
```

A bar in budget is green (the meaning colour), not the violet accent.

`web/src/styles/projects.css`. Find:

```css
.budget-bar__fill {
  height: 100%;
  border-radius: inherit;
  background: var(--color-accent);
```

Replace with:

```css
.budget-bar__fill {
  height: 100%;
  border-radius: inherit;
  background: var(--color-ok);
```

- [ ] **Step 6: Check the scripts' result**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && cd web/src/styles && grep -nE 'var\(--(night|surface|raised|sunken|line|text|muted|faint|emerald|amber|coral|slate|font-display|font-body|fs-(xs|sm|base|md|lg|xl|2xl)|radius-xl|pill|ease|fast|slow)\)' *.css | grep -v '^tokens.css' ; grep -nE '#[0-9a-fA-F]{3,8}\b|rgba?\(' *.css | grep -v '^tokens.css'`
Expected: no output.

- [ ] **Step 7: The system font stack**

`web/src/main.tsx`. Find:

```tsx
import { App } from "./App";
// Fonts are bundled with the app (OFL-1.1 font files via @fontsource;
// see THIRD_PARTY_NOTICES.md) — Latin + Latin Extended only, which covers
// English and Spanish. Nothing is loaded from a font CDN.
import "@fontsource/inter/latin-400.css";
import "@fontsource/inter/latin-ext-400.css";
import "@fontsource/inter/latin-500.css";
import "@fontsource/inter/latin-ext-500.css";
import "@fontsource/inter/latin-600.css";
import "@fontsource/inter/latin-ext-600.css";
import "@fontsource/bricolage-grotesque/latin-600.css";
import "@fontsource/bricolage-grotesque/latin-ext-600.css";
import "@fontsource/bricolage-grotesque/latin-700.css";
import "@fontsource/bricolage-grotesque/latin-ext-700.css";
import "@fontsource/jetbrains-mono/latin-400.css";
import "@fontsource/jetbrains-mono/latin-ext-400.css";
import "@fontsource/jetbrains-mono/latin-500.css";
import "@fontsource/jetbrains-mono/latin-ext-500.css";
import "./styles.css";
```

Replace with:

```tsx
import { App } from "./App";
// Type is the system stack (styles/tokens.css --font-sans, redesign P1): no font files ship.
import "./styles.css";
```

`THIRD_PARTY_NOTICES.md`. Find:

```markdown
## Bundled font files (SIL Open Font License 1.1)

The web face bundles these fonts as local `.woff2`/`.woff` files (Latin
and Latin Extended subsets only), installed from the `@fontsource`
packages and served with the app — never fetched from a font CDN. The
font files are under the SIL Open Font License, Version 1.1 (allowed for
bundled font files only, Ruling 19); the full license text ships in each
package's `LICENSE` file under `web/node_modules/@fontsource/*/`.

| Font | Package | Copyright |
|---|---|---|
| Inter | `@fontsource/inter` 5.3.0 | Copyright 2016 The Inter Project Authors (https://github.com/rsms/inter) |
| Bricolage Grotesque | `@fontsource/bricolage-grotesque` 5.3.0 | Copyright 2022 The Bricolage Grotesque Project Authors (https://github.com/ateliertriay/bricolage) |
| JetBrains Mono | `@fontsource/jetbrains-mono` 5.3.0 | Copyright 2020 The JetBrains Mono Project Authors (https://github.com/JetBrains/JetBrainsMono) |

```

Replace with:

```markdown
## Fonts

The web face uses the system font stack (`web/src/styles/tokens.css`,
look & feel redesign P1) and ships no font files.

```

- [ ] **Step 8: Uninstall the bundled fonts**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && df -g /System/Volumes/Data | awk 'NR==2{print $4}'`
Expected: at least 8. Otherwise stop and report.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && cd web && npm uninstall @fontsource/bricolage-grotesque @fontsource/inter @fontsource/jetbrains-mono`
Expected: `removed 3 packages`.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && grep -rn "fontsource" web/src web/package.json`
Expected: no output.

- [ ] **Step 9: Run the tests to see them pass**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && cd web && npx vitest run tests/tokens.test.ts`
Expected: PASS, 7 tests.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && cd web && npm test`
Expected: every test file passes. No component changed, so no other test moves.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && cd web && npm run build && npm run size`
Expected: the build succeeds, and the entry chunk is within `bundle-budget.json`.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_vocabulary.py -q`
Expected: PASS.

- [ ] **Step 10: Commit**

Run:

```bash
cd /Users/blckit/Desktop/Code_Projects/roost && \
git add web/tests/tokenScan.ts web/tests/tokens.test.ts web/src/main.tsx THIRD_PARTY_NOTICES.md \
  web/package.json web/package-lock.json \
  web/src/styles/avatar.css web/src/styles/base.css web/src/styles/board.css web/src/styles/bot-form.css \
  web/src/styles/chat.css web/src/styles/computer.css web/src/styles/documents.css web/src/styles/home.css \
  web/src/styles/layout.css web/src/styles/login.css web/src/styles/notes.css web/src/styles/profile.css \
  web/src/styles/projects.css web/src/styles/rooms.css web/src/styles/team.css web/src/styles/tokens.css && \
git commit -m "feat: design tokens in one file, every stylesheet on them, a guard test, and the system font stack"
```

### Task 2: The dependencies, the licence check and the base kit

Design P1 "Components" (the base half) and "Dependencies". This task installs everything P1 needs from npm at once (the six Radix primitives used in Task 3 and react-day-picker for Task 4), proves their licences, and builds the kit's plain components in `web/src/ui/`.
- **Licences.** `web/tests/licenseGate.ts` gains `disallowedRuntimeLicenses`: every package the app ships (not `dev`) must carry MIT, Apache-2.0, BSD-2-Clause, BSD-3-Clause, 0BSD, ISC or MPL-2.0, or have a reviewed entry. The test also pins that Radix and react-day-picker are installed and MIT. After Task 1 dropped the OFL fonts, the shipped tree is MIT, ISC, Apache-2.0, BSD and 0BSD (`tslib`) only.
- **The kit keeps base.css's class names** (`btn`, `icon-btn`, `input`, `field`, `chip`), so every existing button and field restyles with the new sizes: `.btn` is the 34 px control (`--control-md`), `.btn--small`/`.btn--sm` 28 px, `.btn--lg` 40 px, inputs 40 px. `.btn--secondary` is the old quiet look (`.btn--quiet` stays as its alias); `.btn--ghost` is new. The primary hover gets darker, not lighter: white on the light violet was 2.7:1.
- **Field** wires a control to its label, hint and error through context, so `<Field label="Title"><Input …/></Field>` is labelled and described with no ids at the call site.
- **Textarea** grows with its text in every browser (`fitHeight`: height `auto`, then the text's height, capped at `TEXTAREA_MAX_ROWS` lines, then it scrolls).
- **Toast** is one polite live region; `ToastProvider` wraps the app in `App.tsx`. Nothing in P1 shows a toast yet; P2 and P3 do.

**Files:**
- Create: `web/src/ui/{cx,constants}.ts`, `web/src/ui/{Button,IconButton,Field,Input,Textarea,Chip,Badge,Meter,Skeleton,EmptyState,Toast}.tsx`, `web/src/styles/ui.css`, `web/tests/uiBasics.test.tsx`, `web/tests/Toast.test.tsx`
- Modify: `web/tests/licenseGate.ts`, `web/tests/licenseGate.test.ts`, `web/src/components/icons.tsx` (`CloseIcon`), `web/src/App.tsx`, `web/src/styles/base.css`, `web/src/styles.css`, `web/package.json`, `web/package-lock.json`
- Test: `web/tests/uiBasics.test.tsx`, `web/tests/Toast.test.tsx`, `web/tests/licenseGate.test.ts`

**Interfaces:**
- Consumes: Task 1's tokens (`--control-*`, `--space-*`, `--color-accent-hover`, `--fs-*`, `--focus-ring`).
- Produces (exact props in the Shared Contract): `cx`, `TOAST_MS`, `TEXTAREA_MAX_ROWS`, `Button`, `ButtonVariant`, `ControlSize`, `IconButton` (no tooltip yet: Task 3 replaces the file), `Field`, `useFieldControl`, `FieldControl`, `controlA11y`, `Input`, `Textarea`, `fitHeight`, `Chip`, `Badge`, `Meter`, `Skeleton`, `EmptyState`, `ToastProvider`, `useToast`, `CloseIcon`; `disallowedRuntimeLicenses` and `ALLOWED_RUNTIME_LICENSES` in `web/tests/licenseGate.ts`.

- [ ] **Step 1: Path guard**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && git -C /Users/blckit/Desktop/Code_Projects/roost rev-parse --show-toplevel && git -C /Users/blckit/Desktop/Code_Projects/roost branch --show-current`
Expected: `/Users/blckit/Desktop/Code_Projects/roost` then `night-1`. If either differs, stop.

Then confirm Task 1 has landed and this task has not:

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && test -f web/tests/tokens.test.ts && test ! -d web/src/ui && grep -c "@radix-ui" web/package.json`
Expected: `0`. Otherwise stop.

- [ ] **Step 2: Write the failing tests**

`web/tests/licenseGate.test.ts`. Find:

```ts
import { metaPresets, proPackages, unreviewedWithoutLicense, type LockFile } from "./licenseGate";
```

Replace with:

```ts
import {
  disallowedRuntimeLicenses, metaPresets, proPackages, unreviewedWithoutLicense, type LockFile,
} from "./licenseGate";
```

`web/tests/licenseGate.test.ts`. Find:

```ts
  it("every installed package names its license or has a reviewed entry", () => {
    expect(unreviewedWithoutLicense(lock)).toEqual([]);
    expect(unreviewedWithoutLicense({ packages: { "node_modules/mystery": {} } })).toEqual(["node_modules/mystery"]);
  });
```

Replace with:

```ts
  it("every installed package names its license or has a reviewed entry", () => {
    expect(unreviewedWithoutLicense(lock)).toEqual([]);
    expect(unreviewedWithoutLicense({ packages: { "node_modules/mystery": {} } })).toEqual(["node_modules/mystery"]);
  });

  it("every package the app ships is MIT, Apache-2.0, BSD, ISC or MPL-2.0 (Radix and react-day-picker included)", () => {
    expect(disallowedRuntimeLicenses(lock)).toEqual([]);
    expect(lock.packages?.["node_modules/@radix-ui/react-select"]?.license).toBe("MIT");
    expect(lock.packages?.["node_modules/react-day-picker"]?.license).toBe("MIT");
    expect(disallowedRuntimeLicenses({ packages: {
      "": {},
      "node_modules/gpl-thing": { license: "GPL-3.0" },
      "node_modules/vitest": { license: "MIT", dev: true },
      "node_modules/caniuse-lite": { license: "CC-BY-4.0", dev: true },
      "node_modules/@univerjs/telemetry": {},
    } })).toEqual(["node_modules/gpl-thing GPL-3.0"]);
  });
```

Create `web/tests/uiBasics.test.tsx`:

```tsx
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { Badge } from "../src/ui/Badge";
import { Button } from "../src/ui/Button";
import { Chip } from "../src/ui/Chip";
import { EmptyState } from "../src/ui/EmptyState";
import { Field } from "../src/ui/Field";
import { IconButton } from "../src/ui/IconButton";
import { Input } from "../src/ui/Input";
import { Meter } from "../src/ui/Meter";
import { Skeleton } from "../src/ui/Skeleton";
import { Textarea, fitHeight } from "../src/ui/Textarea";
import { PlusIcon } from "../src/components/icons";

afterEach(() => cleanup());

describe("Button and IconButton", () => {
  it("draws its variant and size, is a plain button by default, and is busy while loading", async () => {
    const onClick = vi.fn();
    const { rerender } = render(<Button variant="primary" size="sm" onClick={onClick}>Save</Button>);
    const button = screen.getByRole("button", { name: "Save" });
    expect(button).toHaveClass("btn", "btn--primary", "btn--sm");
    expect(button).toHaveAttribute("type", "button");
    await userEvent.click(button);
    expect(onClick).toHaveBeenCalledTimes(1);
    rerender(<Button variant="primary" loading onClick={onClick}>Save</Button>);
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Save" })).toHaveAttribute("aria-busy", "true");
  });

  it("an icon button is named by its label and can be a toggle", () => {
    render(<IconButton label="Search" icon={<PlusIcon />} pressed={false} />);
    const button = screen.getByRole("button", { name: "Search" });
    expect(button).toHaveClass("icon-btn", "icon-btn--md", "icon-btn--ghost");
    expect(button).toHaveAttribute("aria-pressed", "false");
  });
});

describe("Field, Input and Textarea", () => {
  it("labels its control and wires the hint and the error to it", () => {
    render(<Field label="Title" hint="Short is best" error="A task needs a title." optional><Input value="" onChange={vi.fn()} /></Field>);
    const box = screen.getByLabelText("Title");
    expect(box).toHaveAccessibleDescription("Short is best A task needs a title.");
    expect(box).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByRole("alert")).toHaveTextContent("A task needs a title.");
    expect(screen.getByText("optional")).toBeInTheDocument();
  });

  it("an input outside a Field keeps its own id and name", () => {
    render(<Input id="own" aria-label="Search notes" />);
    expect(screen.getByRole("textbox", { name: "Search notes" })).toHaveAttribute("id", "own");
  });

  it("a textarea grows with its text up to its cap, then scrolls", () => {
    const box = document.createElement("textarea");
    document.body.appendChild(box);
    box.style.lineHeight = "20px";
    box.style.padding = "0";
    Object.defineProperty(box, "scrollHeight", { configurable: true, get: () => 64 });
    fitHeight(box, 12);
    expect(box.style.height).toBe("64px");
    expect(box.style.overflowY).toBe("hidden");
    Object.defineProperty(box, "scrollHeight", { configurable: true, get: () => 900 });
    fitHeight(box, 12);
    expect(box.style.height).toBe("240px");
    expect(box.style.overflowY).toBe("auto");
    box.remove();
  });

  it("a textarea resizes when its value changes", async () => {
    function Grows() {
      const [text, setText] = useState("");
      return <Field label="Instructions"><Textarea value={text} onChange={(event) => setText(event.target.value)} /></Field>;
    }
    render(<Grows />);
    const box = screen.getByLabelText("Instructions");
    Object.defineProperty(box, "scrollHeight", { configurable: true, get: () => 48 });
    await userEvent.type(box, "a");
    expect(box).toHaveStyle({ height: "48px" });
    expect(box).toHaveClass("input--grow");
  });
});

describe("Chip, Badge, Meter, Skeleton and EmptyState", () => {
  it("a chip is a pressable pill", () => {
    render(<Chip selected>Tomorrow</Chip>);
    expect(screen.getByRole("button", { name: "Tomorrow" })).toHaveAttribute("aria-pressed", "true");
  });

  it("a badge carries its tone", () => {
    render(<Badge tone="warn">2 left</Badge>);
    expect(screen.getByText("2 left")).toHaveClass("badge", "badge--warn");
  });

  it("a meter clamps what it draws and announces, and says its value text", () => {
    render(<Meter label="This month" value={250} tone="over" valueText="Over by €150.00" />);
    const meter = screen.getByRole("meter", { name: "This month" });
    expect(meter).toHaveAttribute("aria-valuenow", "100");
    expect(meter).toHaveAttribute("aria-valuetext", "Over by €150.00");
    expect(meter.querySelector(".meter__fill--over")).toHaveStyle({ width: "100%" });
  });

  it("a skeleton is one loading status with hidden bars", () => {
    render(<Skeleton lines={3} label="Loading tasks" />);
    const status = screen.getByRole("status", { name: "Loading tasks" });
    expect(status.querySelectorAll(".skeleton")).toHaveLength(3);
  });

  it("an empty state shows its title, hint and action", () => {
    render(<EmptyState title="No notes yet" hint="Write one, or ask a bot." action={<Button>New note</Button>} />);
    expect(screen.getByText("No notes yet")).toBeInTheDocument();
    expect(screen.getByText("Write one, or ask a bot.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "New note" })).toBeInTheDocument();
  });
});
```

Create `web/tests/Toast.test.tsx`:

```tsx
import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ToastProvider, useToast } from "../src/ui/Toast";

afterEach(() => { cleanup(); vi.useRealTimers(); });

function Saver() {
  const toast = useToast();
  return <button type="button" onClick={() => toast.show("Look saved", { tone: "ok" })}>Save look</button>;
}

describe("Toast", () => {
  it("says a note in one polite live region, and Dismiss takes it away", async () => {
    render(<ToastProvider><Saver /></ToastProvider>);
    await userEvent.click(screen.getByRole("button", { name: "Save look" }));
    const region = screen.getByRole("status");
    expect(region).toHaveAttribute("aria-live", "polite");
    expect(region).toHaveTextContent("Look saved");
    expect(region.querySelector(".toast--ok")).not.toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(region).not.toHaveTextContent("Look saved");
  });

  it("leaves by itself after its time", () => {
    vi.useFakeTimers();
    render(<ToastProvider><Saver /></ToastProvider>);
    act(() => screen.getByRole("button", { name: "Save look" }).click());
    expect(screen.getByRole("status")).toHaveTextContent("Look saved");
    act(() => { vi.advanceTimersByTime(4000); });
    expect(screen.getByRole("status")).not.toHaveTextContent("Look saved");
  });

  it("refuses to work without its provider, with a sentence that says where it is", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    expect(() => render(<Saver />)).toThrow("useToast needs a ToastProvider above it");
  });
});
```

- [ ] **Step 3: Run them to see them fail**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && cd web && npx vitest run tests/uiBasics.test.tsx tests/Toast.test.tsx tests/licenseGate.test.ts`
Expected: FAIL:
- `uiBasics.test.tsx`: `Failed to resolve import "../src/ui/Badge"`.
- `Toast.test.tsx`: `Failed to resolve import "../src/ui/Toast"`.
- `licenseGate.test.ts`: 1 failed, 3 passed; the new test fails with `TypeError: disallowedRuntimeLicenses is not a function`.

- [ ] **Step 4: Install the dependencies**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && df -g /System/Volumes/Data | awk 'NR==2{print $4}'`
Expected: at least 8. Otherwise stop and report.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && cd web && npm install --save-exact @radix-ui/react-select@2.3.7 @radix-ui/react-dropdown-menu@2.1.24 @radix-ui/react-tabs@1.1.21 @radix-ui/react-dialog@1.1.23 @radix-ui/react-popover@1.1.23 @radix-ui/react-tooltip@1.2.16 react-day-picker@9.13.2`
Expected: the seven packages appear in `web/package.json` `dependencies` at exactly these versions. (They are weeks old; the newest Radix line, 2026-10-12, is days old.)

- [ ] **Step 5: The runtime licence check**

`web/tests/licenseGate.ts`. Find:

```ts
export interface LockFile {
  packages?: Record<string, { license?: string }>;
}
```

Replace with:

```ts
export interface LockFile {
  packages?: Record<string, { license?: string; dev?: boolean }>;
}

// Spec §10.3: Roost ships only MIT, Apache-2.0, BSD (0BSD, 2- and 3-clause), ISC or MPL-2.0 code.
// Dev-only tools (the test runner, the bundler) are not shipped, so only runtime packages count.
export const ALLOWED_RUNTIME_LICENSES: ReadonlySet<string> = new Set([
  "MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "0BSD", "ISC", "MPL-2.0",
]);
```

`web/tests/licenseGate.ts`. Find:

```ts
export function unreviewedWithoutLicense(lock: LockFile): string[] {
```

Replace with:

```ts
export function disallowedRuntimeLicenses(lock: LockFile): string[] {
  return Object.entries(lock.packages ?? {})
    .filter(([path, meta]) => path !== "" && !meta.dev && !(path in REVIEWED_NO_LICENSE_FIELD))
    .filter(([, meta]) => !ALLOWED_RUNTIME_LICENSES.has(meta.license ?? ""))
    .map(([path, meta]) => `${path} ${meta.license ?? "(none)"}`)
    .sort();
}

export function unreviewedWithoutLicense(lock: LockFile): string[] {
```

- [ ] **Step 6: The base kit**

The components. Each one is small and keeps base.css's class names.

Create `web/src/ui/cx.ts`:

```ts
// Joins class names, leaving out the false, null and undefined ones.
export function cx(...parts: ReadonlyArray<string | false | null | undefined>): string {
  return parts.filter((part): part is string => typeof part === "string" && part.length > 0).join(" ");
}
```

Create `web/src/ui/constants.ts`:

```ts
// The UI kit's numbers (look & feel redesign P1), in one place.
export const TOAST_MS = 4000; // how long a toast stays
export const TEXTAREA_MAX_ROWS = 12; // an auto-growing textarea scrolls past this
```

Create `web/src/ui/Button.tsx`:

```tsx
import type { ComponentPropsWithRef } from "react";
import { cx } from "./cx";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
export type ControlSize = "sm" | "md" | "lg";

export interface ButtonProps extends Omit<ComponentPropsWithRef<"button">, "type"> {
  variant?: ButtonVariant;
  size?: ControlSize;
  type?: "button" | "submit" | "reset";
  block?: boolean; // full width
  loading?: boolean; // disabled and aria-busy while an action runs
}

// The one button (redesign P1): base.css's .btn classes, sized by the control-height tokens.
export function Button({
  variant = "secondary", size = "md", type = "button", block = false, loading = false, disabled, className, ...rest
}: ButtonProps) {
  return (
    <button {...rest} type={type} disabled={disabled || loading} aria-busy={loading || undefined}
      className={cx("btn", `btn--${variant}`, `btn--${size}`, block && "btn--block", className)} />
  );
}
```

Create `web/src/ui/IconButton.tsx`:

```tsx
import type { ComponentPropsWithRef, ReactNode } from "react";
import { cx } from "./cx";
import type { ControlSize } from "./Button";

export interface IconButtonProps extends Omit<ComponentPropsWithRef<"button">, "aria-label" | "children" | "type"> {
  label: string; // the accessible name: an icon alone says nothing
  icon: ReactNode;
  size?: ControlSize;
  variant?: "ghost" | "secondary";
  pressed?: boolean; // a toggle: sets aria-pressed
}

// A square button with an icon and a name (redesign P1). Task 3 gives it a tooltip that says the name.
export function IconButton({ label, icon, size = "md", variant = "ghost", pressed, className, ...rest }: IconButtonProps) {
  return (
    <button {...rest} type="button" aria-label={label} aria-pressed={pressed}
      className={cx("icon-btn", `icon-btn--${size}`, `icon-btn--${variant}`, className)}>
      {icon}
    </button>
  );
}
```

Create `web/src/ui/Field.tsx`:

```tsx
import { createContext, useContext, useId, type ReactNode } from "react";
import { cx } from "./cx";

// What a control inside a Field takes from it: its id (the label points at it), what describes it,
// and whether it holds an error. Input, Textarea, Select and the date pickers read it.
export interface FieldControl {
  id: string;
  labelId: string;
  describedBy: string | undefined;
  invalid: boolean;
}

const FieldContext = createContext<FieldControl | null>(null);

export function useFieldControl(): FieldControl | null {
  return useContext(FieldContext);
}

export interface FieldProps {
  label: ReactNode;
  hint?: ReactNode; // a line under the control
  error?: string | null; // replaces nothing: shown under the hint, and marks the control invalid
  optional?: boolean; // says "optional" beside the label
  className?: string;
  children: ReactNode; // one control
}

// A labelled control (redesign P1): label, the control, a hint and an error, wired for screen readers.
export function Field({ label, hint, error = null, optional = false, className, children }: FieldProps) {
  const id = useId();
  const hintId = hint ? `${id}-hint` : null;
  const errorId = error ? `${id}-error` : null;
  const describedBy = [hintId, errorId].filter(Boolean).join(" ") || undefined;
  const control: FieldControl = { id: `${id}-control`, labelId: `${id}-label`, describedBy, invalid: Boolean(error) };
  return (
    <div className={cx("field", className)}>
      <div className="field__head">
        <label className="field__label" id={control.labelId} htmlFor={control.id}>{label}</label>
        {optional ? <span className="field__optional">optional</span> : null}
      </div>
      <FieldContext.Provider value={control}>{children}</FieldContext.Provider>
      {hintId ? <p id={hintId} className="field__hint">{hint}</p> : null}
      {errorId ? <p id={errorId} className="field__error" role="alert">{error}</p> : null}
    </div>
  );
}

export interface ControlA11y {
  id: string | undefined;
  "aria-describedby": string | undefined;
  "aria-invalid": true | undefined;
}

// The id and aria a control inside a Field should carry, merged with the control's own.
export function controlA11y(
  field: FieldControl | null, own: { id?: string; describedBy?: string; invalid?: boolean } = {},
): ControlA11y {
  const describedBy = [field?.describedBy, own.describedBy].filter(Boolean).join(" ") || undefined;
  return {
    id: own.id ?? field?.id,
    "aria-describedby": describedBy,
    "aria-invalid": own.invalid || field?.invalid ? true : undefined,
  };
}
```

Create `web/src/ui/Input.tsx`:

```tsx
import type { ComponentPropsWithRef } from "react";
import { cx } from "./cx";
import { controlA11y, useFieldControl } from "./Field";
import type { ControlSize } from "./Button";

export interface InputProps extends Omit<ComponentPropsWithRef<"input">, "size"> {
  controlSize?: ControlSize; // "size" is the native attribute's name, so the height is controlSize
  invalid?: boolean;
}

// A text box (redesign P1). Inside a Field it takes the Field's id, hint and error.
export function Input({ controlSize = "lg", invalid, id, className, "aria-describedby": describedBy, ...rest }: InputProps) {
  const a11y = controlA11y(useFieldControl(), { id, describedBy, invalid });
  return <input {...rest} {...a11y} className={cx("input", `input--${controlSize}`, className)} />;
}
```

Create `web/src/ui/Textarea.tsx`:

```tsx
import { useLayoutEffect, useRef, type ComponentPropsWithRef } from "react";
import { cx } from "./cx";
import { controlA11y, useFieldControl } from "./Field";
import { TEXTAREA_MAX_ROWS } from "./constants";

export interface TextareaProps extends Omit<ComponentPropsWithRef<"textarea">, "ref"> {
  autoGrow?: boolean; // grows with its text, up to maxRows, then scrolls
  maxRows?: number;
  invalid?: boolean;
}

// Fits the box to its text: height "auto" first, so it can also shrink, then the text's height, capped.
export function fitHeight(box: HTMLTextAreaElement, maxRows: number): void {
  const style = window.getComputedStyle(box);
  const line = Number.parseFloat(style.lineHeight) || Number.parseFloat(style.fontSize) * 1.5 || 20;
  const padding = (Number.parseFloat(style.paddingTop) || 0) + (Number.parseFloat(style.paddingBottom) || 0);
  const cap = line * maxRows + padding;
  box.style.height = "auto";
  const wanted = box.scrollHeight;
  box.style.height = `${Math.min(wanted, cap)}px`;
  box.style.overflowY = wanted > cap ? "auto" : "hidden";
}

// A multi-line box (redesign P1) that grows as you type, in every browser.
export function Textarea({
  autoGrow = true, maxRows = TEXTAREA_MAX_ROWS, invalid, id, className, value, "aria-describedby": describedBy, ...rest
}: TextareaProps) {
  const ref = useRef<HTMLTextAreaElement>(null);
  const a11y = controlA11y(useFieldControl(), { id, describedBy, invalid });
  useLayoutEffect(() => {
    if (autoGrow && ref.current) fitHeight(ref.current, maxRows);
  }, [autoGrow, maxRows, value]);
  return (
    <textarea {...rest} {...a11y} ref={ref} value={value}
      className={cx("input", "input--area", autoGrow && "input--grow", className)} />
  );
}
```

Create `web/src/ui/Chip.tsx`:

```tsx
import type { ComponentPropsWithRef } from "react";
import { cx } from "./cx";

export interface ChipProps extends Omit<ComponentPropsWithRef<"button">, "type"> {
  selected?: boolean; // a toggle chip: aria-pressed
  size?: "sm" | "md";
}

// A small pill button: a quick pick, a filter, a time (redesign P1).
export function Chip({ selected, size = "md", className, ...rest }: ChipProps) {
  return <button {...rest} type="button" aria-pressed={selected} className={cx("chip", `chip--${size}`, className)} />;
}
```

Create `web/src/ui/Badge.tsx`:

```tsx
import type { ReactNode } from "react";
import { cx } from "./cx";

export type BadgeTone = "neutral" | "accent" | "ok" | "warn" | "danger" | "info";

export interface BadgeProps {
  tone?: BadgeTone;
  className?: string;
  children: ReactNode;
}

// A small label that never acts: a count, a state, a mark (redesign P1).
export function Badge({ tone = "neutral", className, children }: BadgeProps) {
  return <span className={cx("badge", `badge--${tone}`, className)}>{children}</span>;
}
```

Create `web/src/ui/Meter.tsx`:

```tsx
import { cx } from "./cx";

export type MeterTone = "accent" | "ok" | "warn" | "over";

export interface MeterProps {
  label: string; // the meter's accessible name
  value: number; // drawn and announced clamped to 0..max
  max?: number;
  tone?: MeterTone;
  valueText?: string; // what a screen reader says instead of the number
  className?: string;
}

const FULL = 100;

// A bar for an amount of something, a budget for one (redesign P1). The caller sends the tone.
export function Meter({ label, value, max = FULL, tone = "accent", valueText, className }: MeterProps) {
  const shown = Math.min(Math.max(value, 0), max);
  const percent = max > 0 ? (shown / max) * FULL : 0;
  return (
    <div className={cx("meter", className)} role="meter" aria-label={label} aria-valuemin={0} aria-valuemax={max}
      aria-valuenow={shown} aria-valuetext={valueText}>
      <div className={cx("meter__fill", `meter__fill--${tone}`)} style={{ width: `${percent}%` }} />
    </div>
  );
}
```

Create `web/src/ui/Skeleton.tsx`:

```tsx
import { cx } from "./cx";

export interface SkeletonProps {
  lines?: number; // how many grey bars
  label?: string; // what is loading, for screen readers
  className?: string;
}

// Grey bars where content will be (redesign P1). One status for the whole group; the bars are hidden.
export function Skeleton({ lines = 1, label = "Loading", className }: SkeletonProps) {
  return (
    <div className={cx("skeleton-group", className)} role="status" aria-label={label}>
      {Array.from({ length: Math.max(lines, 1) }, (_, index) => (
        <span key={index} className="skeleton" aria-hidden="true" />
      ))}
    </div>
  );
}
```

Create `web/src/ui/EmptyState.tsx`:

```tsx
import type { ReactNode } from "react";
import { cx } from "./cx";

export interface EmptyStateProps {
  title: string;
  hint?: ReactNode;
  art?: ReactNode; // a picture (a robot), decorative
  action?: ReactNode; // a button that starts the first thing
  className?: string;
}

// What a list shows when it has nothing yet (redesign P1; P5 gives each one its robot).
export function EmptyState({ title, hint, art, action, className }: EmptyStateProps) {
  return (
    <div className={cx("empty-state", className)}>
      {art ? <div className="empty-state__art" aria-hidden="true">{art}</div> : null}
      <p className="empty-state__title">{title}</p>
      {hint ? <p className="empty-state__hint">{hint}</p> : null}
      {action ? <div className="empty-state__action">{action}</div> : null}
    </div>
  );
}
```

`web/src/components/icons.tsx`. Find:

```tsx
export function PencilIcon() {
  return <Icon><path d="M13.5 3.5l3 3L7 16H4v-3z" /></Icon>;
}
```

Replace with:

```tsx
export function PencilIcon() {
  return <Icon><path d="M13.5 3.5l3 3L7 16H4v-3z" /></Icon>;
}

export function CloseIcon() {
  return <Icon><path d="M5 5l10 10M15 5L5 15" /></Icon>;
}
```

Create `web/src/ui/Toast.tsx`:

```tsx
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { CloseIcon } from "../components/icons";
import { cx } from "./cx";
import { IconButton } from "./IconButton";
import { TOAST_MS } from "./constants";

export type ToastTone = "info" | "ok" | "danger";

export interface ToastOptions {
  tone?: ToastTone;
  duration?: number; // ms; the default is TOAST_MS
}

interface ToastItem {
  id: number;
  message: string;
  tone: ToastTone;
}

export interface ToastApi {
  show: (message: string, options?: ToastOptions) => void;
}

const ToastContext = createContext<ToastApi | null>(null);

export function useToast(): ToastApi {
  const api = useContext(ToastContext);
  if (!api) throw new Error("useToast needs a ToastProvider above it (App.tsx has one).");
  return api;
}

function useToastQueue() {
  const [items, setItems] = useState<readonly ToastItem[]>([]);
  const timers = useRef(new Map<number, number>());
  const next = useRef(0);
  const dismiss = useCallback((id: number) => {
    window.clearTimeout(timers.current.get(id));
    timers.current.delete(id);
    setItems((current) => current.filter((item) => item.id !== id));
  }, []);
  const show = useCallback((message: string, options: ToastOptions = {}) => {
    const id = ++next.current;
    setItems((current) => [...current, { id, message, tone: options.tone ?? "info" }]);
    timers.current.set(id, window.setTimeout(() => dismiss(id), options.duration ?? TOAST_MS));
  }, [dismiss]);
  useEffect(() => {
    const pending = timers.current;
    return () => pending.forEach((timer) => window.clearTimeout(timer));
  }, []);
  return { items, show, dismiss };
}

// Short notes that come and go at the bottom of the screen (redesign P1). One polite live region
// reads each new note once; each note has Dismiss and leaves by itself after its duration.
export function ToastProvider({ children }: { children: ReactNode }) {
  const { items, show, dismiss } = useToastQueue();
  const api = useMemo(() => ({ show }), [show]);
  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="toast-region" role="status" aria-live="polite">
        {items.map((item) => (
          <div key={item.id} className={cx("toast", `toast--${item.tone}`)}>
            <p className="toast__message">{item.message}</p>
            <IconButton label="Dismiss" icon={<CloseIcon />} size="sm" onClick={() => dismiss(item.id)} />
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
```

`web/src/App.tsx`. Find:

```tsx
import { AuthProvider, useAuth } from "./hooks/useAuth";
```

Replace with:

```tsx
import { AuthProvider, useAuth } from "./hooks/useAuth";
import { ToastProvider } from "./ui/Toast";
```

`web/src/App.tsx`. Find:

```tsx
    <AuthProvider>
      <AppRoutes />
    </AuthProvider>
```

Replace with:

```tsx
    <AuthProvider>
      <ToastProvider>
        <AppRoutes />
      </ToastProvider>
    </AuthProvider>
```

- [ ] **Step 7: Their styles**

base.css gets the new sizes and variants; `ui.css` holds what base.css has no rule for.

ui/Button's sizes: md is the default height.

`web/src/styles/base.css`. Find:

```css
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  height: 40px;
  padding: 0 20px;
```

Replace with:

```css
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  height: var(--control-md);
  padding: 0 var(--space-4);
```

White on the light violet failed contrast on hover; the hover goes darker. Secondary is the old quiet look.

`web/src/styles/base.css`. Find:

```css
.btn--primary:hover:not(:disabled) {
  background: var(--color-accent-strong);
}

.btn--quiet {
  background: var(--color-raised);
  border-color: var(--color-border);
  color: var(--color-text);
}

.btn--quiet:hover:not(:disabled) {
  border-color: var(--color-border-strong);
}
```

Replace with:

```css
.btn--primary:hover:not(:disabled) {
  background: var(--color-accent-hover);
}

.btn--secondary,
.btn--quiet {
  background: var(--color-raised);
  border-color: var(--color-border);
  color: var(--color-text);
}

.btn--secondary:hover:not(:disabled),
.btn--quiet:hover:not(:disabled) {
  border-color: var(--color-border-strong);
}

.btn--ghost {
  background: transparent;
  color: var(--color-text-secondary);
}

.btn--ghost:hover:not(:disabled) {
  background: var(--color-raised);
  color: var(--color-text);
}
```

`web/src/styles/base.css`. Find:

```css
.btn--small {
  height: 32px;
  padding: 0 14px;
  font-size: var(--fs-label);
}
```

Replace with:

```css
.btn--sm,
.btn--small {
  height: var(--control-sm);
  padding: 0 var(--space-3);
  font-size: var(--fs-label);
}

.btn--lg {
  height: var(--control-lg);
  padding: 0 var(--space-5);
}
```

`web/src/styles/base.css`. Find:

```css
.icon-btn:hover {
  background: var(--color-raised);
}
```

Replace with:

```css
.icon-btn:hover {
  background: var(--color-raised);
}

.icon-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.icon-btn--sm {
  width: var(--control-sm);
  height: var(--control-sm);
}

.icon-btn--md {
  width: var(--control-md);
  height: var(--control-md);
}

.icon-btn--lg {
  width: var(--control-lg);
  height: var(--control-lg);
}

.icon-btn--secondary {
  border-color: var(--color-border);
  background: var(--color-raised);
}
```

`web/src/styles/base.css`. Find:

```css
.input {
  width: 100%;
  height: 44px;
```

Replace with:

```css
.input {
  width: 100%;
  height: var(--control-lg);
```

Create `web/src/styles/ui.css`:

```css
/* ---------------------------------------------------------------------
   The UI kit (web/src/ui, redesign P1): what base.css's shared controls
   (buttons, inputs, fields, chips) do not already cover. Tokens only.
   --------------------------------------------------------------------- */

/* ---- Field ----------------------------------------------------------- */

.field__head {
  display: flex;
  align-items: baseline;
  gap: var(--space-2);
}

.field__head .field__optional {
  margin-left: 0;
}

.field__hint,
.field__error {
  margin: 0;
  font-size: var(--fs-label);
}

.field__hint {
  color: var(--color-text-secondary);
}

.field__error {
  color: var(--color-danger);
}

.input[aria-invalid="true"] {
  border-color: var(--color-danger-edge);
}

/* ---- Input heights and the growing textarea --------------------------- */

.input--sm {
  height: var(--control-sm);
  padding: 0 var(--space-2);
  font-size: var(--fs-label);
}

.input--md {
  height: var(--control-md);
  padding: 0 var(--space-3);
}

.input--lg {
  height: var(--control-lg);
}

.input--grow {
  min-height: var(--control-lg);
  resize: none;
  overflow-y: hidden;
}

/* ---- Chip sizes ------------------------------------------------------- */

.chip--sm {
  height: var(--control-sm);
  padding: 0 var(--space-3);
  font-size: var(--fs-label);
}

.chip--md {
  height: var(--control-md);
}

/* ---- Badge ------------------------------------------------------------ */

.badge {
  display: inline-flex;
  align-items: center;
  height: 20px;
  padding: 0 var(--space-2);
  border-radius: var(--radius-pill);
  background: var(--color-raised);
  color: var(--color-text-secondary);
  font-size: var(--fs-caption);
  font-weight: 600;
  white-space: nowrap;
}

.badge--accent {
  background: var(--color-accent-tint);
  color: var(--color-accent-soft);
}

.badge--ok {
  color: var(--color-ok);
}

.badge--warn {
  color: var(--color-warn);
}

.badge--danger {
  background: var(--color-danger-tint);
  color: var(--color-danger);
}

.badge--info {
  color: var(--color-info);
}

/* ---- Meter ------------------------------------------------------------ */

.meter {
  height: 8px;
  overflow: hidden;
  border-radius: var(--radius-pill);
  background: var(--color-raised);
  box-shadow: inset 0 0 0 1px var(--color-border);
}

.meter__fill {
  height: 100%;
  border-radius: inherit;
  transition: width var(--duration-slow) var(--ease-standard);
}

.meter__fill--accent {
  background: var(--color-accent);
}

.meter__fill--ok {
  background: var(--color-ok);
}

.meter__fill--warn {
  background: var(--color-warn);
}

.meter__fill--over {
  background: var(--color-danger);
}

/* ---- Skeleton --------------------------------------------------------- */

.skeleton-group {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.skeleton {
  display: block;
  height: 12px;
  border-radius: var(--radius-xs);
  background: var(--color-raised);
  animation: skeleton-pulse 1.4s ease-in-out infinite;
}

.skeleton:last-child:not(:first-child) {
  width: 60%;
}

@keyframes skeleton-pulse {
  50% {
    opacity: 0.45;
  }
}

/* ---- Empty state ------------------------------------------------------ */

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-8) var(--space-4);
  text-align: center;
}

.empty-state__art {
  margin-bottom: var(--space-2);
}

.empty-state__title {
  margin: 0;
  font-size: var(--fs-lead);
  font-weight: 600;
}

.empty-state__hint {
  max-width: 42ch;
  margin: 0;
  color: var(--color-text-secondary);
  font-size: var(--fs-body);
}

.empty-state__action {
  margin-top: var(--space-3);
}

/* ---- Toast ------------------------------------------------------------ */

.toast-region {
  position: fixed;
  right: var(--space-4);
  bottom: var(--space-4);
  z-index: 60;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  max-width: min(380px, calc(100vw - 2 * var(--space-4)));
  pointer-events: none;
}

.toast {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-2) var(--space-2) var(--space-2) var(--space-4);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-overlay);
  box-shadow: var(--shadow-md);
  color: var(--color-text);
  font-size: var(--fs-body);
  pointer-events: auto;
}

.toast--ok {
  border-color: var(--color-ok);
}

.toast--danger {
  border-color: var(--color-danger-edge);
}

.toast__message {
  flex: 1;
  margin: 0;
}
```

`web/src/styles.css`. Find:

```css
@import "./styles/base.css";
```

Replace with:

```css
@import "./styles/base.css";
@import "./styles/ui.css";
```

- [ ] **Step 8: Run the tests to see them pass**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && cd web && npx vitest run tests/uiBasics.test.tsx tests/Toast.test.tsx tests/licenseGate.test.ts tests/tokens.test.ts`
Expected: PASS: `uiBasics` 11, `Toast` 3, `licenseGate` 4 and `tokens` 7 tests.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && cd web && npm test && npm run build && npm run size`
Expected: every test file passes, the build succeeds (it type-checks), and the entry chunk is within the budget (nothing imports Radix yet).

- [ ] **Step 9: Commit**

Run:

```bash
cd /Users/blckit/Desktop/Code_Projects/roost && \
git add web/package.json web/package-lock.json web/tests/licenseGate.ts web/tests/licenseGate.test.ts \
  web/tests/uiBasics.test.tsx web/tests/Toast.test.tsx web/src/ui/cx.ts web/src/ui/constants.ts \
  web/src/ui/Button.tsx web/src/ui/IconButton.tsx web/src/ui/Field.tsx web/src/ui/Input.tsx \
  web/src/ui/Textarea.tsx web/src/ui/Chip.tsx web/src/ui/Badge.tsx web/src/ui/Meter.tsx \
  web/src/ui/Skeleton.tsx web/src/ui/EmptyState.tsx web/src/ui/Toast.tsx web/src/components/icons.tsx \
  web/src/App.tsx web/src/styles/base.css web/src/styles/ui.css web/src/styles.css && \
git commit -m "feat: the base UI kit, Radix and react-day-picker, and a runtime licence check"
```

### Task 3: Radix Select, Menu, Tabs, Sheet, Popover and Tooltip, in place of every native select and both tab styles

Design P1 "Components" (the Radix half) and Review Focus 3. Today the app has three native `<select>`s (a task's priority, a project's lead bot, a room's coordinator), a home-made pop-up menu (`components/Menu.tsx`), and two tab styles (the Board's and the project page's pills, the profile's segmented bar).
- **Select, Menu, Tabs, Sheet, Popover and Tooltip** are thin wrappers over the Radix primitives, in Roost's tokens, with their keyboard and screen-reader behaviour.
- **Menu** keeps the old component's four exports (`Menu`, `MenuItem`, `MenuLink`, `MenuNote`), so `BotMenu`, Home and Chat only change their import. It gains `side` and `align` (the account menu opens rightwards, the chat's + menu upwards). It is not modal: Radix's modal menu traps focus while it closes, and New room's dialog lost its name field's focus. When an item's action has moved focus, the menu leaves it there.
- **Tabs**: one style everywhere (the profile's segmented bar, now `.tabs__*`), on the Board, the project page and the profile. The tab still lives in the URL; arrow keys move and select, Home and End jump.
- **Select** in the three forms. An option's value is never `""` (Radix keeps that for "nothing chosen"), so "No lead bot" is the word `none`. New room's dialog lets an Escape that an open list already used close only the list.
- **Sheet** (a right-side drawer) has no caller yet: P2 and P3 use it. It gives focus back to whatever opened it, even when that was not a Radix trigger.
- **IconButton** now shows its name as a tooltip.
- **The CSS** the old controls leave behind goes: the two tab styles, the home-made menu's positioning, the + menu's upward override, and the rule for a disabled native select.
- **Tests**: jsdom lacks pointer capture, `scrollIntoView` and `ResizeObserver`, which Radix calls; `web/tests/setup.ts` gives harmless stand-ins on `Element.prototype` (so a test that spies on `scrollIntoView` still can). A Radix menu item that is disabled is `aria-disabled`, not `disabled`. The token test learns that `--radix-*` variables are set by Radix at run time.

**Files:**
- Create: `web/src/ui/{Select,Menu,Tabs,Sheet,Popover,Tooltip}.tsx`, `web/src/styles/ui-overlays.css`, `web/tests/{Select,Menu,Tabs,overlays}.test.tsx`
- Delete: `web/src/components/Menu.tsx`
- Modify:
  - `web/src/ui/IconButton.tsx` (replaced), `web/src/ui/constants.ts`, `web/src/components/icons.tsx`
  - `web/src/pages/{Board,Project,Profile,Home,Chat}.tsx`, `web/src/components/{BotMenu,NewRoomDialog}.tsx`, `web/src/components/board/TaskEditForm.tsx`, `web/src/components/projects/ProjectEditForm.tsx`
  - `web/src/styles.css`, `web/src/styles/{board,profile,home,chat,rooms}.css`
  - `web/tests/setup.ts`, `web/tests/{BotMenu,TasksBoard,ProjectsBoard,NewRoomDialog}.test.tsx`, `web/tests/tokens.test.ts`, `web/e2e/team.spec.ts`
- Test: the four new files and the four changed ones

**Interfaces:**
- Consumes: Task 2's `Field`, `controlA11y`, `useFieldControl`, `IconButton`, `cx`, `ControlSize`, `CloseIcon` and `ui/constants.ts` (this task adds `TOOLTIP_DELAY_MS`).
- Produces (props in the Shared Contract): `Select`, `SelectOption`, `Menu`, `MenuItem`, `MenuLink`, `MenuNote`, `Tabs`, `TabItem`, `Sheet`, `Popover`, `Tooltip`, `TOOLTIP_DELAY_MS`, `ChevronDownIcon`, `CheckIcon`; `IconButton`'s `tooltip` prop. Accessible names other tasks rely on: a select is a `combobox` named by its Field; its options are `option`s; the Board's tab list is named "Board", the project page's "In this project", the profile's "{name}'s profile".

- [ ] **Step 1: Path guard**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && git -C /Users/blckit/Desktop/Code_Projects/roost rev-parse --show-toplevel && git -C /Users/blckit/Desktop/Code_Projects/roost branch --show-current`
Expected: `/Users/blckit/Desktop/Code_Projects/roost` then `night-1`. If either differs, stop.

Then confirm Task 2 has landed and this task has not:

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && test -f web/src/ui/Button.tsx && test ! -f web/src/ui/Select.tsx && test -f web/src/components/Menu.tsx && echo ready`
Expected: `ready`.

- [ ] **Step 2: Write the failing tests**

The four new test files, the Radix stand-ins, and the existing tests that must now find a combobox and options instead of a native select:

`web/tests/setup.ts`. Find:

```ts
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
}
```

Replace with:

```ts
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
}

// Radix primitives (Select, DropdownMenu, Popover, Tooltip) call these browser APIs, which jsdom
// does not have. Harmless stand-ins on Element, so a test may still replace one with its own spy.
if (typeof window !== "undefined") {
  const element = window.Element.prototype;
  element.hasPointerCapture ??= () => false;
  element.setPointerCapture ??= () => {};
  element.releasePointerCapture ??= () => {};
  element.scrollIntoView ??= () => {};
  globalThis.ResizeObserver ??= class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
}
```

Create `web/tests/Select.test.tsx`:

```tsx
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { Field } from "../src/ui/Field";
import { Select } from "../src/ui/Select";

afterEach(() => cleanup());

type Priority = "low" | "medium" | "high";
const OPTIONS = [
  { value: "low" as const, label: "Low" }, { value: "medium" as const, label: "Medium" }, { value: "high" as const, label: "High" },
];

function Picker({ onChange = vi.fn() }: { onChange?: (value: Priority) => void }) {
  const [value, setValue] = useState<Priority>("medium");
  return (
    <Field label="Priority" hint="How soon it matters">
      <Select value={value} options={OPTIONS} onChange={(next) => { setValue(next); onChange(next); }} />
    </Field>
  );
}

describe("Select", () => {
  it("is a combobox named by its Field, showing the chosen option", () => {
    render(<Picker />);
    const select = screen.getByRole("combobox", { name: "Priority" });
    expect(select).toHaveTextContent("Medium");
    expect(select).toHaveAccessibleDescription("How soon it matters");
  });

  it("opens on a click and picks an option", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<Picker onChange={onChange} />);
    await user.click(screen.getByRole("combobox", { name: "Priority" }));
    await user.click(screen.getByRole("option", { name: "High" }));
    expect(onChange).toHaveBeenCalledWith("high");
    expect(screen.getByRole("combobox", { name: "Priority" })).toHaveTextContent("High");
  });

  it("works from the keyboard alone: open, arrows, Enter, and focus back on the trigger", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<Picker onChange={onChange} />);
    const select = screen.getByRole("combobox", { name: "Priority" });
    select.focus();
    await user.keyboard("{Enter}");
    expect(await screen.findByRole("listbox")).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Medium" })).toHaveFocus();
    await user.keyboard("{ArrowDown}");
    expect(screen.getByRole("option", { name: "High" })).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(onChange).toHaveBeenCalledWith("high");
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    expect(select).toHaveFocus();
  });

  it("Escape closes the list without changing the choice", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<Picker onChange={onChange} />);
    await user.click(screen.getByRole("combobox", { name: "Priority" }));
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByRole("combobox", { name: "Priority" })).toHaveTextContent("Medium");
  });

  it("a select outside a Field takes its name from label", () => {
    render(<Select label="Lead bot" value="none" options={[{ value: "none", label: "No lead bot" }]} onChange={vi.fn()} />);
    expect(screen.getByRole("combobox", { name: "Lead bot" })).toHaveTextContent("No lead bot");
  });
});
```

Create `web/tests/Menu.test.tsx`:

```tsx
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useEffect, useRef, useState } from "react";
import { MemoryRouter } from "react-router-dom";
import { Menu, MenuItem, MenuLink, MenuNote } from "../src/ui/Menu";

afterEach(() => cleanup());

function renderMenu(onStop = vi.fn()) {
  render(
    <MemoryRouter>
      <Menu label="Scout menu" trigger="⋯">
        <MenuNote>Signed in as ana</MenuNote>
        <MenuItem onSelect={onStop}>Stop</MenuItem>
        <MenuItem onSelect={vi.fn()} disabled title="Make another bot the main bot first.">Retire this bot</MenuItem>
        <MenuLink to="/bots/new">New bot</MenuLink>
      </Menu>
    </MemoryRouter>,
  );
  return onStop;
}

describe("Menu", () => {
  it("opens from its button and lists its items, notes and links", async () => {
    renderMenu();
    const button = screen.getByRole("button", { name: "Scout menu" });
    expect(button).toHaveAttribute("aria-haspopup", "menu");
    await userEvent.click(button);
    expect(screen.getByRole("menu", { name: "Scout menu" })).toBeInTheDocument();
    expect(screen.getByText("Signed in as ana")).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "New bot" })).toHaveAttribute("href", "/bots/new");
    expect(screen.getByRole("menuitem", { name: "Retire this bot" })).toHaveAttribute("aria-disabled", "true");
  });

  it("picking an item runs it and closes the menu", async () => {
    const onStop = renderMenu();
    await userEvent.click(screen.getByRole("button", { name: "Scout menu" }));
    await userEvent.click(screen.getByRole("menuitem", { name: "Stop" }));
    expect(onStop).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });

  it("works from the keyboard: Enter opens, arrows skip the disabled item, Escape gives focus back", async () => {
    const onStop = renderMenu();
    const user = userEvent.setup();
    const button = screen.getByRole("button", { name: "Scout menu" });
    button.focus();
    await user.keyboard("{Enter}");
    await waitFor(() => expect(screen.getByRole("menuitem", { name: "Stop" })).toHaveFocus());
    await user.keyboard("{ArrowDown}");
    expect(screen.getByRole("menuitem", { name: "New bot" })).toHaveFocus();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    await waitFor(() => expect(button).toHaveFocus());
    expect(onStop).not.toHaveBeenCalled();
  });

  it("leaves focus where the chosen item's action put it", async () => {
    function RoomName() { // like NewRoomDialog: it focuses its field once it has mounted
      const field = useRef<HTMLInputElement>(null);
      useEffect(() => field.current?.focus(), []);
      return <input ref={field} aria-label="Room name" />;
    }
    function WithDialog() {
      const [open, setOpen] = useState(false);
      return (
        <MemoryRouter>
          <Menu label="New" trigger="+"><MenuItem onSelect={() => setOpen(true)}>New room</MenuItem></Menu>
          {open ? <RoomName /> : null}
        </MemoryRouter>
      );
    }
    render(<WithDialog />);
    await userEvent.click(screen.getByRole("button", { name: "New" }));
    await userEvent.click(screen.getByRole("menuitem", { name: "New room" }));
    const field = await screen.findByRole("textbox", { name: "Room name" });
    await waitFor(() => expect(field).toHaveFocus());
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(field).toHaveFocus();
  });
});
```

Create `web/tests/Tabs.test.tsx`:

```tsx
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { Tabs } from "../src/ui/Tabs";

afterEach(() => cleanup());

type Tab = "tasks" | "money" | "notes";
const TABS = [{ id: "tasks" as const, label: "Tasks" }, { id: "money" as const, label: "Money" }, { id: "notes" as const, label: "Notes" }];

function Board() {
  const [tab, setTab] = useState<Tab>("tasks");
  return <Tabs label="Board" tabs={TABS} value={tab} onChange={setTab} panelClassName="board-panel"><p>Panel {tab}</p></Tabs>;
}

describe("Tabs", () => {
  it("is a named tab list with the selected tab's panel, labelled by its tab", () => {
    render(<Board />);
    expect(screen.getByRole("tablist", { name: "Board" })).toBeInTheDocument();
    expect(screen.getAllByRole("tab").map((tab) => tab.textContent)).toEqual(["Tasks", "Money", "Notes"]);
    expect(screen.getByRole("tab", { name: "Tasks" })).toHaveAttribute("aria-selected", "true");
    const panel = screen.getByRole("tabpanel", { name: "Tasks" });
    expect(panel).toHaveTextContent("Panel tasks");
    expect(panel).toHaveClass("tabs__panel", "board-panel");
  });

  it("a click selects a tab", async () => {
    render(<Board />);
    await userEvent.click(screen.getByRole("tab", { name: "Notes" }));
    expect(screen.getByRole("tab", { name: "Notes" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tabpanel", { name: "Notes" })).toHaveTextContent("Panel notes");
  });

  it("arrow keys move between tabs and select them; Home and End jump to the ends", async () => {
    const user = userEvent.setup();
    render(<Board />);
    screen.getByRole("tab", { name: "Tasks" }).focus();
    await user.keyboard("{ArrowRight}");
    expect(screen.getByRole("tab", { name: "Money" })).toHaveFocus();
    expect(screen.getByRole("tab", { name: "Money" })).toHaveAttribute("aria-selected", "true");
    await user.keyboard("{End}");
    expect(screen.getByRole("tab", { name: "Notes" })).toHaveAttribute("aria-selected", "true");
    await user.keyboard("{Home}");
    expect(screen.getByRole("tab", { name: "Tasks" })).toHaveAttribute("aria-selected", "true");
  });
});
```

Create `web/tests/overlays.test.tsx`:

```tsx
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { IconButton } from "../src/ui/IconButton";
import { Popover } from "../src/ui/Popover";
import { Sheet } from "../src/ui/Sheet";
import { Tooltip } from "../src/ui/Tooltip";
import { CalendarIcon, PlusIcon } from "../src/components/icons";

afterEach(() => cleanup());

function TaskSheet() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>Open task</button>
      <Sheet open={open} onOpenChange={setOpen} title="Call the dentist" description="Due tomorrow">
        <input aria-label="Title" />
      </Sheet>
    </>
  );
}

describe("Sheet", () => {
  it("opens as a named modal dialog with Close, and Escape gives focus back to its opener", async () => {
    const user = userEvent.setup();
    render(<TaskSheet />);
    const opener = screen.getByRole("button", { name: "Open task" });
    await user.click(opener);
    const sheet = screen.getByRole("dialog", { name: "Call the dentist" });
    expect(sheet).toHaveClass("ui-sheet");
    expect(sheet).toHaveAccessibleDescription("Due tomorrow");
    expect(screen.getByRole("button", { name: "Close" })).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(opener).toHaveFocus();
  });

  it("Close closes it", async () => {
    render(<TaskSheet />);
    await userEvent.click(screen.getByRole("button", { name: "Open task" }));
    await userEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});

describe("Popover", () => {
  it("opens a named panel from an icon button and closes on Escape, focus back on the button", async () => {
    const user = userEvent.setup();
    render(
      <Popover label="Pick a day" trigger={<IconButton label="Open calendar" icon={<CalendarIcon />} />}>
        <button type="button">Tomorrow</button>
      </Popover>,
    );
    const button = screen.getByRole("button", { name: "Open calendar" });
    await user.click(button);
    expect(screen.getByRole("dialog", { name: "Pick a day" })).toBeInTheDocument();
    expect(button).toHaveAttribute("aria-expanded", "true");
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog", { name: "Pick a day" })).not.toBeInTheDocument();
    expect(button).toHaveFocus();
  });
});

describe("Tooltip and IconButton", () => {
  it("an icon button's tooltip says its name on keyboard focus", async () => {
    const user = userEvent.setup();
    render(<IconButton label="New chat" icon={<PlusIcon />} />);
    await user.tab();
    expect(screen.getByRole("button", { name: "New chat" })).toHaveFocus();
    expect(await screen.findByRole("tooltip")).toHaveTextContent("New chat");
  });

  it("a tooltip leaves its element's own name alone", async () => {
    const user = userEvent.setup();
    render(<Tooltip content="Saves at once"><button type="button">Save</button></Tooltip>);
    await user.hover(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("tooltip")).toHaveTextContent("Saves at once");
    expect(screen.getByRole("button", { name: "Save" })).toBeInTheDocument();
  });
});
```

`web/tests/BotMenu.test.tsx`. Find:

```tsx
    expect(screen.getByRole("menuitem", { name: "Stop" })).toBeDisabled();
```

Replace with:

```tsx
    expect(screen.getByRole("menuitem", { name: "Stop" })).toHaveAttribute("aria-disabled", "true");
```

`web/tests/BotMenu.test.tsx`. Find:

```tsx
    expect(screen.getByRole("menuitem", { name: "Retire this bot" })).toBeDisabled();
```

Replace with:

```tsx
    expect(screen.getByRole("menuitem", { name: "Retire this bot" })).toHaveAttribute("aria-disabled", "true");
```

`web/tests/TasksBoard.test.tsx`. Find:

```tsx
    await user.selectOptions(screen.getByLabelText("Priority"), "high");
```

Replace with:

```tsx
    await user.click(screen.getByRole("combobox", { name: "Priority" }));
    await user.click(screen.getByRole("option", { name: "High" }));
```

`web/tests/ProjectsBoard.test.tsx`. Find:

```tsx
    await user.selectOptions(within(form).getByLabelText("Lead bot"), "Helper");
```

Replace with:

```tsx
    await user.click(within(form).getByRole("combobox", { name: "Lead bot" }));
    await user.click(screen.getByRole("option", { name: "Helper" }));
```

`web/tests/NewRoomDialog.test.tsx`. Find:

```tsx
    expect(screen.getByLabelText("Coordinator")).toHaveValue("c");
```

Replace with:

```tsx
    expect(screen.getByRole("combobox", { name: "Coordinator" })).toHaveTextContent("Chief");
```

`web/tests/NewRoomDialog.test.tsx`. Find:

```tsx
  it("closes with Escape and moves focus into the name field", async () => {
```

Replace with:

```tsx
  it("Escape closes the open Coordinator list, not the dialog", async () => {
    const { onClose } = setup();
    for (const name of ["Chief", "Scout"]) await userEvent.click(screen.getByRole("checkbox", { name }));
    await userEvent.click(screen.getByRole("combobox", { name: "Coordinator" }));
    expect(screen.getByRole("listbox")).toBeInTheDocument();
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog", { name: "New room" })).toBeInTheDocument();
  });

  it("picks another coordinator from the list", async () => {
    createRoomMock.mockResolvedValue({ id: "r1", name: "Saturday" });
    setup();
    await userEvent.type(screen.getByLabelText("Room name"), "Saturday");
    for (const name of ["Chief", "Scout"]) await userEvent.click(screen.getByRole("checkbox", { name }));
    await userEvent.click(screen.getByRole("combobox", { name: "Coordinator" }));
    await userEvent.click(screen.getByRole("option", { name: "Scout" }));
    await userEvent.click(screen.getByRole("button", { name: "Create room" }));
    expect(createRoomMock).toHaveBeenCalledWith({ name: "Saturday", member_ids: ["c", "s"], coordinator_id: "s" });
  });

  it("closes with Escape and moves focus into the name field", async () => {
```

`web/e2e/team.spec.ts`. Find:

```ts
  await expect(dialog.getByLabel("Coordinator")).toHaveValue(/.+/);
```

Replace with:

```ts
  await expect(dialog.getByRole("combobox", { name: "Coordinator" })).toHaveText(/.+/);
```

`web/tests/tokens.test.ts`. Find:

```ts
const READABLE = 4.5;
```

Replace with:

```ts
const READABLE = 4.5;
// Set by Radix on its own popper elements at run time (the select's width and room to grow).
const RUNTIME_VARIABLE = /^--radix-/;
```

`web/tests/tokens.test.ts`. Find:

```ts
    expect(used.filter((entry) => !defined.has(entry.split(" ")[1]))).toEqual([]);
```

Replace with:

```ts
    const unknown = used.filter((entry) => {
      const variable = entry.split(" ")[1];
      return !defined.has(variable) && !RUNTIME_VARIABLE.test(variable);
    });
    expect(unknown).toEqual([]);
```

- [ ] **Step 3: Run them to see them fail**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && cd web && npx vitest run tests/Select.test.tsx tests/Menu.test.tsx tests/Tabs.test.tsx tests/overlays.test.tsx tests/BotMenu.test.tsx tests/TasksBoard.test.tsx tests/ProjectsBoard.test.tsx tests/NewRoomDialog.test.tsx tests/tokens.test.ts`
Expected: FAIL, 8 files failed and 1 passed (`tokens`):
- `Select`, `Menu`, `Tabs` and `overlays`: `Failed to resolve import "../src/ui/…"`.
- `BotMenu`: 2 failed (`toHaveAttribute("aria-disabled", "true")`: the old menu sets `disabled`).
- `NewRoomDialog`: 2 failed (`Unable to find an accessible element with the role "listbox"`, and the pick that cannot happen).
- `TasksBoard`: `edits a task's title and priority` (`Unable to find … role "option" and name "High"`).
- `ProjectsBoard`: `makes a project from the form and reloads the list`.

- [ ] **Step 4: The Radix components**

`web/src/ui/constants.ts`. Find:

```ts
export const TEXTAREA_MAX_ROWS = 12; // an auto-growing textarea scrolls past this
```

Replace with:

```ts
export const TEXTAREA_MAX_ROWS = 12; // an auto-growing textarea scrolls past this
export const TOOLTIP_DELAY_MS = 400; // hover this long before a tooltip shows
```

`web/src/components/icons.tsx`. Find:

```tsx
export function CloseIcon() {
  return <Icon><path d="M5 5l10 10M15 5L5 15" /></Icon>;
}
```

Replace with:

```tsx
export function CloseIcon() {
  return <Icon><path d="M5 5l10 10M15 5L5 15" /></Icon>;
}

export function ChevronDownIcon() {
  return <Icon><path d="M5 8l5 5 5-5" /></Icon>;
}

export function CheckIcon() {
  return <Icon><path d="M4 10.5l4 4 8-9" /></Icon>;
}
```

Create `web/src/ui/Tooltip.tsx`:

```tsx
import * as RadixTooltip from "@radix-ui/react-tooltip";
import type { ReactElement, ReactNode } from "react";
import { TOOLTIP_DELAY_MS } from "./constants";

export interface TooltipProps {
  content: ReactNode;
  children: ReactElement; // the element it explains; it keeps its own accessible name
  side?: "top" | "bottom" | "left" | "right";
}

// A short hint on hover or keyboard focus (redesign P1, Radix Tooltip). Each tooltip brings its own
// provider, so nothing has to wrap the app.
export function Tooltip({ content, children, side = "top" }: TooltipProps) {
  return (
    <RadixTooltip.Provider delayDuration={TOOLTIP_DELAY_MS}>
      <RadixTooltip.Root>
        <RadixTooltip.Trigger asChild>{children}</RadixTooltip.Trigger>
        <RadixTooltip.Portal>
          <RadixTooltip.Content className="tooltip" side={side} sideOffset={6}>{content}</RadixTooltip.Content>
        </RadixTooltip.Portal>
      </RadixTooltip.Root>
    </RadixTooltip.Provider>
  );
}
```

Replace the whole of `web/src/ui/IconButton.tsx` with: (the tooltip says the name)

```tsx
import type { ComponentPropsWithRef, ReactNode } from "react";
import { cx } from "./cx";
import { Tooltip } from "./Tooltip";
import type { ControlSize } from "./Button";

export interface IconButtonProps extends Omit<ComponentPropsWithRef<"button">, "aria-label" | "children" | "type"> {
  label: string; // the accessible name: an icon alone says nothing
  icon: ReactNode;
  size?: ControlSize;
  variant?: "ghost" | "secondary";
  pressed?: boolean; // a toggle: sets aria-pressed
  tooltip?: boolean; // shows the label on hover and focus (default)
}

// A square button with an icon and a name (redesign P1); its tooltip says the name.
export function IconButton({
  label, icon, size = "md", variant = "ghost", pressed, tooltip = true, className, ...rest
}: IconButtonProps) {
  const button = (
    <button {...rest} type="button" aria-label={label} aria-pressed={pressed}
      className={cx("icon-btn", `icon-btn--${size}`, `icon-btn--${variant}`, className)}>
      {icon}
    </button>
  );
  return tooltip ? <Tooltip content={label}>{button}</Tooltip> : button;
}
```

Create `web/src/ui/Select.tsx`:

```tsx
import * as RadixSelect from "@radix-ui/react-select";
import { CheckIcon, ChevronDownIcon } from "../components/icons";
import { cx } from "./cx";
import { controlA11y, useFieldControl } from "./Field";
import type { ControlSize } from "./Button";

// An option's value is never "" (Radix keeps "" for "nothing chosen"): use a word such as "none".
export interface SelectOption<T extends string = string> {
  value: T;
  label: string;
  disabled?: boolean;
}

export interface SelectProps<T extends string = string> {
  value: T;
  onChange: (value: T) => void;
  options: ReadonlyArray<SelectOption<T>>;
  label?: string; // the accessible name when the select is not inside a Field
  id?: string;
  disabled?: boolean;
  placeholder?: string;
  size?: ControlSize;
}

// A styled list to pick one from (redesign P1, Radix Select): the keyboard, typeahead and screen
// reader behaviour of a native select, in Roost's look. It opens below its button.
export function Select<T extends string = string>({
  value, onChange, options, label, id, disabled = false, placeholder, size = "lg",
}: SelectProps<T>) {
  const a11y = controlA11y(useFieldControl(), { id });
  return (
    <RadixSelect.Root value={value} onValueChange={(next) => onChange(next as T)} disabled={disabled}>
      <RadixSelect.Trigger {...a11y} aria-label={label} className={cx("select", `select--${size}`)}>
        <RadixSelect.Value placeholder={placeholder} />
        <RadixSelect.Icon className="select__icon"><ChevronDownIcon /></RadixSelect.Icon>
      </RadixSelect.Trigger>
      <RadixSelect.Portal>
        <RadixSelect.Content className="select__content" position="popper" sideOffset={4}>
          <RadixSelect.Viewport className="select__viewport">
            {options.map((option) => (
              <RadixSelect.Item key={option.value} value={option.value} disabled={option.disabled} className="select__item">
                <RadixSelect.ItemText>{option.label}</RadixSelect.ItemText>
                <RadixSelect.ItemIndicator className="select__check"><CheckIcon /></RadixSelect.ItemIndicator>
              </RadixSelect.Item>
            ))}
          </RadixSelect.Viewport>
        </RadixSelect.Content>
      </RadixSelect.Portal>
    </RadixSelect.Root>
  );
}
```

Create `web/src/ui/Menu.tsx`:

```tsx
import * as RadixMenu from "@radix-ui/react-dropdown-menu";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";

export interface MenuProps {
  label: string; // names the button and the menu
  trigger: ReactNode; // what the button shows (an icon, initials)
  children: ReactNode; // MenuItem, MenuLink and MenuNote
  side?: "top" | "bottom";
  align?: "start" | "end";
}

// Radix gives focus back to the button when the menu closes. When the chosen item has already put
// focus somewhere (New room focuses the dialog's name field), leave it there.
function keepFocusAnItemMoved(event: Event) {
  const active = document.activeElement;
  const moved = active instanceof HTMLElement && active !== document.body && active.isConnected
    && !active.closest("[role='menu']");
  if (moved) event.preventDefault();
}

// A pop-up menu (redesign P1, Radix DropdownMenu): arrow keys, typeahead, Escape, and focus back to
// its button. Picking an item closes it. Not modal: an item may open a dialog that takes the focus.
export function Menu({ label, trigger, children, side = "bottom", align = "end" }: MenuProps) {
  return (
    <div className="menu">
      <RadixMenu.Root modal={false}>
        <RadixMenu.Trigger className="icon-btn" aria-label={label}>{trigger}</RadixMenu.Trigger>
        <RadixMenu.Portal>
          <RadixMenu.Content className="menu__list" side={side} align={align} sideOffset={6}
            onCloseAutoFocus={keepFocusAnItemMoved}>
            {children}
          </RadixMenu.Content>
        </RadixMenu.Portal>
      </RadixMenu.Root>
    </div>
  );
}

export function MenuItem({ onSelect, disabled = false, title, children }: {
  onSelect: () => void; disabled?: boolean; title?: string; children: ReactNode;
}) {
  return (
    <RadixMenu.Item className="menu__item" disabled={disabled} title={title} onSelect={onSelect}>
      {children}
    </RadixMenu.Item>
  );
}

export function MenuLink({ to, children }: { to: string; children: ReactNode }) {
  return (
    <RadixMenu.Item asChild className="menu__item">
      <Link to={to}>{children}</Link>
    </RadixMenu.Item>
  );
}

export function MenuNote({ children }: { children: ReactNode }) {
  return <RadixMenu.Label className="menu__note">{children}</RadixMenu.Label>;
}
```

Create `web/src/ui/Tabs.tsx`:

```tsx
import * as RadixTabs from "@radix-ui/react-tabs";
import type { ReactNode } from "react";
import { cx } from "./cx";

export interface TabItem<T extends string> {
  id: T;
  label: string;
}

export interface TabsProps<T extends string> {
  label: string; // the tab list's accessible name
  tabs: ReadonlyArray<TabItem<T>>;
  value: T;
  onChange: (value: T) => void;
  children: ReactNode; // the selected tab's panel
  panelClassName?: string;
}

// One tab style everywhere (redesign P1, Radix Tabs): arrow keys move and select, Home and End jump.
// The caller keeps the selected tab (in the URL) and renders only its panel.
export function Tabs<T extends string>({ label, tabs, value, onChange, children, panelClassName }: TabsProps<T>) {
  return (
    <RadixTabs.Root className="tabs" value={value} onValueChange={(next) => onChange(next as T)}>
      <RadixTabs.List className="tabs__list" aria-label={label}>
        {tabs.map((tab) => (
          <RadixTabs.Trigger key={tab.id} value={tab.id} className="tabs__tab">{tab.label}</RadixTabs.Trigger>
        ))}
      </RadixTabs.List>
      <RadixTabs.Content value={value} className={cx("tabs__panel", panelClassName)}>{children}</RadixTabs.Content>
    </RadixTabs.Root>
  );
}
```

Create `web/src/ui/Sheet.tsx`:

```tsx
import * as RadixDialog from "@radix-ui/react-dialog";
import { useRef, type ReactNode } from "react";
import { CloseIcon } from "../components/icons";
import { IconButton } from "./IconButton";

export interface SheetProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string; // a line under the title
  children: ReactNode;
  footer?: ReactNode; // actions, pinned to the bottom
}

// A drawer from the right edge (redesign P1, Radix Dialog): modal, focus kept inside, Escape and
// the scrim close it, and focus goes back to what opened it.
export function Sheet({ open, onOpenChange, title, description, children, footer }: SheetProps) {
  const opener = useRef<HTMLElement | null>(null);
  // Remembered as it opens, before focus moves in: a sheet opened from code has no Radix trigger.
  const remember = () => {
    opener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  };
  const giveBack = (event: Event) => {
    event.preventDefault();
    if (opener.current?.isConnected) opener.current.focus();
  };
  return (
    <RadixDialog.Root open={open} onOpenChange={onOpenChange}>
      <RadixDialog.Portal>
        <RadixDialog.Overlay className="ui-sheet__scrim" />
        <RadixDialog.Content className="ui-sheet" onOpenAutoFocus={remember} onCloseAutoFocus={giveBack}
          {...(description ? {} : { "aria-describedby": undefined })}>
          <header className="ui-sheet__head">
            <RadixDialog.Title className="ui-sheet__title">{title}</RadixDialog.Title>
            <RadixDialog.Close asChild>
              <IconButton label="Close" icon={<CloseIcon />} tooltip={false} />
            </RadixDialog.Close>
          </header>
          {description ? <RadixDialog.Description className="ui-sheet__description">{description}</RadixDialog.Description> : null}
          <div className="ui-sheet__body">{children}</div>
          {footer ? <footer className="ui-sheet__foot">{footer}</footer> : null}
        </RadixDialog.Content>
      </RadixDialog.Portal>
    </RadixDialog.Root>
  );
}
```

Create `web/src/ui/Popover.tsx`:

```tsx
import * as RadixPopover from "@radix-ui/react-popover";
import type { ReactElement, ReactNode } from "react";

export interface PopoverProps {
  trigger: ReactElement; // one element that opens it, such as an IconButton
  label: string; // the panel's accessible name
  children: ReactNode;
  open?: boolean; // controlled when given, with onOpenChange
  onOpenChange?: (open: boolean) => void;
  side?: "top" | "bottom";
  align?: "start" | "center" | "end";
}

// A small panel beside its button (redesign P1, Radix Popover): Escape and a click outside close it,
// and focus goes back to the button.
export function Popover({ trigger, label, children, open, onOpenChange, side = "bottom", align = "end" }: PopoverProps) {
  return (
    <RadixPopover.Root open={open} onOpenChange={onOpenChange}>
      <RadixPopover.Trigger asChild>{trigger}</RadixPopover.Trigger>
      <RadixPopover.Portal>
        <RadixPopover.Content className="popover" aria-label={label} side={side} align={align} sideOffset={6}>
          {children}
        </RadixPopover.Content>
      </RadixPopover.Portal>
    </RadixPopover.Root>
  );
}
```

- [ ] **Step 5: Menus: the new component, the old one gone**

ui/Menu.tsx replaces it, with the same four exports.

Delete `web/src/components/Menu.tsx`:

```bash
cd /Users/blckit/Desktop/Code_Projects/roost && git rm web/src/components/Menu.tsx
```

`web/src/components/BotMenu.tsx`. Find:

```tsx
import { Menu, MenuItem } from "./Menu";
```

Replace with:

```tsx
import { Menu, MenuItem } from "../ui/Menu";
```

`web/src/pages/Home.tsx`. Find:

```tsx
import { Menu, MenuItem, MenuLink, MenuNote } from "../components/Menu";
```

Replace with:

```tsx
import { Menu, MenuItem, MenuLink, MenuNote } from "../ui/Menu";
```

The account menu sits at the left edge, so it opens rightwards.

`web/src/pages/Home.tsx`. Find:

```tsx
      <Menu label="Account" trigger={<span className="home-header__initials">{initials(user?.username ?? "")}</span>}>
```

Replace with:

```tsx
      <Menu label="Account" align="start" trigger={<span className="home-header__initials">{initials(user?.username ?? "")}</span>}>
```

`web/src/pages/Chat.tsx`. Find:

```tsx
import { Menu, MenuItem, MenuNote } from "../components/Menu";
```

Replace with:

```tsx
import { Menu, MenuItem, MenuNote } from "../ui/Menu";
```

The + sits at the bottom of the screen, so its menu opens upwards.

`web/src/pages/Chat.tsx`. Find:

```tsx
        <Menu label="More for this chat" trigger={<PlusIcon />}>
```

Replace with:

```tsx
        <Menu label="More for this chat" side="top" align="start" trigger={<PlusIcon />}>
```

- [ ] **Step 6: One tab style**

`web/src/pages/Board.tsx`. Find:

```tsx
import { ProjectsBoard } from "../components/projects/ProjectsBoard";
```

Replace with:

```tsx
import { ProjectsBoard } from "../components/projects/ProjectsBoard";
import { Tabs } from "../ui/Tabs";
```

`web/src/pages/Board.tsx`. Find:

```tsx
        <div className="board-tabs" role="tablist" aria-label="Board">
          {TABS.map((tab) => (
            <button key={tab.id} id={`board-tab-${tab.id}`} type="button" role="tab" aria-selected={tab.id === current.id}
              aria-controls="board-panel" className={`board-tab${tab.id === current.id ? " board-tab--active" : ""}`}
              onClick={() => setParams({ tab: tab.id }, { replace: true })}>
              {tab.label}
            </button>
          ))}
        </div>
        <div id="board-panel" className="board-panel" role="tabpanel" aria-labelledby={`board-tab-${current.id}`}>
          {PANELS[current.id]()}
        </div>
```

Replace with:

```tsx
        <Tabs label="Board" tabs={TABS} value={current.id} panelClassName="board-panel"
          onChange={(tab) => setParams({ tab }, { replace: true })}>
          {PANELS[current.id]()}
        </Tabs>
```

`web/src/pages/Project.tsx`. Find:

```tsx
import { useLiveState } from "../hooks/useLiveStore";
```

Replace with:

```tsx
import { useLiveState } from "../hooks/useLiveStore";
import { Tabs } from "../ui/Tabs";
```

`web/src/pages/Project.tsx`. Find:

```tsx
function ProjectTabs({ current, onPick }: { current: ProjectTab; onPick: (tab: ProjectTab) => void }) {
  return (
    <div className="board-tabs" role="tablist" aria-label="In this project">
      {TABS.map((tab) => (
        <button key={tab.id} id={`project-tab-${tab.id}`} type="button" role="tab" aria-selected={tab.id === current}
          aria-controls="project-panel" className={`board-tab${tab.id === current ? " board-tab--active" : ""}`}
          onClick={() => onPick(tab.id)}>
          {tab.label}
        </button>
      ))}
    </div>
  );
}

```

Delete it.

`web/src/pages/Project.tsx`. Find:

```tsx
      <ProjectTabs current={current} onPick={(tab) => setParams({ tab }, { replace: true })} />
      <div id="project-panel" role="tabpanel" aria-labelledby={`project-tab-${current}`} className="board-panel">
        {PANELS[current]({ project, reload })}
      </div>
```

Replace with:

```tsx
      <Tabs label="In this project" tabs={TABS} value={current} panelClassName="board-panel"
        onChange={(tab) => setParams({ tab }, { replace: true })}>
        {PANELS[current]({ project, reload })}
      </Tabs>
```

`web/src/pages/Profile.tsx`. Find:

```tsx
import { useLiveState } from "../hooks/useLiveStore";
```

Replace with:

```tsx
import { useLiveState } from "../hooks/useLiveStore";
import { Tabs } from "../ui/Tabs";
```

`web/src/pages/Profile.tsx`. Find:

```tsx
function ProfileTabs({ name, current, onPick }: { name: string; current: ProfileTab; onPick: (tab: ProfileTab) => void }) {
  return (
    <div className="profile-tabs" role="tablist" aria-label={`${name}'s profile`}>
      {TABS.map((tab) => (
        <button key={tab.id} type="button" role="tab" id={`profile-tab-${tab.id}`} aria-selected={tab.id === current}
          aria-controls="profile-panel" className={`profile-tab${tab.id === current ? " profile-tab--active" : ""}`}
          onClick={() => onPick(tab.id)}>
          {tab.label}
        </button>
      ))}
    </div>
  );
}

```

Delete it.

`web/src/pages/Profile.tsx`. Find:

```tsx
        <ProfileTabs name={shown.name} current={current} onPick={(tab) => setParams({ tab }, { replace: true })} />
        <div id="profile-panel" role="tabpanel" aria-labelledby={`profile-tab-${current}`} className="profile-panel">
          {PANELS[current]({ bot: shown, onChange: setBot, onShare: () => setSharing(true) })}
        </div>
```

Replace with:

```tsx
        <Tabs label={`${shown.name}'s profile`} tabs={TABS} value={current} panelClassName="profile-panel"
          onChange={(tab) => setParams({ tab }, { replace: true })}>
          {PANELS[current]({ bot: shown, onChange: setBot, onShare: () => setSharing(true) })}
        </Tabs>
```

- [ ] **Step 7: No native select**

`web/src/components/board/TaskEditForm.tsx`. Find:

```tsx
import { MAX_DUE_TEXT, MAX_TITLE } from "./taskLimits";

const PRIORITIES: readonly TaskOut["priority"][] = ["low", "medium", "high", "urgent"];
```

Replace with:

```tsx
import { MAX_DUE_TEXT, MAX_TITLE } from "./taskLimits";
import { Field } from "../../ui/Field";
import { Select, type SelectOption } from "../../ui/Select";

const PRIORITIES: ReadonlyArray<SelectOption<TaskOut["priority"]>> = [
  { value: "low", label: "Low" }, { value: "medium", label: "Medium" }, { value: "high", label: "High" },
  { value: "urgent", label: "Urgent" },
];
```

`web/src/components/board/TaskEditForm.tsx`. Find:

```tsx
      <label className="field"><span className="field__label">Priority</span>
        <select className="input" value={fields.priority}
          onChange={(e) => set("priority", e.target.value as TaskOut["priority"])}>
          {PRIORITIES.map((p) => <option key={p} value={p}>{p}</option>)}
        </select>
      </label>
```

Replace with:

```tsx
      <Field label="Priority">
        <Select value={fields.priority} options={PRIORITIES} onChange={(priority) => set("priority", priority)} />
      </Field>
```

`web/src/components/projects/ProjectEditForm.tsx`. Find:

```tsx
import { useLiveState } from "../../hooks/useLiveStore";
```

Replace with:

```tsx
import { useLiveState } from "../../hooks/useLiveStore";
import { Field } from "../../ui/Field";
import { Select, type SelectOption } from "../../ui/Select";
```

`web/src/components/projects/ProjectEditForm.tsx`. Find:

```tsx
type Setter = (key: keyof Fields, value: string) => void;
```

Replace with:

```tsx
type Setter = (key: keyof Fields, value: string) => void;

// The Select's word for "no lead bot" (Radix keeps "" for "nothing chosen"); a bot id is a UUID.
const NO_LEAD = "none";
```

`web/src/components/projects/ProjectEditForm.tsx`. Find:

```tsx
  const bots = [...Object.values(live.bots)].sort((a, b) => a.name.localeCompare(b.name));
```

Replace with:

```tsx
  const bots = [...Object.values(live.bots)].sort((a, b) => a.name.localeCompare(b.name));
  const leads: SelectOption[] = [{ value: NO_LEAD, label: "No lead bot" }, ...bots.map((bot) => ({ value: bot.id, label: bot.name }))];
```

`web/src/components/projects/ProjectEditForm.tsx`. Find:

```tsx
      <label className="field project-edit__lead"><span className="field__label">Lead bot</span>
        <select className="input" value={fields.lead} onChange={(e) => set("lead", e.target.value)}>
          <option value="">No lead bot</option>
          {bots.map((bot) => <option key={bot.id} value={bot.id}>{bot.name}</option>)}
        </select>
      </label>
```

Replace with:

```tsx
      <Field label="Lead bot" className="project-edit__lead">
        <Select value={fields.lead || NO_LEAD} options={leads}
          onChange={(lead) => set("lead", lead === NO_LEAD ? "" : lead)} />
      </Field>
```

`web/src/components/NewRoomDialog.tsx`. Find:

```tsx
import { useEffect, useId, useRef, useState, type FormEvent, type RefObject } from "react";
import { ErrorNotice } from "./ErrorNotice";
```

Replace with:

```tsx
import { useEffect, useRef, useState, type FormEvent, type RefObject } from "react";
import { ErrorNotice } from "./ErrorNotice";
import { Field } from "../ui/Field";
import { Select } from "../ui/Select";
```

No native select is left; Radix's hidden one must not join the Tab loop.

`web/src/components/NewRoomDialog.tsx`. Find:

```tsx
const FOCUSABLE = "button:not(:disabled), input:not(:disabled), select:not(:disabled), [href], [tabindex]:not([tabindex='-1'])";
```

Replace with:

```tsx
const FOCUSABLE = "button:not(:disabled), input:not(:disabled), [href], [tabindex]:not([tabindex='-1'])";
```

`web/src/components/NewRoomDialog.tsx`. Find:

```tsx
// Focus the name field on open, Escape closes, Tab stays inside, and
// focus goes back to whatever opened the dialog when it closes.
```

Replace with:

```tsx
// Focus the name field on open, Escape closes, Tab stays inside, and
// focus goes back to whatever opened the dialog when it closes. An Escape
// that an open list inside already used (the Coordinator select) is its own.
```

`web/src/components/NewRoomDialog.tsx`. Find:

```tsx
      if (event.key === "Escape") onClose();
```

Replace with:

```tsx
      if (event.key === "Escape" && !event.defaultPrevented) onClose();
```

`web/src/components/NewRoomDialog.tsx`. Find:

```tsx
function CoordinatorField({ members, value, onChange }: { members: BotOut[]; value: string | null; onChange: (id: string) => void }) {
  const id = useId();
  return (
    <div className="field">
      <label className="field__label" htmlFor={id}>
        Coordinator
      </label>
      <select
        id={id} className="input" value={value ?? ""} disabled={members.length === 0}
        aria-describedby={`${id}-hint`} onChange={(event) => onChange(event.target.value)}
      >
        {members.map((bot) => (
          <option key={bot.id} value={bot.id}>
            {bot.name}
          </option>
        ))}
      </select>
      <span id={`${id}-hint`} className="room-pick__hint">
        Answers any post that mentions nobody.
      </span>
    </div>
  );
}
```

Replace with:

```tsx
function CoordinatorField({ members, value, onChange }: { members: BotOut[]; value: string | null; onChange: (id: string) => void }) {
  return (
    <Field label="Coordinator" hint="Answers any post that mentions nobody.">
      <Select value={value ?? ""} disabled={members.length === 0} placeholder="Pick the bots first"
        options={members.map((bot) => ({ value: bot.id, label: bot.name }))} onChange={onChange} />
    </Field>
  );
}
```

- [ ] **Step 8: The styles**

Create `web/src/styles/ui-overlays.css`:

```css
/* ---------------------------------------------------------------------
   The Radix-based kit (redesign P1): Select, Menu, Tabs, Sheet, Popover
   and Tooltip. Their panels live in portals at the end of <body>, so
   nothing here depends on where the trigger sits. Tokens only.
   --------------------------------------------------------------------- */

/* ---- Select ----------------------------------------------------------- */

.select {
  display: inline-flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  width: 100%;
  padding: 0 var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-bg);
  color: var(--color-text);
  font: inherit;
  text-align: left;
  transition: border-color var(--duration-fast) var(--ease-standard);
}

.select--sm {
  height: var(--control-sm);
  font-size: var(--fs-label);
}

.select--md {
  height: var(--control-md);
}

.select--lg {
  height: var(--control-lg);
}

.select:hover {
  border-color: var(--color-border-strong);
}

.select:focus-visible {
  outline: none;
  border-color: var(--color-accent);
  box-shadow: var(--focus-ring);
}

.select:disabled {
  color: var(--color-text-faint);
  cursor: not-allowed;
}

.select[data-placeholder] {
  color: var(--color-text-faint);
}

.select__icon {
  display: inline-grid;
  color: var(--color-text-secondary);
}

.select__content,
.menu__list,
.popover {
  z-index: 50;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-overlay);
  box-shadow: var(--shadow-lg);
  color: var(--color-text);
}

.select__content {
  min-width: var(--radix-select-trigger-width);
  max-height: var(--radix-select-content-available-height);
  overflow: hidden;
}

.select__viewport {
  padding: var(--space-1);
}

.select__item,
.menu__item {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-height: var(--control-md);
  padding: 0 var(--space-3);
  border-radius: var(--radius-sm);
  color: var(--color-text);
  font-size: var(--fs-body);
  text-decoration: none;
  cursor: pointer;
  user-select: none;
  outline: none;
}

.select__item[data-highlighted],
.menu__item[data-highlighted] {
  background: var(--color-raised);
}

.select__item[data-disabled],
.menu__item[data-disabled] {
  opacity: 0.45;
  cursor: default;
}

.select__check {
  display: inline-grid;
  margin-left: auto;
  color: var(--color-accent-strong);
}

/* ---- Menu ------------------------------------------------------------- */

.menu {
  position: relative;
  flex: none;
}

.menu__list {
  display: flex;
  flex-direction: column;
  min-width: 220px;
  padding: var(--space-1);
}

.menu__note {
  margin: 0;
  padding: var(--space-2) var(--space-3);
  color: var(--color-text-secondary);
  font-size: var(--fs-label);
}

/* ---- Tabs: one style everywhere --------------------------------------- */

.tabs {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.tabs__list {
  display: flex;
  gap: var(--space-1);
  padding: var(--space-1);
  overflow-x: auto;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-pill);
  background: var(--color-panel);
  scrollbar-width: none;
}

.tabs__tab {
  flex: 1 0 auto;
  min-height: var(--control-md);
  padding: 0 var(--space-4);
  border: none;
  border-radius: var(--radius-pill);
  background: none;
  color: var(--color-text-secondary);
  font: inherit;
  font-size: var(--fs-label);
  font-weight: 600;
  transition:
    background-color var(--duration-fast) var(--ease-standard),
    color var(--duration-fast) var(--ease-standard);
}

.tabs__tab:hover {
  color: var(--color-text);
}

.tabs__tab[data-state="active"] {
  background: var(--color-raised);
  color: var(--color-text);
}

.tabs__panel:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring);
  border-radius: var(--radius-sm);
}

/* ---- Sheet: a drawer from the right ----------------------------------- */

.ui-sheet__scrim {
  position: fixed;
  inset: 0;
  z-index: 40;
  background: var(--color-scrim);
}

.ui-sheet {
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  z-index: 41;
  display: flex;
  flex-direction: column;
  width: min(480px, 100vw);
  border-left: 1px solid var(--color-border);
  background: var(--color-panel);
  box-shadow: var(--shadow-lg);
}

.ui-sheet__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  padding: var(--space-4) var(--space-4) var(--space-2) var(--space-6);
}

.ui-sheet__title {
  margin: 0;
  font-size: var(--fs-heading);
  font-weight: 600;
}

.ui-sheet__description {
  margin: 0;
  padding: 0 var(--space-6);
  color: var(--color-text-secondary);
  font-size: var(--fs-body);
}

.ui-sheet__body {
  flex: 1;
  min-height: 0;
  padding: var(--space-4) var(--space-6);
  overflow-y: auto;
}

.ui-sheet__foot {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-2);
  padding: var(--space-3) var(--space-6);
  border-top: 1px solid var(--color-border);
}

@media (prefers-reduced-motion: no-preference) {
  .ui-sheet[data-state="open"] {
    animation: sheet-in var(--duration-slow) var(--ease-standard);
  }
}

@keyframes sheet-in {
  from {
    transform: translateX(24px);
    opacity: 0;
  }
}

/* ---- Popover and Tooltip ---------------------------------------------- */

.popover {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  max-width: calc(100vw - 2 * var(--space-4));
  padding: var(--space-3);
}

.tooltip {
  z-index: 70;
  padding: var(--space-1) var(--space-2);
  border-radius: var(--radius-xs);
  background: var(--color-text);
  color: var(--color-bg);
  font-size: var(--fs-caption);
  font-weight: 500;
  box-shadow: var(--shadow-sm);
}
```

`web/src/styles.css`. Find:

```css
@import "./styles/ui.css";
```

Replace with:

```css
@import "./styles/ui.css";
@import "./styles/ui-overlays.css";
```

One tab style everywhere: ui-overlays.css .tabs__*.

`web/src/styles/board.css`. Find:

```css
/* ---- Sub-tabs (pills, so they never read as a second header) --------- */

.board-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.board-tab {
  height: 32px;
  padding: 0 14px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-pill);
  background: var(--color-raised);
  color: var(--color-text-secondary);
  font-size: var(--fs-label);
  font-weight: 600;
  transition:
    color var(--duration-fast) var(--ease-standard),
    border-color var(--duration-fast) var(--ease-standard),
    background-color var(--duration-fast) var(--ease-standard);
}

.board-tab:hover {
  color: var(--color-text);
  border-color: var(--color-border-strong);
}

.board-tab--active,
.board-tab--active:hover {
  border-color: var(--color-accent-edge);
  background: var(--color-accent-tint);
  color: var(--color-accent-soft);
}

```

Delete it.

`web/src/styles/profile.css`. Find:

```css
/* ---- Pill tabs ------------------------------------------------------ */

.profile-tabs {
  display: flex;
  gap: 6px;
  padding: 4px;
  overflow-x: auto;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-pill);
  background: var(--color-panel);
  scrollbar-width: none;
}

.profile-tab {
  flex: 1 0 auto;
  min-height: 36px;
  padding: 0 16px;
  border: none;
  border-radius: var(--radius-pill);
  background: none;
  color: var(--color-text-secondary);
  font: inherit;
  font-size: var(--fs-label);
  font-weight: 600;
  transition:
    background-color var(--duration-fast) var(--ease-standard),
    color var(--duration-fast) var(--ease-standard);
}

.profile-tab:hover {
  color: var(--color-text);
}

.profile-tab--active {
  background: var(--color-raised);
  color: var(--color-text);
}

```

Delete it.

The menu lives in a portal now; Radix places it (ui-overlays.css styles it).

`web/src/styles/home.css`. Find:

```css
/* ---- Menu ------------------------------------------------------------ */

.menu {
  position: relative;
  flex: none;
}

.menu__list {
  position: absolute;
  top: calc(100% + 6px);
  right: 0;
  z-index: 20;
  display: flex;
  flex-direction: column;
  min-width: 220px;
  padding: 6px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-raised);
  box-shadow: var(--shadow-lg);
}

/* The account menu opens from the left edge, so it opens rightwards. */
.home-header > .menu .menu__list {
  right: auto;
  left: 0;
}

.menu__item {
  display: block;
  width: 100%;
  padding: 9px 12px;
  border: none;
  border-radius: var(--radius-sm);
  background: none;
  color: var(--color-text);
  font-size: var(--fs-body);
  text-align: left;
  text-decoration: none;
}

.menu__item:hover:not(:disabled),
.menu__item:focus-visible {
  background: var(--color-border);
}

.menu__item:disabled {
  opacity: 0.45;
  cursor: default;
}

.menu__note {
  margin: 0;
  padding: 6px 12px;
  color: var(--color-text-secondary);
  font-size: var(--fs-label);
}

.menu__note + .menu__item {
  margin-top: 4px;
}

```

Delete it.

Chat.tsx says side="top" instead.

`web/src/styles/chat.css`. Find:

```css
/* The + sits at the bottom of the screen, so its menu opens upwards. */
.chat-composer .menu__list {
  top: auto;
  right: auto;
  bottom: calc(100% + 8px);
  left: 0;
}

```

Delete it.

`web/src/styles/rooms.css`. Find:

```css
.dialog select.input:disabled {
  color: var(--color-text-faint);
  cursor: not-allowed;
}

```

Delete it.

- [ ] **Step 9: Run the tests to see them pass**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && cd web && npx vitest run tests/Select.test.tsx tests/Menu.test.tsx tests/Tabs.test.tsx tests/overlays.test.tsx tests/BotMenu.test.tsx tests/TasksBoard.test.tsx tests/ProjectsBoard.test.tsx tests/NewRoomDialog.test.tsx tests/tokens.test.ts`
Expected: PASS: `Select` 5, `Menu` 4, `Tabs` 3, `overlays` 5, `BotMenu` 4, `TasksBoard` 16, `ProjectsBoard` 11, `NewRoomDialog` 6 and `tokens` 7 tests.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && cd web && npm test && npm run build && npm run size`
Expected: every test file passes (`Board`, `Project`, `Profile`, `Home`, `Chat` and `ChatThreads` keep passing on the new tabs and menus), the build succeeds, the entry chunk is within the budget.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && grep -rn "<select\|board-tab\|profile-tab\|components/Menu\"" web/src`
Expected: no output.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && df -g /System/Volumes/Data | awk 'NR==2{print $4}'`
Expected: at least 8. Otherwise stop and report.

Run this as one shell call (`computer.spec` makes Scout, whom `team.spec`'s room needs):

```bash
cd /Users/blckit/Desktop/Code_Projects/roost && cd web && \
port=18800 && if curl -fsS -o /dev/null --max-time 2 http://127.0.0.1:18800/api/health; then port=5173; fi && \
npm run build && ROOST_E2E_PORT=$port npx playwright test e2e/computer.spec.ts e2e/team.spec.ts
```

Expected: 2 passed. If Playwright reports that the browser executable is missing, run `cd /Users/blckit/Desktop/Code_Projects/roost && cd web && npx playwright install chromium` (the disk guard has passed) and run it again.

- [ ] **Step 10: Commit**

Run:

```bash
cd /Users/blckit/Desktop/Code_Projects/roost && \
git add web/src/ui/Select.tsx web/src/ui/Menu.tsx web/src/ui/Tabs.tsx web/src/ui/Sheet.tsx \
  web/src/ui/Popover.tsx web/src/ui/Tooltip.tsx web/src/ui/IconButton.tsx web/src/ui/constants.ts \
  web/src/components/icons.tsx web/src/components/BotMenu.tsx web/src/components/NewRoomDialog.tsx \
  web/src/components/board/TaskEditForm.tsx web/src/components/projects/ProjectEditForm.tsx \
  web/src/pages/Board.tsx web/src/pages/Project.tsx web/src/pages/Profile.tsx web/src/pages/Home.tsx web/src/pages/Chat.tsx \
  web/src/styles.css web/src/styles/ui-overlays.css web/src/styles/board.css web/src/styles/profile.css \
  web/src/styles/home.css web/src/styles/chat.css web/src/styles/rooms.css \
  web/tests/setup.ts web/tests/Select.test.tsx web/tests/Menu.test.tsx web/tests/Tabs.test.tsx web/tests/overlays.test.tsx \
  web/tests/BotMenu.test.tsx web/tests/TasksBoard.test.tsx web/tests/ProjectsBoard.test.tsx \
  web/tests/NewRoomDialog.test.tsx web/tests/tokens.test.ts web/e2e/team.spec.ts && \
git commit -m "feat: Radix Select, Menu, Tabs, Sheet, Popover and Tooltip; one tab style; no native select left"
```

(`web/src/components/Menu.tsx` was staged as deleted by `git rm` in Step 5.)

### Task 4: DatePicker and DateTimePicker on Madrid time, with a lazy calendar

Design P1 "DatePicker and DateTimePicker" and Review Focus 2 and 4. Today a task's due is a free text box, a project's dates are two native `type="date"` inputs, and an expense has no day field at all (the gateway takes `spent_at`, the web never sends it).
- **One field you can type in.** `DateField` is a text box, a calendar button and a line under the box that says how the gateway reads it. `DatePicker` and `DateTimePicker` are two thin wrappers.
- **The value is what the gateway reads.** A quick pick or a calendar day writes a Madrid day (`2026-10-16`); a time chip writes Madrid wall time (`2026-10-16 09:00`); typing writes the words. "Today" is Madrid's today whatever the browser's zone (`todayIn`, `Intl` on `Europe/Madrid`); day arithmetic never touches a clock (`addDays` works on UTC noon); a stored timed due shows the wall time written in it (`pickerText`), never one converted to the browser's zone. Nothing is ever sent as an instant.
- **The preview is the existing parser.** Words are read by `GET /api/dates/parse`, a read-only route on `roost/tasks/due.py`'s `parse_due` (the reading a task's due already gets), 300 ms after the typing stops. A picked value needs no gateway.
- **Each form sends what its API takes.** A task's due takes words or ISO, so it goes as it is (today's contract). A project's dates take only `YYYY-MM-DD`, and an expense's day is read by another parser, so both forms turn words into a day with the preview's own reading before they save (`resolveDay`). What the user saw under the box is what is saved.
- **The forms:** the Board's "When" and the task edit form's "Due" are DateTimePickers; a project's "Starts" and "Due" are DatePickers; the expense form gains "Day" (Today, Yesterday, nothing after today; empty is today).
- **The calendar is lazy.** Only `ui/date/Calendar.tsx` imports react-day-picker, and only `CalendarPopover` reaches it, through `React.lazy`; its CSS (`calendar.css`, on react-day-picker's `rdp-*` class names) loads with it. `web/tests/bundleGuard.test.ts` pins both rules, and `npm run size` refuses an entry chunk that holds `rdp-`.

**Files:**
- Create:
  - `roost/gateway/routes/dates.py`, `tests/test_dates_api.py`
  - `web/src/api/dates.ts`, `web/src/ui/date/{dates,picks,useDateReading,resolve}.ts`, `web/src/ui/date/{Calendar,CalendarPopover,DateField,DatePicker,DateTimePicker}.tsx`
  - `web/src/styles/{date-field,calendar}.css`
  - `web/tests/{dates,bundleGuard}.test.ts`, `web/tests/{DateTimePicker,DatePicker,ExpenseAddForm}.test.tsx`
- Modify:
  - `roost/gateway/app.py`
  - `web/src/ui/constants.ts`, `web/src/components/icons.tsx` (`CalendarIcon`), `web/src/api/money.ts`
  - `web/src/components/board/{taskLimits.ts,TaskAddForm.tsx,TaskEditForm.tsx,ExpenseAddForm.tsx}`, `web/src/components/projects/ProjectEditForm.tsx`
  - `web/src/styles.css`, `web/src/styles/{board,projects}.css`, `web/scripts/check-bundle.mjs`
  - `web/tests/{TasksBoard,ProjectsBoard}.test.tsx`
- Test: the new test files and the two changed ones

**Interfaces:**
- Consumes: Task 3's `Popover`, `IconButton` (with its tooltip), `Field`/`controlA11y`/`useFieldControl`, `Chip`, `cx`; `parse_due` (`roost/tasks/due.py`), `MAX_DUE_TEXT_LENGTH`, `CurrentUser`; `apiRequest`, `describeError`, `ApiError`.
- Produces (Shared Contract "Dates"): `GET /api/dates/parse`; `parseDate`, `DateReadOut`; `DatePicker`, `DateTimePicker`, `DateField`, `CalendarPopover`, `Calendar` (default, lazy); `FUTURE_PICKS`, `PAST_PICKS`, `TIME_CHIPS`, `QuickPick`; `todayIn`, `addDays`, `nextMonday`, `dueParts`, `joinDue`, `pickerText`, `friendlyDue`, `isIsoDay`, `dayToDate`, `dateToDay`, `APP_TIME_ZONE`, `IsoDay`, `WallTime`, `DueParts`; `useDateReading`, `DateReading`; `resolveDay`; `DATE_PREVIEW_DELAY_MS`, `MAX_DATE_TEXT`; `CalendarIcon`; `ExpenseIn.spent_at`. Names Task 7 relies on: the button "Open calendar", the panels "Pick a day" / "Pick a day and a time", the chips by their labels, the preview's `date-field__preview--read` class, the fields "When", "Due", "Starts", "Day".

- [ ] **Step 1: Path guard**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && git -C /Users/blckit/Desktop/Code_Projects/roost rev-parse --show-toplevel && git -C /Users/blckit/Desktop/Code_Projects/roost branch --show-current`
Expected: `/Users/blckit/Desktop/Code_Projects/roost` then `night-1`. If either differs, stop.

Then confirm Task 3 has landed and this task has not:

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && test -f web/src/ui/Popover.tsx && test ! -d web/src/ui/date && test ! -f roost/gateway/routes/dates.py && echo ready`
Expected: `ready`.

- [ ] **Step 2: Write the failing tests**

Create `tests/test_dates_api.py`:

```python
"""GET /api/dates/parse (redesign P1): the date pickers' typed-text preview, read the way a task's
due is read (parse_due, Europe/Madrid). A picked wall time is Madrid's clock, never UTC."""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from roost.gateway.app import create_app
from roost.talk.instructions import MADRID_TZ

O = {"Origin": "http://127.0.0.1:18800"}


def _client() -> TestClient:
    client = TestClient(create_app())
    assert client.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"},
                       headers=O).status_code == 201
    return client


def _read(client: TestClient, text: str):
    return client.get("/api/dates/parse", params={"text": text})


def test_words_read_on_madrid_time():
    client = _client()
    tomorrow = (datetime.now(MADRID_TZ) + timedelta(days=1)).date().isoformat()
    timed = _read(client, "tomorrow at 9").json()["due_date"]
    assert re.fullmatch(rf"{tomorrow}T09:00:00\+0[12]:00", timed)
    assert _read(client, "tomorrow").json() == {"due_date": tomorrow}


def test_a_picked_wall_time_is_read_on_madrid_time():
    client = _client()
    assert _read(client, "2026-10-16 09:00").json() == {"due_date": "2026-10-16T09:00:00+02:00"}   # summer time
    assert _read(client, "2026-12-01 09:00").json() == {"due_date": "2026-12-01T09:00:00+01:00"}   # winter time
    assert _read(client, "2026-10-16").json() == {"due_date": "2026-10-16"}


def test_no_text_is_no_date_and_unreadable_text_says_why():
    client = _client()
    assert _read(client, "").json() == {"due_date": None}
    refused = _read(client, "someday")
    assert refused.status_code == 422
    assert refused.json()["detail"] == "I could not read a date in “someday”. Try “tomorrow at 9” or 2026-10-20."


def test_it_needs_a_login_and_refuses_a_novel():
    assert TestClient(create_app()).get("/api/dates/parse", params={"text": "tomorrow"}).status_code == 401
    assert _read(_client(), "x" * 101).status_code == 422
```

Create `web/tests/dates.test.ts`:

```ts
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import {
  addDays, dateToDay, dayToDate, dueParts, friendlyDue, isIsoDay, joinDue, nextMonday, pickerText, todayIn,
} from "../src/ui/date/dates";

// Far from Madrid, so a helper that leaned on the browser's zone would show it.
const BROWSER_ZONE = "America/Los_Angeles";
let savedZone: string | undefined;
beforeAll(() => { savedZone = process.env.TZ; process.env.TZ = BROWSER_ZONE; });
afterAll(() => { process.env.TZ = savedZone; });
afterEach(() => vi.useRealTimers());

describe("Madrid days", () => {
  it("today is Madrid's day, not UTC's or the browser's", () => {
    // 22:30 UTC on the 15th is 00:30 on the 16th in Madrid (CEST) and 15:30 on the 15th in Los Angeles.
    expect(todayIn(new Date("2026-10-15T22:30:00Z"))).toBe("2026-10-16");
    // In winter (CET) Madrid is UTC+1: 23:30 UTC on 1 Dec is 00:30 on 2 Dec.
    expect(todayIn(new Date("2026-12-01T23:30:00Z"))).toBe("2026-12-02");
  });

  it("adds days across months, years and the night the clocks go back", () => {
    expect(addDays("2026-10-31", 1)).toBe("2026-11-01");
    expect(addDays("2026-12-31", 1)).toBe("2027-01-01");
    expect(addDays("2026-10-25", 1)).toBe("2026-10-26"); // Madrid's last Sunday of October
    expect(addDays("2026-03-01", -1)).toBe("2026-02-28");
  });

  it("next week is the next Monday", () => {
    expect(nextMonday("2026-10-15")).toBe("2026-10-19"); // a Thursday
    expect(nextMonday("2026-10-19")).toBe("2026-10-26"); // a Monday gives the one after
    expect(nextMonday("2026-10-18")).toBe("2026-10-19"); // a Sunday
  });

  it("knows a real day from a near miss", () => {
    expect(isIsoDay("2026-10-16")).toBe(true);
    expect(isIsoDay("2026-02-30")).toBe(false);
    expect(isIsoDay("16/10/2026")).toBe(false);
  });
});

describe("what a picker holds", () => {
  it("reads a stored timed due as its Madrid wall time, whatever the browser's zone", () => {
    expect(dueParts("2026-10-14T23:30:00+02:00")).toEqual({ day: "2026-10-14", time: "23:30" });
    expect(pickerText("2026-10-14T09:00:00+02:00")).toBe("2026-10-14 09:00");
    expect(pickerText("2026-10-14")).toBe("2026-10-14");
    expect(pickerText(null)).toBe("");
  });

  it("sends a day, or a day and a wall time, never an instant", () => {
    expect(joinDue("2026-10-17", null)).toBe("2026-10-17");
    expect(joinDue("2026-10-17", "09:00")).toBe("2026-10-17 09:00");
    expect(dueParts("2026-10-17 09:00")).toEqual({ day: "2026-10-17", time: "09:00" });
    expect(dueParts("tomorrow at 9")).toBeNull();
  });

  it("says a day the friendly way", () => {
    expect(friendlyDue({ day: "2026-10-16", time: null })).toBe("Fri 16 Oct 2026");
    expect(friendlyDue({ day: "2026-10-16", time: "09:00" })).toBe("Fri 16 Oct 2026, 09:00");
    expect(friendlyDue({ day: "2026-10-16", time: "09:00" }, false)).toBe("Fri 16 Oct 2026");
  });

  it("the calendar's dates round-trip to the same day in any zone", () => {
    for (const day of ["2026-10-25", "2026-03-29", "2026-12-31"]) expect(dateToDay(dayToDate(day))).toBe(day);
  });
});
```

Create `web/tests/DateTimePicker.test.tsx`:

```tsx
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { Field } from "../src/ui/Field";
import { DateTimePicker } from "../src/ui/date/DateTimePicker";

const parseDateMock = vi.fn();
vi.mock("../src/api/dates", () => ({ parseDate: (text: string) => parseDateMock(text) }));

// A browser far from Madrid, late in its evening: 22:30 UTC on 15 Oct 2026 is already the 16th in Madrid.
const NOW = new Date("2026-10-15T22:30:00Z");
let savedZone: string | undefined;
beforeAll(() => { savedZone = process.env.TZ; process.env.TZ = "America/Los_Angeles"; });
afterAll(() => { process.env.TZ = savedZone; });
beforeEach(() => {
  parseDateMock.mockReset();
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(NOW);
});
afterEach(() => { cleanup(); vi.useRealTimers(); });

function Due({ initial = "", onChange = vi.fn() }: { initial?: string; onChange?: (value: string) => void }) {
  const [value, setValue] = useState(initial);
  return (
    <Field label="Due">
      <DateTimePicker value={value} onChange={(next) => { setValue(next); onChange(next); }} />
    </Field>
  );
}

async function openCalendar(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: "Open calendar" }));
  return screen.getByRole("dialog", { name: "Pick a day and a time" });
}

describe("DateTimePicker", () => {
  it("sends Madrid's day and Madrid wall time from a browser in Los Angeles, never a UTC instant", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<Due onChange={onChange} />);
    await openCalendar(user);
    await user.click(screen.getByRole("button", { name: "Tomorrow" }));
    expect(onChange).toHaveBeenLastCalledWith("2026-10-17"); // Madrid's tomorrow; the browser's would be the 16th
    await user.click(screen.getByRole("button", { name: "09:00" }));
    expect(onChange).toHaveBeenLastCalledWith("2026-10-17 09:00");
    expect(onChange.mock.calls.flat().some((value: string) => /Z$|[+-]\d{2}:\d{2}$/.test(value))).toBe(false);
    expect(screen.getByLabelText("Due")).toHaveValue("2026-10-17 09:00");
    expect(screen.getByText("Sat 17 Oct 2026, 09:00")).toBeInTheDocument();
    expect(parseDateMock).not.toHaveBeenCalled(); // a picked value needs no gateway
  });

  it("shows a stored due at its Madrid wall time", () => {
    render(<Due initial="2026-10-14 23:30" />);
    expect(screen.getByLabelText("Due")).toHaveValue("2026-10-14 23:30");
    expect(screen.getByText("Wed 14 Oct 2026, 23:30")).toBeInTheDocument();
  });

  it("a new day keeps the time already chosen, and No time drops it", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<Due initial="2026-10-20 15:00" onChange={onChange} />);
    await openCalendar(user);
    await user.click(screen.getByRole("button", { name: "Next week" }));
    expect(onChange).toHaveBeenLastCalledWith("2026-10-19 15:00");
    await user.click(screen.getByRole("button", { name: "No time" }));
    expect(onChange).toHaveBeenLastCalledWith("2026-10-19");
  });

  it("No date empties it", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<Due initial="2026-10-20" onChange={onChange} />);
    await openCalendar(user);
    await user.click(screen.getByRole("button", { name: "No date" }));
    expect(onChange).toHaveBeenLastCalledWith("");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("typed words go out as typed, and the line under says how the gateway reads them", async () => {
    parseDateMock.mockResolvedValue({ due_date: "2026-10-17T09:00:00+02:00" });
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<Due onChange={onChange} />);
    await user.type(screen.getByLabelText("Due"), "tomorrow at 9");
    expect(onChange).toHaveBeenLastCalledWith("tomorrow at 9");
    expect(await screen.findByText("Sat 17 Oct 2026, 09:00")).toBeInTheDocument();
    expect(parseDateMock).toHaveBeenLastCalledWith("tomorrow at 9");
  });

  it("says why words can't be read, and marks the box", async () => {
    const { ApiError } = await import("../src/api/client");
    parseDateMock.mockRejectedValue(new ApiError(422, "I could not read a date in “someday”. Try “tomorrow at 9” or 2026-10-20."));
    const user = userEvent.setup();
    render(<Due />);
    await user.type(screen.getByLabelText("Due"), "someday");
    expect(await screen.findByText(/I could not read a date in “someday”/)).toBeInTheDocument();
    expect(screen.getByLabelText("Due")).toHaveAttribute("aria-invalid", "true");
  });

  it("picks a day on the lazy calendar", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<Due onChange={onChange} />);
    await openCalendar(user);
    await user.click(await screen.findByRole("button", { name: /October 20th, 2026/ }));
    expect(onChange).toHaveBeenLastCalledWith("2026-10-20");
  });
});
```

Create `web/tests/DatePicker.test.tsx`:

```tsx
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { DatePicker } from "../src/ui/date/DatePicker";
import { PAST_PICKS } from "../src/ui/date/picks";
import { resolveDay } from "../src/ui/date/resolve";

const parseDateMock = vi.fn();
vi.mock("../src/api/dates", () => ({ parseDate: (text: string) => parseDateMock(text) }));

beforeEach(() => {
  parseDateMock.mockReset();
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-10-15T10:00:00Z"));
});
afterEach(() => { cleanup(); vi.useRealTimers(); });

function Day({ onChange = vi.fn(), past = false }: { onChange?: (value: string) => void; past?: boolean }) {
  const [value, setValue] = useState("");
  return (
    <DatePicker label="Day" value={value} picks={past ? PAST_PICKS : undefined} max={past ? "2026-10-15" : undefined}
      onChange={(next) => { setValue(next); onChange(next); }} />
  );
}

describe("DatePicker", () => {
  it("offers Today, Tomorrow, Next week and No date, and has no time chips", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<Day onChange={onChange} />);
    await user.click(screen.getByRole("button", { name: "Open calendar" }));
    const panel = screen.getByRole("dialog", { name: "Pick a day" });
    expect(panel).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Time" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Tomorrow" }));
    expect(onChange).toHaveBeenLastCalledWith("2026-10-16");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByText("Fri 16 Oct 2026")).toBeInTheDocument();
  });

  it("a day that names a time shows only the day", async () => {
    parseDateMock.mockResolvedValue({ due_date: "2026-10-16T09:00:00+02:00" });
    const user = userEvent.setup();
    render(<Day />);
    await user.type(screen.getByRole("textbox", { name: "Day" }), "tomorrow at 9");
    expect(await screen.findByText("Fri 16 Oct 2026")).toBeInTheDocument();
  });

  it("an expense's day looks back, and the calendar offers nothing after today", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<Day past onChange={onChange} />);
    await user.click(screen.getByRole("button", { name: "Open calendar" }));
    expect(screen.queryByRole("button", { name: "No date" })).not.toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /October 16th, 2026/ })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Yesterday" }));
    expect(onChange).toHaveBeenLastCalledWith("2026-10-14");
  });
});

describe("resolveDay", () => {
  it("keeps a picked day, empties an empty field, and has the gateway read words", async () => {
    expect(await resolveDay("2026-10-20")).toBe("2026-10-20");
    expect(await resolveDay("  ")).toBeNull();
    parseDateMock.mockResolvedValue({ due_date: "2026-10-19T09:00:00+02:00" });
    expect(await resolveDay("next monday at 9")).toBe("2026-10-19");
    expect(parseDateMock).toHaveBeenCalledTimes(1);
  });
});
```

Create `web/tests/bundleGuard.test.ts`:

```ts
// @vitest-environment node
import { readdirSync, readFileSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

// The main bundle stays within bundle-budget.json (redesign P1): the calendar (react-day-picker and
// date-fns) loads only when a calendar opens. A static import anywhere would pull it into the entry.
const SRC = fileURLToPath(new URL("../src/", import.meta.url));
const CALENDAR = "ui/date/Calendar.tsx";
const STATIC_IMPORT = /^\s*import\s[^;]*?from\s+["']([^"']+)["']/gm;
const BARE_IMPORT = /^\s*import\s+["']([^"']+)["']/gm;

function sources(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return sources(path);
    return /\.(ts|tsx)$/.test(entry.name) ? [path] : [];
  });
}

function staticImports(path: string): string[] {
  const text = readFileSync(path, "utf8");
  return [...text.matchAll(STATIC_IMPORT), ...text.matchAll(BARE_IMPORT)].map((match) => match[1]);
}

describe("bundle guard (redesign P1)", () => {
  it("imports react-day-picker only in the lazy calendar chunk", () => {
    const importers = sources(SRC)
      .filter((path) => staticImports(path).some((spec) => spec === "react-day-picker" || spec.startsWith("react-day-picker/")))
      .map((path) => relative(SRC, path));
    expect(importers).toEqual([CALENDAR]);
  });

  it("nothing imports the calendar statically: it is reached through React.lazy only", () => {
    const importers = sources(SRC)
      .filter((path) => staticImports(path).some((spec) => /(^|\/)Calendar$/.test(spec)))
      .map((path) => relative(SRC, path));
    expect(importers).toEqual([]);
    const popover = readFileSync(join(SRC, "ui/date/CalendarPopover.tsx"), "utf8");
    expect(popover).toContain('lazy(() => import("./Calendar"))');
  });
});
```

Create `web/tests/ExpenseAddForm.test.tsx`:

```tsx
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ExpenseAddForm } from "../src/components/board/ExpenseAddForm";

const createExpenseMock = vi.fn();
vi.mock("../src/api/money", () => ({ createExpense: (input: unknown) => createExpenseMock(input) }));
const parseDateMock = vi.fn();
vi.mock("../src/api/dates", () => ({ parseDate: (text: string) => parseDateMock(text) }));

beforeEach(() => {
  createExpenseMock.mockReset().mockResolvedValue({});
  parseDateMock.mockReset();
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-10-15T22:30:00Z")); // already the 16th in Madrid
});
afterEach(() => { cleanup(); vi.useRealTimers(); });

describe("ExpenseAddForm's day", () => {
  it("sends no day when left empty: the gateway takes today", async () => {
    const user = userEvent.setup();
    render(<ExpenseAddForm projects={[]} fixedProjectId="p1" onAdded={vi.fn()} />);
    await user.type(screen.getByLabelText("Amount"), "9,90");
    await user.click(screen.getByRole("button", { name: "Add expense" }));
    expect(createExpenseMock).toHaveBeenCalledWith({ amount: "9.90", project_id: "p1", note: undefined });
  });

  it("Yesterday sends Madrid's yesterday", async () => {
    const user = userEvent.setup();
    render(<ExpenseAddForm projects={[]} fixedProjectId="p1" onAdded={vi.fn()} />);
    await user.type(screen.getByLabelText("Amount"), "9,90");
    await user.click(screen.getByRole("button", { name: "Open calendar" }));
    await user.click(screen.getByRole("button", { name: "Yesterday" }));
    await user.click(screen.getByRole("button", { name: "Add expense" }));
    expect(createExpenseMock).toHaveBeenCalledWith({ amount: "9.90", project_id: "p1", note: undefined, spent_at: "2026-10-15" });
  });

  it("a typed day is read by the gateway first, and its refusal is shown", async () => {
    const { ApiError } = await import("../src/api/client");
    parseDateMock.mockRejectedValue(new ApiError(422, "I could not read a date in “someday”. Try “tomorrow at 9” or 2026-10-20."));
    const user = userEvent.setup();
    render(<ExpenseAddForm projects={[]} fixedProjectId="p1" onAdded={vi.fn()} />);
    await user.type(screen.getByLabelText("Amount"), "9,90");
    await user.type(screen.getByRole("textbox", { name: "Day" }), "someday");
    await user.click(screen.getByRole("button", { name: "Add expense" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("I could not read a date in “someday”.");
    expect(createExpenseMock).not.toHaveBeenCalled();
  });
});
```

`web/tests/TasksBoard.test.tsx`. Find:

```tsx
vi.mock("../src/hooks/useLiveStore", () => ({ useLiveState: () => live }));
```

Replace with:

```tsx
vi.mock("../src/hooks/useLiveStore", () => ({ useLiveState: () => live }));
const parseDateMock = vi.fn().mockResolvedValue({ due_date: null });
vi.mock("../src/api/dates", () => ({ parseDate: (text: string) => parseDateMock(text) }));
```

`web/tests/TasksBoard.test.tsx`. Find:

```tsx
  it("offers Keep only on a web-made task, and keeping it reloads", async () => {
```

Replace with:

```tsx
  it("adds a task due at a picked day and time, as Madrid wall time", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-10-15T10:00:00Z"));
    createTaskMock.mockResolvedValue(task({ id: "t3", title: "Water the plants" }));
    const user = userEvent.setup();
    render(<TasksBoard />);
    await user.type(await screen.findByLabelText("New task"), "Water the plants");
    await user.click(screen.getByRole("button", { name: "Open calendar" }));
    await user.click(screen.getByRole("button", { name: "Tomorrow" }));
    await user.click(screen.getByRole("button", { name: "09:00" }));
    expect(screen.getByLabelText("When")).toHaveValue("2026-10-16 09:00");
    await user.click(screen.getByRole("button", { name: "Add" }));
    expect(createTaskMock).toHaveBeenCalledWith({ title: "Water the plants", due_date: "2026-10-16 09:00" });
    vi.useRealTimers();
  });

  it("offers Keep only on a web-made task, and keeping it reloads", async () => {
```

`web/tests/ProjectsBoard.test.tsx`. Find:

```tsx
vi.mock("../src/hooks/useLiveStore", () => ({ useLiveState: () => live }));
```

Replace with:

```tsx
vi.mock("../src/hooks/useLiveStore", () => ({ useLiveState: () => live }));
const parseDateMock = vi.fn();
vi.mock("../src/api/dates", () => ({ parseDate: (text: string) => parseDateMock(text) }));
```

`web/tests/ProjectsBoard.test.tsx`. Find:

```tsx
  it("refuses an amount or a currency it can't read before calling the gateway", async () => {
```

Replace with:

```tsx
  it("reads a typed start day through the gateway and saves the day", async () => {
    parseDateMock.mockResolvedValue({ due_date: "2026-10-19" });
    createProjectMock.mockResolvedValue(makeProject({ id: "p3", name: "Kitchen" }));
    const user = userEvent.setup();
    render(board());
    const form = await openNewProject(user);
    await user.type(within(form).getByLabelText("Name"), "Kitchen");
    await user.type(within(form).getByLabelText("Starts"), "next monday");
    expect(await within(form).findByText("Mon 19 Oct 2026")).toBeInTheDocument();
    await user.click(within(form).getByRole("button", { name: "Create project" }));
    expect(parseDateMock).toHaveBeenLastCalledWith("next monday");
    expect(createProjectMock).toHaveBeenCalledWith(expect.objectContaining({ start_date: "2026-10-19", due_date: null }));
  });

  it("refuses an amount or a currency it can't read before calling the gateway", async () => {
```

- [ ] **Step 3: Run them to see them fail**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_dates_api.py -q`
Expected: FAIL, 4 failed: the route does not exist (`{'detail': 'Not Found'}`, and a 404 where the login test wants 401).

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && cd web && npx vitest run tests/dates.test.ts tests/DateTimePicker.test.tsx tests/DatePicker.test.tsx tests/bundleGuard.test.ts tests/ExpenseAddForm.test.tsx tests/TasksBoard.test.tsx tests/ProjectsBoard.test.tsx`
Expected: FAIL, 7 files:
- `dates`, `DateTimePicker`, `DatePicker`: `Failed to resolve import "../src/ui/date/…"`.
- `bundleGuard`: `expected [] to deeply equal [ 'ui/date/Calendar.tsx' ]`, and `ENOENT … CalendarPopover.tsx`.
- `ExpenseAddForm`: 2 failed (no "Open calendar" button, no "Day" box); the empty-day test passes already.
- `TasksBoard`: `adds a task due at a picked day and time, as Madrid wall time` (no "Open calendar").
- `ProjectsBoard`: `reads a typed start day through the gateway and saves the day` (no preview line).

- [ ] **Step 4: The gateway reads a typed date**

Create `roost/gateway/routes/dates.py`:

```python
"""``GET /api/dates/parse``: how the gateway reads a typed date (look & feel redesign P1). The web's
date pickers show it under the box while the user types. It is the same reading a task's due gets
(``roost.tasks.due.parse_due``, on Europe/Madrid), and it changes nothing."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from roost.constants import MAX_DUE_TEXT_LENGTH
from roost.gateway.deps import CurrentUser
from roost.tasks.due import parse_due

dates_router = APIRouter(prefix="/api/dates", tags=["dates"])


@dates_router.get("/parse")
async def parse_date(user: CurrentUser, text: str = Query(default="", max_length=MAX_DUE_TEXT_LENGTH)):
    """``{"due_date": "2026-10-16"}``, ``{"due_date": "2026-10-16T09:00:00+02:00"}`` when the words name
    a time, ``{"due_date": null}`` for no text; 422 with the parser's sentence when it can't read it."""
    try:
        due = parse_due(text)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"due_date": due.due_date}
```

`roost/gateway/app.py`. Find:

```python
from roost.gateway.routes.chats import chats_router
```

Replace with:

```python
from roost.gateway.routes.chats import chats_router
from roost.gateway.routes.dates import dates_router
```

`roost/gateway/app.py`. Find:

```python
    app.include_router(tasks_router)
```

Replace with:

```python
    app.include_router(tasks_router)
    app.include_router(dates_router)
```

- [ ] **Step 5: Madrid days, quick picks and the reading**

Create `web/src/api/dates.ts`:

```ts
import { apiRequest } from "./client";

// How the gateway reads a typed date (GET /api/dates/parse): the same parser a task's due uses
// (roost/tasks/due.py parse_due), on Madrid time. "" reads as no date (null). It changes nothing.
export interface DateReadOut {
  due_date: string | null; // "2026-10-16", or "2026-10-16T09:00:00+02:00" when the words name a time
}

export function parseDate(text: string): Promise<DateReadOut> {
  return apiRequest<DateReadOut>("GET", `/api/dates/parse?text=${encodeURIComponent(text)}`);
}
```

`web/src/ui/constants.ts`. Find:

```ts
export const TOOLTIP_DELAY_MS = 400; // hover this long before a tooltip shows
```

Replace with:

```ts
export const TOOLTIP_DELAY_MS = 400; // hover this long before a tooltip shows
export const DATE_PREVIEW_DELAY_MS = 300; // typing pauses this long before the gateway reads a date
export const MAX_DATE_TEXT = 100; // the gateway's MAX_DUE_TEXT_LENGTH (roost/constants.py)
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

export function CalendarIcon() {
  return (
    <Icon>
      <rect x={3} y={4.5} width={14} height={12.5} rx={2} />
      <path d="M3 8.5h14M7 2.5v4M13 2.5v4" />
    </Icon>
  );
}
```

Create `web/src/ui/date/dates.ts`:

```ts
// Days and wall times on Madrid's calendar (redesign P1). A picker never turns a day into an instant:
// "2026-10-16" is a Madrid day and "2026-10-16 09:00" is 09:00 on Madrid's clock, both exactly as the
// gateway reads them (roost/tasks/due.py). Only "today" needs the clock, and it asks Madrid.

export const APP_TIME_ZONE = "Europe/Madrid";

export type IsoDay = string; // "YYYY-MM-DD"
export type WallTime = string; // "HH:MM"

export interface DueParts {
  day: IsoDay;
  time: WallTime | null;
}

const ISO_DAY = /^(\d{4})-(\d{2})-(\d{2})$/;
// A picked or stored timed due: "2026-10-16 09:00", "2026-10-16T09:00", "2026-10-16T09:00:00+02:00".
const ISO_DAY_TIME = /^(\d{4}-\d{2}-\d{2})[T ](\d{2}):(\d{2})(?::\d{2})?(?:Z|[+-]\d{2}:\d{2})?$/;
const DAY_FORMAT = new Intl.DateTimeFormat("en-CA", { timeZone: APP_TIME_ZONE, year: "numeric", month: "2-digit", day: "2-digit" });
const FRIENDLY_DAY = new Intl.DateTimeFormat("en-GB", {
  weekday: "short", day: "numeric", month: "short", year: "numeric", timeZone: "UTC",
});
const DAYS_PER_WEEK = 7;

function utcNoon(day: IsoDay): Date {
  const [year, month, date] = day.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, date, 12));
}

export function isIsoDay(text: string): boolean {
  const match = ISO_DAY.exec(text);
  if (!match) return false;
  return utcNoon(text).toISOString().slice(0, 10) === text; // 2026-02-30 is not a day
}

/** Today on Madrid's calendar, whatever the browser's own zone. */
export function todayIn(now: Date = new Date()): IsoDay {
  const parts = DAY_FORMAT.formatToParts(now);
  const part = (type: Intl.DateTimeFormatPartTypes) => parts.find((p) => p.type === type)?.value ?? "";
  return `${part("year")}-${part("month")}-${part("day")}`;
}

/** Calendar arithmetic on days alone: no clock, so no time zone and no daylight saving. */
export function addDays(day: IsoDay, count: number): IsoDay {
  const moved = utcNoon(day);
  moved.setUTCDate(moved.getUTCDate() + count);
  return moved.toISOString().slice(0, 10);
}

/** The Monday after `day` (a Monday gives the next one). */
export function nextMonday(day: IsoDay): IsoDay {
  const weekday = (utcNoon(day).getUTCDay() + DAYS_PER_WEEK - 1) % DAYS_PER_WEEK; // Monday 0
  return addDays(day, DAYS_PER_WEEK - weekday);
}

/** The day and wall time a picked or stored value names, or null for words the gateway must read. */
export function dueParts(text: string): DueParts | null {
  const value = text.trim();
  if (isIsoDay(value)) return { day: value, time: null };
  const timed = ISO_DAY_TIME.exec(value);
  if (!timed || !isIsoDay(timed[1])) return null;
  return { day: timed[1], time: `${timed[2]}:${timed[3]}` };
}

/** What a picker sends: "2026-10-16", or "2026-10-16 09:00" (Madrid wall time, no offset). */
export function joinDue(day: IsoDay, time: WallTime | null): string {
  return time ? `${day} ${time}` : day;
}

/** A stored due (TaskOut.due_date) as the picker's text: its Madrid day and wall time as written. */
export function pickerText(due: string | null): string {
  if (!due) return "";
  const parts = dueParts(due);
  return parts ? joinDue(parts.day, parts.time) : due;
}

/** "Fri 16 Oct 2026", or "Fri 16 Oct 2026, 09:00". */
export function friendlyDue(parts: DueParts, withTime = true): string {
  const day = FRIENDLY_DAY.format(utcNoon(parts.day)).replace(",", "");
  return withTime && parts.time ? `${day}, ${parts.time}` : day;
}

// The calendar grid works in local Date objects: a day goes in as local noon and comes back by its
// local fields, so the browser's zone never moves it.
export function dayToDate(day: IsoDay): Date {
  const [year, month, date] = day.split("-").map(Number);
  return new Date(year, month - 1, date, 12);
}

export function dateToDay(date: Date): IsoDay {
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}
```

Create `web/src/ui/date/picks.ts`:

```ts
import { addDays, nextMonday, type IsoDay, type WallTime } from "./dates";

// A one-tap day: from Madrid's today to a day, or null for "No date".
export interface QuickPick {
  label: string;
  day: (today: IsoDay) => IsoDay | null;
}

// Due dates and project dates look ahead.
export const FUTURE_PICKS: readonly QuickPick[] = [
  { label: "Today", day: (today) => today },
  { label: "Tomorrow", day: (today) => addDays(today, 1) },
  { label: "Next week", day: (today) => nextMonday(today) },
  { label: "No date", day: () => null },
];

// An expense looks back; an empty day is today (the gateway's default), so there is no "No date".
export const PAST_PICKS: readonly QuickPick[] = [
  { label: "Today", day: (today) => today },
  { label: "Yesterday", day: (today) => addDays(today, -1) },
];

// The DateTimePicker's time chips, on Madrid's clock.
export const TIME_CHIPS: readonly WallTime[] = ["09:00", "12:00", "15:00", "18:00"];
```

Create `web/src/ui/date/useDateReading.ts`:

```ts
import { useEffect, useState } from "react";
import { parseDate } from "../../api/dates";
import { describeError } from "../../api/client";
import { DATE_PREVIEW_DELAY_MS } from "../constants";
import { dueParts, type DueParts } from "./dates";

export type DateReading =
  | { kind: "empty" }
  | { kind: "reading" }
  | { kind: "read"; parts: DueParts }
  | { kind: "error"; message: string };

// A picked value needs no gateway; words do.
function readLocally(text: string): DateReading | null {
  const value = text.trim();
  if (!value) return { kind: "empty" };
  const parts = dueParts(value);
  return parts ? { kind: "read", parts } : null;
}

function fromServer(due: string | null): DateReading {
  if (!due) return { kind: "empty" };
  const parts = dueParts(due);
  return parts ? { kind: "read", parts } : { kind: "error", message: `I could not read “${due}”.` };
}

// How the gateway reads what the user typed, once they pause (the existing natural-language parser,
// on Madrid time). Only the newest text's answer is kept.
export function useDateReading(text: string): DateReading {
  const local = readLocally(text);
  const [answer, setAnswer] = useState<{ text: string; reading: DateReading } | null>(null);
  const needsServer = local === null;
  useEffect(() => {
    if (!needsServer) return;
    let current = true;
    const timer = window.setTimeout(() => {
      parseDate(text.trim())
        .then((out) => { if (current) setAnswer({ text, reading: fromServer(out.due_date) }); })
        .catch((err: unknown) => { if (current) setAnswer({ text, reading: { kind: "error", message: describeError(err) } }); });
    }, DATE_PREVIEW_DELAY_MS);
    return () => { current = false; window.clearTimeout(timer); };
  }, [text, needsServer]);
  if (local) return local;
  return answer && answer.text === text ? answer.reading : { kind: "reading" };
}
```

- [ ] **Step 6: The pickers and the lazy calendar**

Create `web/src/ui/date/Calendar.tsx`:

```tsx
import { DayPicker } from "react-day-picker";
import "../../styles/calendar.css";
import { dateToDay, dayToDate, type IsoDay } from "./dates";

export interface CalendarProps {
  selected: IsoDay | null;
  today: IsoDay; // Madrid's today, not the browser's
  max?: IsoDay; // the last day it offers
  onSelect: (day: IsoDay) => void;
}

// The month grid (react-day-picker), its own lazy chunk: only CalendarPopover imports it, through
// React.lazy, so the main bundle never carries it (tests/bundleGuard.test.ts).
export default function Calendar({ selected, today, max, onSelect }: CalendarProps) {
  const chosen = selected ? dayToDate(selected) : undefined;
  return (
    <DayPicker mode="single" selected={chosen} defaultMonth={chosen ?? dayToDate(today)} today={dayToDate(today)}
      weekStartsOn={1} disabled={max ? { after: dayToDate(max) } : undefined}
      onSelect={(date) => { if (date) onSelect(dateToDay(date)); }} />
  );
}
```

Create `web/src/ui/date/CalendarPopover.tsx`:

```tsx
import { lazy, Suspense, useState } from "react";
import { CalendarIcon } from "../../components/icons";
import { Chip } from "../Chip";
import { IconButton } from "../IconButton";
import { Popover } from "../Popover";
import { dueParts, joinDue, todayIn, type IsoDay, type WallTime } from "./dates";
import { TIME_CHIPS, type QuickPick } from "./picks";

const Calendar = lazy(() => import("./Calendar"));

export interface CalendarPopoverProps {
  value: string; // the field's text
  withTime: boolean;
  picks: readonly QuickPick[];
  max?: IsoDay;
  disabled?: boolean;
  onPick: (value: string) => void;
}

function TimeChips({ day, time, onPick }: { day: IsoDay; time: WallTime | null; onPick: (value: string) => void }) {
  return (
    <div className="date-pop__row" role="group" aria-label="Time">
      {TIME_CHIPS.map((chip) => (
        <Chip key={chip} size="sm" selected={time === chip} onClick={() => onPick(joinDue(day, chip))}>{chip}</Chip>
      ))}
      {time ? <Chip size="sm" onClick={() => onPick(joinDue(day, null))}>No time</Chip> : null}
    </div>
  );
}

// The calendar button and its panel: quick picks, the month grid, and for a due its time chips. A
// day keeps the time already chosen; the panel closes once the value is complete.
export function CalendarPopover({ value, withTime, picks, max, disabled = false, onPick }: CalendarPopoverProps) {
  const [open, setOpen] = useState(false);
  const today = todayIn();
  const parts = dueParts(value);
  const pickDay = (day: IsoDay | null) => {
    onPick(day ? joinDue(day, parts?.time ?? null) : "");
    if (!withTime || day === null) setOpen(false);
  };
  const pickTime = (next: string) => { onPick(next); setOpen(false); };
  return (
    <Popover open={open} onOpenChange={setOpen} label={withTime ? "Pick a day and a time" : "Pick a day"}
      trigger={<IconButton label="Open calendar" icon={<CalendarIcon />} variant="secondary" disabled={disabled} />}>
      <div className="date-pop__row" role="group" aria-label="Quick picks">
        {picks.map((pick) => (
          <Chip key={pick.label} size="sm" onClick={() => pickDay(pick.day(today))}>{pick.label}</Chip>
        ))}
      </div>
      <Suspense fallback={<p className="date-pop__loading">Loading the calendar…</p>}>
        <Calendar selected={parts?.day ?? null} today={today} max={max} onSelect={(day) => pickDay(day)} />
      </Suspense>
      {withTime ? <TimeChips day={parts?.day ?? today} time={parts?.time ?? null} onPick={pickTime} /> : null}
    </Popover>
  );
}
```

Create `web/src/ui/date/DateField.tsx`:

```tsx
import { useId } from "react";
import { cx } from "../cx";
import { MAX_DATE_TEXT } from "../constants";
import { controlA11y, useFieldControl } from "../Field";
import { CalendarPopover } from "./CalendarPopover";
import { friendlyDue, type IsoDay } from "./dates";
import { useDateReading, type DateReading } from "./useDateReading";
import type { QuickPick } from "./picks";

export interface DateFieldProps {
  value: string; // what the gateway reads: "", "2026-10-16", "2026-10-16 09:00", or the words typed
  onChange: (value: string) => void;
  withTime: boolean;
  picks: readonly QuickPick[];
  label?: string; // the text box's name when it is not inside a Field
  placeholder?: string;
  max?: IsoDay;
  disabled?: boolean;
}

function previewText(reading: DateReading, withTime: boolean): string {
  if (reading.kind === "reading") return "Reading…";
  if (reading.kind === "read") return friendlyDue(reading.parts, withTime);
  if (reading.kind === "error") return reading.message;
  return "";
}

// The typeable date box shared by DatePicker and DateTimePicker: the text, the calendar button, and
// a line saying how the gateway reads the text.
export function DateField({ value, onChange, withTime, picks, label, placeholder, max, disabled = false }: DateFieldProps) {
  const previewId = useId();
  const reading = useDateReading(value);
  const a11y = controlA11y(useFieldControl(), { describedBy: previewId, invalid: reading.kind === "error" });
  return (
    <div className="date-field">
      <div className="date-field__row">
        <input {...a11y} className="input date-field__input" aria-label={a11y.id ? undefined : label} value={value}
          placeholder={placeholder} maxLength={MAX_DATE_TEXT} disabled={disabled} autoComplete="off"
          onChange={(event) => onChange(event.target.value)} />
        <CalendarPopover value={value} withTime={withTime} picks={picks} max={max} disabled={disabled} onPick={onChange} />
      </div>
      <p id={previewId} className={cx("date-field__preview", `date-field__preview--${reading.kind}`)} aria-live="polite">
        {previewText(reading, withTime)}
      </p>
    </div>
  );
}
```

Create `web/src/ui/date/DatePicker.tsx`:

```tsx
import { DateField } from "./DateField";
import { FUTURE_PICKS, type QuickPick } from "./picks";
import type { IsoDay } from "./dates";

export interface DatePickerProps {
  value: string; // "", "2026-10-16", or the words typed; resolveDay turns words into a day before saving
  onChange: (value: string) => void;
  label?: string; // the text box's name when it is not inside a Field
  placeholder?: string;
  picks?: readonly QuickPick[]; // FUTURE_PICKS by default (Today, Tomorrow, Next week, No date)
  max?: IsoDay; // the last day the calendar offers (an expense: today)
  disabled?: boolean;
}

// A day you can type ("next friday", "2026-10-20") or pick (redesign P1).
export function DatePicker({ picks = FUTURE_PICKS, ...rest }: DatePickerProps) {
  return <DateField {...rest} picks={picks} withTime={false} />;
}
```

Create `web/src/ui/date/DateTimePicker.tsx`:

```tsx
import { DateField } from "./DateField";
import { FUTURE_PICKS, type QuickPick } from "./picks";

export interface DateTimePickerProps {
  value: string; // "", "2026-10-16", "2026-10-16 09:00" (Madrid wall time), or the words typed
  onChange: (value: string) => void;
  label?: string;
  placeholder?: string;
  picks?: readonly QuickPick[];
  disabled?: boolean;
}

// A day and, if you like, a time: typed ("tomorrow at 9") or picked, with time chips (redesign P1).
// What it holds goes to the gateway as it is: a task's due_date takes words or ISO, on Madrid time.
export function DateTimePicker({ picks = FUTURE_PICKS, ...rest }: DateTimePickerProps) {
  return <DateField {...rest} picks={picks} withTime />;
}
```

Create `web/src/ui/date/resolve.ts`:

```ts
import { parseDate } from "../../api/dates";
import { dueParts, type IsoDay } from "./dates";

// A date-only field's value as the day an API that takes "YYYY-MM-DD" wants: a picked day as it is,
// words read by the gateway (its sentence is the ApiError's message when it can't), "" as null.
export async function resolveDay(value: string): Promise<IsoDay | null> {
  const text = value.trim();
  if (!text) return null;
  const parts = dueParts(text);
  if (parts) return parts.day;
  const read = await parseDate(text);
  return read.due_date ? read.due_date.slice(0, 10) : null;
}
```

Create `web/src/styles/date-field.css`:

```css
/* ---------------------------------------------------------------------
   DatePicker and DateTimePicker (redesign P1): the typeable box, its
   calendar button, the reading line under it, and the popover's chips.
   The month grid's own styles are calendar.css, loaded with its chunk.
   --------------------------------------------------------------------- */

.date-field {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  min-width: 0;
}

.date-field__row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.date-field__input {
  flex: 1;
  min-width: 0;
}

.date-field__preview {
  min-height: 1.2em;
  margin: 0;
  color: var(--color-text-secondary);
  font-size: var(--fs-caption);
}

.date-field__preview--error {
  color: var(--color-danger);
}

.date-field__preview--reading {
  color: var(--color-text-faint);
}

.date-pop__row {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.date-pop__loading {
  margin: 0;
  padding: var(--space-4) 0;
  color: var(--color-text-faint);
  font-size: var(--fs-label);
  text-align: center;
}
```

Create `web/src/styles/calendar.css`:

```css
/* ---------------------------------------------------------------------
   The month grid (react-day-picker's rdp-* class names, redesign P1),
   in Roost's tokens. Imported by ui/date/Calendar.tsx only, so it loads
   with the calendar's lazy chunk.
   --------------------------------------------------------------------- */

.rdp-root {
  position: relative;
  color: var(--color-text);
  font-size: var(--fs-label);
}

.rdp-months {
  display: flex;
}

.rdp-month_caption {
  display: flex;
  align-items: center;
  height: var(--control-md);
  padding: 0 var(--space-2);
  font-size: var(--fs-body);
  font-weight: 600;
}

.rdp-nav {
  position: absolute;
  top: 0;
  right: 0;
  display: flex;
  gap: var(--space-1);
}

.rdp-button_previous,
.rdp-button_next {
  display: inline-grid;
  place-items: center;
  width: var(--control-md);
  height: var(--control-md);
  padding: 0;
  border: none;
  border-radius: var(--radius-pill);
  background: none;
  color: var(--color-text-secondary);
  cursor: pointer;
}

.rdp-button_previous:hover,
.rdp-button_next:hover {
  background: var(--color-raised);
  color: var(--color-text);
}

.rdp-chevron {
  fill: currentColor;
}

.rdp-month_grid {
  border-collapse: collapse;
}

.rdp-weekday {
  width: var(--control-md);
  height: var(--control-sm);
  color: var(--color-text-faint);
  font-size: var(--fs-caption);
  font-weight: 500;
}

.rdp-day {
  padding: 1px;
  text-align: center;
}

.rdp-day_button {
  width: var(--control-md);
  height: var(--control-md);
  border: none;
  border-radius: var(--radius-sm);
  background: none;
  color: inherit;
  font: inherit;
  cursor: pointer;
}

.rdp-day_button:hover:not(:disabled) {
  background: var(--color-raised);
}

.rdp-today .rdp-day_button {
  color: var(--color-accent-strong);
  font-weight: 700;
}

.rdp-selected .rdp-day_button {
  background: var(--color-accent);
  color: var(--color-on-accent);
}

.rdp-outside .rdp-day_button {
  color: var(--color-text-faint);
}

.rdp-disabled .rdp-day_button {
  opacity: 0.35;
  cursor: not-allowed;
}
```

`web/src/styles.css`. Find:

```css
@import "./styles/ui-overlays.css";
```

Replace with:

```css
@import "./styles/ui-overlays.css";
@import "./styles/date-field.css";
```

- [ ] **Step 7: The forms**

`web/src/components/board/taskLimits.ts`. Find:

```ts
// The gateway's limits for a task's text (roost/constants.py
// MAX_TASK_TITLE_LENGTH, MAX_DUE_TEXT_LENGTH): the inputs stop there.
export const MAX_TITLE = 200;
export const MAX_DUE_TEXT = 100;
```

Replace with:

```ts
// The gateway's limit for a task's title (roost/constants.py MAX_TASK_TITLE_LENGTH): the input stops
// there. A due's text stops at ui/constants.ts MAX_DATE_TEXT, in every date picker.
export const MAX_TITLE = 200;
```

`web/src/components/board/TaskAddForm.tsx`. Find:

```tsx
import { MAX_DUE_TEXT, MAX_TITLE } from "./taskLimits";
```

Replace with:

```tsx
import { MAX_TITLE } from "./taskLimits";
import { DateTimePicker } from "../../ui/date/DateTimePicker";
```

`web/src/components/board/TaskAddForm.tsx`. Find:

```tsx
// "When" takes words ("tomorrow at 9"): the gateway reads them on Madrid time.
```

Replace with:

```tsx
// "When" takes words ("tomorrow at 9") or a pick: the gateway reads either on Madrid time.
```

`web/src/components/board/TaskAddForm.tsx`. Find:

```tsx
      <input className="input" aria-label="When" placeholder="When? e.g. tomorrow at 9" value={when}
        maxLength={MAX_DUE_TEXT} onChange={(e) => setWhen(e.target.value)} />
```

Replace with:

```tsx
      <DateTimePicker label="When" placeholder="When? e.g. tomorrow at 9" value={when} onChange={setWhen} />
```

`web/src/components/board/TaskEditForm.tsx`. Find:

```tsx
import { MAX_DUE_TEXT, MAX_TITLE } from "./taskLimits";
import { Field } from "../../ui/Field";
import { Select, type SelectOption } from "../../ui/Select";
```

Replace with:

```tsx
import { MAX_TITLE } from "./taskLimits";
import { Field } from "../../ui/Field";
import { Select, type SelectOption } from "../../ui/Select";
import { DateTimePicker } from "../../ui/date/DateTimePicker";
import { pickerText } from "../../ui/date/dates";
```

pickerText (ui/date/dates.ts) does this now, for every picker.

`web/src/components/board/TaskEditForm.tsx`. Find:

```tsx
// A timed due reads "2026-10-14 09:00" (Madrid time, which the gateway reads back).
function dueText(due: string | null): string {
  if (!due) return "";
  return due.includes("T") ? due.slice(0, 16).replace("T", " ") : due;
}

```

Delete it.

`web/src/components/board/TaskEditForm.tsx`. Find:

```tsx
  const withDue = when === dueText(task.due_date) ? patch : { ...patch, due_date: when || null };
```

Replace with:

```tsx
  const withDue = when === pickerText(task.due_date) ? patch : { ...patch, due_date: when || null };
```

`web/src/components/board/TaskEditForm.tsx`. Find:

```tsx
    title: task.title, priority: task.priority, when: dueText(task.due_date), slice: task.allocated_budget ?? "",
```

Replace with:

```tsx
    title: task.title, priority: task.priority, when: pickerText(task.due_date), slice: task.allocated_budget ?? "",
```

`web/src/components/board/TaskEditForm.tsx`. Find:

```tsx
      <label className="field"><span className="field__label">Due</span>
        <input className="input" value={fields.when} maxLength={MAX_DUE_TEXT} placeholder="tomorrow at 9, 2026-10-20, or empty"
          onChange={(e) => set("when", e.target.value)} />
      </label>
```

Replace with:

```tsx
      <Field label="Due">
        <DateTimePicker value={fields.when} placeholder="tomorrow at 9, 2026-10-20, or empty"
          onChange={(text) => set("when", text)} />
      </Field>
```

`web/src/components/projects/ProjectEditForm.tsx`. Find:

```tsx
import { Select, type SelectOption } from "../../ui/Select";
```

Replace with:

```tsx
import { Select, type SelectOption } from "../../ui/Select";
import { DatePicker } from "../../ui/date/DatePicker";
import { resolveDay } from "../../ui/date/resolve";
```

`web/src/components/projects/ProjectEditForm.tsx`. Find:

```tsx
// What Save sends, or the sentence that says why it can't yet.
```

Replace with:

```tsx
// The two dates as days: a picked day as it is, typed words read by the gateway first.
async function withDays(fields: Fields): Promise<Fields> {
  const [start, due] = await Promise.all([resolveDay(fields.start), resolveDay(fields.due)]);
  return { ...fields, start: start ?? "", due: due ?? "" };
}

// What Save sends, or the sentence that says why it can't yet.
```

`web/src/components/projects/ProjectEditForm.tsx`. Find:

```tsx
      <label className="field"><span className="field__label">Starts</span>
        <input className="input" type="date" value={fields.start} onChange={(e) => set("start", e.target.value)} />
      </label>
      <label className="field"><span className="field__label">Due</span>
        <input className="input" type="date" value={fields.due} onChange={(e) => set("due", e.target.value)} />
      </label>
```

Replace with:

```tsx
      <Field label="Starts">
        <DatePicker value={fields.start} placeholder="a day, or empty" onChange={(day) => set("start", day)} />
      </Field>
      <Field label="Due">
        <DatePicker value={fields.due} placeholder="a day, or empty" onChange={(day) => set("due", day)} />
      </Field>
```

`web/src/components/projects/ProjectEditForm.tsx`. Find:

```tsx
  const save = async () => {
    const request = requestFor(project, fields, opened.budget);
    if (typeof request === "string") {
      setError(request);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await request();
      onDone();
    } catch (err) {
      setError(describeError(err));
      setBusy(false);
    }
  };
```

Replace with:

```tsx
  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      const request = requestFor(project, await withDays(fields), opened.budget);
      if (typeof request === "string") {
        setError(request);
        setBusy(false);
        return;
      }
      await request();
      onDone();
    } catch (err) {
      setError(describeError(err));
      setBusy(false);
    }
  };
```

`web/src/api/money.ts`. Find:

```ts
  project_id?: string;
  note?: string;
}
```

Replace with:

```ts
  project_id?: string;
  note?: string;
  spent_at?: string; // "YYYY-MM-DD", a Madrid day; none is today (the gateway refuses a future day)
}
```

`web/src/components/board/ExpenseAddForm.tsx`. Find:

```tsx
import { describeError } from "../../api/client";
```

Replace with:

```tsx
import { describeError } from "../../api/client";
import { DatePicker } from "../../ui/date/DatePicker";
import { todayIn } from "../../ui/date/dates";
import { PAST_PICKS } from "../../ui/date/picks";
import { resolveDay } from "../../ui/date/resolve";
```

`web/src/components/board/ExpenseAddForm.tsx`. Find:

```tsx
// Amount accepts the comma decimal a Spanish user types ("12,50"); anything
// ambiguous is refused here, before the gateway (which checks again).
```

Replace with:

```tsx
// Amount accepts the comma decimal a Spanish user types ("12,50"); anything
// ambiguous is refused here, before the gateway (which checks again). Day is
// today when empty; a typed day is read by the gateway before it is sent.
```

`web/src/components/board/ExpenseAddForm.tsx`. Find:

```tsx
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
```

Replace with:

```tsx
  const [note, setNote] = useState("");
  const [day, setDay] = useState("");
  const [busy, setBusy] = useState(false);
```

`web/src/components/board/ExpenseAddForm.tsx`. Find:

```tsx
    try {
      const target = fixedProjectId === undefined
        ? { project: project.trim() || undefined }
        : { project_id: fixedProjectId };
      await moneyApi.createExpense({ amount: parsed, ...target, note: note.trim() || undefined });
      setAmount("");
      setNote("");
      onAdded();
```

Replace with:

```tsx
    try {
      const spentAt = await resolveDay(day);
      const target = fixedProjectId === undefined
        ? { project: project.trim() || undefined }
        : { project_id: fixedProjectId };
      const when = spentAt ? { spent_at: spentAt } : {};
      await moneyApi.createExpense({ amount: parsed, ...target, note: note.trim() || undefined, ...when });
      setAmount("");
      setNote("");
      setDay("");
      onAdded();
```

`web/src/components/board/ExpenseAddForm.tsx`. Find:

```tsx
      {fixedProjectId === undefined ? <ProjectField value={project} projects={projects} onChange={setProject} /> : null}
```

Replace with:

```tsx
      {fixedProjectId === undefined ? <ProjectField value={project} projects={projects} onChange={setProject} /> : null}
      <DatePicker label="Day" placeholder="Today" value={day} onChange={setDay} picks={PAST_PICKS} max={todayIn()} />
```

Amount, Project, Day, Note, Add.

`web/src/styles/board.css`. Find:

```css
.expense-add {
  display: grid;
  grid-template-columns: minmax(0, 0.8fr) minmax(0, 1fr) minmax(0, 1.6fr) auto;
```

Replace with:

```css
.expense-add {
  display: grid;
  grid-template-columns: minmax(0, 0.8fr) minmax(0, 1fr) minmax(0, 1fr) minmax(0, 1.4fr) auto;
```

`web/src/styles/board.css`. Find:

```css
  .expense-add > .input:nth-of-type(3),
  .expense-add .btn {
```

Replace with:

```css
  .expense-add > .input:nth-of-type(3),
  .expense-add > .date-field,
  .expense-add .btn {
```

`web/src/styles/projects.css`. Find:

```css
/* A project's page has no Project field: Amount, Note, Add. */
.expense-add.expense-add--fixed {
  grid-template-columns: minmax(0, 0.8fr) minmax(0, 1.6fr) auto;
}
```

Replace with:

```css
/* A project's page has no Project field: Amount, Day, Note, Add. */
.expense-add.expense-add--fixed {
  grid-template-columns: minmax(0, 0.8fr) minmax(0, 1fr) minmax(0, 1.4fr) auto;
}
```

- [ ] **Step 8: The size check refuses a calendar in the entry chunk**

`web/scripts/check-bundle.mjs`. Find:

```js
const GROWTH_ALLOWED_BYTES = 150 * 1024;
```

Replace with:

```js
const GROWTH_ALLOWED_BYTES = 150 * 1024;
// Redesign P1: react-day-picker's class prefix. The calendar is a lazy chunk; it must never be in the entry.
const LAZY_ONLY_MARKERS = ["rdp-"];
```

`web/scripts/check-bundle.mjs`. Find:

```js
  return { entry, bytes: gzipSync(readFileSync(new URL(entry, dist))).length };
}

const { entry, bytes } = entryGzipBytes();
```

Replace with:

```js
  const source = readFileSync(new URL(entry, dist));
  return { entry, bytes: gzipSync(source).length, text: source.toString("utf8") };
}

const { entry, bytes, text } = entryGzipBytes();
const leaked = LAZY_ONLY_MARKERS.filter((marker) => text.includes(marker));
if (leaked.length > 0) {
  console.error(`The calendar is in the main bundle (${leaked.join(", ")}): import it through React.lazy only.`);
  process.exit(1);
}
```

- [ ] **Step 9: Run the tests to see them pass**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_dates_api.py tests/test_tasks_api.py tests/test_task_time.py -q`
Expected: PASS (`test_dates_api` has 4 tests).

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && cd web && npx vitest run tests/dates.test.ts tests/DateTimePicker.test.tsx tests/DatePicker.test.tsx tests/bundleGuard.test.ts tests/ExpenseAddForm.test.tsx tests/TasksBoard.test.tsx tests/ProjectsBoard.test.tsx tests/MoneyBoard.test.tsx tests/Project.test.tsx`
Expected: PASS: `dates` 8, `DateTimePicker` 7, `DatePicker` 4, `bundleGuard` 2, `ExpenseAddForm` 3, `TasksBoard` 17 and `ProjectsBoard` 12 tests; `MoneyBoard` and `Project` unchanged (an expense with an empty day still sends no `spent_at`).

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && cd web && npm test && npm run build && npm run size`
Expected: every test file passes; the build succeeds and lists a separate `Calendar-*.js` chunk; the size check prints the entry within the budget and no "The calendar is in the main bundle".

- [ ] **Step 10: Commit**

Run:

```bash
cd /Users/blckit/Desktop/Code_Projects/roost && \
git add roost/gateway/routes/dates.py roost/gateway/app.py tests/test_dates_api.py \
  web/src/api/dates.ts web/src/api/money.ts web/src/ui/constants.ts web/src/components/icons.tsx \
  web/src/ui/date/dates.ts web/src/ui/date/picks.ts web/src/ui/date/useDateReading.ts web/src/ui/date/resolve.ts \
  web/src/ui/date/Calendar.tsx web/src/ui/date/CalendarPopover.tsx web/src/ui/date/DateField.tsx \
  web/src/ui/date/DatePicker.tsx web/src/ui/date/DateTimePicker.tsx \
  web/src/components/board/taskLimits.ts web/src/components/board/TaskAddForm.tsx \
  web/src/components/board/TaskEditForm.tsx web/src/components/board/ExpenseAddForm.tsx \
  web/src/components/projects/ProjectEditForm.tsx web/src/styles.css web/src/styles/date-field.css \
  web/src/styles/calendar.css web/src/styles/board.css web/src/styles/projects.css web/scripts/check-bundle.mjs \
  web/tests/dates.test.ts web/tests/DateTimePicker.test.tsx web/tests/DatePicker.test.tsx \
  web/tests/bundleGuard.test.ts web/tests/ExpenseAddForm.test.tsx web/tests/TasksBoard.test.tsx \
  web/tests/ProjectsBoard.test.tsx && \
git commit -m "feat: DatePicker and DateTimePicker on Madrid time with a lazy calendar, and GET /api/dates/parse"
```

### Task 5: Robot avatars: six heads, three screen styles, every old shape still drawn, a free colour for new bots

Design V1 (Boxbot, final) and P1 "Robot avatars"; Review Focus 1. Today a bot is a bird drawn from seven body shapes (`round`, `tall`, `wide`, `egg`, `pear`, `plump`, `crest`), its status shown by poses.
- **The robot** (`web/src/components/robot/`), ported from `docs/design/robot-faces-sketch.html` (`HEADS` and `STYLES`) and rewritten as React and TypeScript:
  - `look.ts`: the head and screen names, the one bird-to-head table, the defaults, `robotHead`, `robotScreen`, `lookOf`.
  - `palette.ts`: the editor's twelve colours, the ten default colours for new bots, `nextBotColor`, `tint`, `shade`, `surpriseLook`.
  - `heads.tsx`: the six heads (Classic, Tall, Wide with two antennas and ears, Soft, Cube in 3D, Monitor on a stand), each with its screen box.
  - `moments.ts`: the five statuses and three moments (`think`, `msg`, `done`, for P2), and which status shows which.
  - `signals.tsx` with `signalGlow.tsx` (Glow icons), `signalPixel.tsx` (Pixel icons) and `signalWave.tsx` (Signals): every moment in every style, drawn around (0, 0) in the bot's colour lightened (`tint(color, 0.55)`) with a soft glow. The sketch's "?" was a font glyph; here it is a path, so no font is needed. Its fixed colours (the screen, the star, the alert bar, the new-message dot) are robot tokens.
  - `RobotFace.tsx`: the head, the dark screen, its glare, the signal in the middle, the star for the main bot.
- **Motion** runs only under `prefers-reduced-motion: no-preference`, and never on a robot marked `robot--still`, which `Avatar` sets from the same preference (`usePrefersReducedMotion`) so tests can see it.
- **`Avatar.tsx`** is rewritten on `RobotFace`, with the same props as before minus `perch` (a robot stands on nothing: every caller drops the prop, BotForm its branch, and the stylesheets their perch rules) plus `moment`.
- **Each bot picks its screen style:** the avatar JSON gains `screen` (`glow`, `pixel` or `signal`; none is `glow`, `ROBOT_SIGNAL_STYLE`). The look editor still saves at once; its Screen picker comes with the rest of the editor in Task 6.
- **The gateway:**
  - accepts the six heads and still accepts every bird shape (`AvatarShape`, `AVATAR_SHAPES`), and `screen` from an allow-list (`AvatarScreen`); it stores the shape as sent and defaults a missing screen to glow (old rows included);
  - writes `screen` everywhere an avatar goes on the wire or into a card (`avatar_dict`), and into a shared bot file (`TemplateAvatar.screen`, optional, so an older file still reads);
  - gives `suggest_bot` and `create_bot` a `screen` argument, offers only the six heads in their tool specs, and, when the model names no colour, the first default colour nobody on the team wears (`next_bot_color`); the New bot form does the same on the web (`newBotValues`).
- **The templates** wear the robots: Chief a violet Classic (glow), Life admin a teal Soft (pixel), Researcher a blue Monitor (signal).
- **Where the table lives.** The gateway never draws, so the bird-to-head table is TypeScript only; `tests/test_bot_look.py` reads `look.ts` and `palette.ts` to prove that every shape the gateway accepts has a head and that the default colours agree.

**Files:**
- Create:
  - `roost/bots/look.py`, `tests/test_bot_look.py`
  - `web/src/components/robot/{look,palette,moments}.ts`, `web/src/components/robot/{heads,signals,signalGlow,signalPixel,signalWave,RobotFace}.tsx`, `web/src/styles/robot.css`
  - `web/tests/robotLook.test.ts`, `web/tests/RobotFace.test.tsx`
- Modify:
  - `roost/constants.py`, `roost/bots/{models,store,service,templates,template_file}.py`, `roost/gateway/routes/{bots,templates}.py`, `roost/talk/{team_tools,tool_catalog}.py`
  - `tests/{test_bot_store,test_bots_api,test_create_bot,test_suggest_bot,test_template_file}.py`
  - `web/src/api/types.ts`, `web/src/components/{Avatar,AvatarPicker}.tsx` (replaced), `web/src/components/{BotForm,ShareTemplateDialog,CreatedBotCard,SuggestionCard,ChatList,MessageRow}.tsx`, `web/src/components/profile/AvatarEditor.tsx`, `web/src/pages/{Home,Room,Chat,Profile,Login,NewBot}.tsx`, `web/src/lib/team.ts`
  - `web/src/styles.css`, `web/src/styles/avatar.css` (replaced), `web/src/styles/{bot-form,profile}.css`
  - `web/tests/Avatar.test.tsx` (replaced), `web/tests/{BotForm,NewBot,AvatarEditor}.test.tsx`, `web/tests/{team,tokens}.test.ts`
- Test: the new test files and the changed ones

**Interfaces:**
- Consumes: Task 1's robot and status tokens; Task 2's `cx`; `usePrefersReducedMotion`, `StatusLabel`, `STATUS_LABELS`; `useLiveState`.
- Produces (Shared Contract "Robots"): `ROBOT_HEADS`, `LEGACY_AVATAR_SHAPES`, `AVATAR_SHAPES`, `DEFAULT_ROBOT_HEAD`, `ROBOT_SCREENS`, `DEFAULT_ROBOT_SCREEN`, `BOT_DEFAULT_COLORS` (Python); `AvatarShape` (11), `AvatarScreen`, `Avatar.screen`; `avatar_dict`, `next_bot_color`; `SuggestBotArgs.card(team_colors)`, `CreateBotArgs.draft(team_colors)`. Web: `RobotHead`, `LegacyAvatarShape`, `AvatarShape`, `RobotScreen`, `AvatarOut.screen`; everything in `robot/look.ts`, `palette.ts`, `moments.ts`, `heads.tsx`, `signals.tsx`; `RobotFace`, `RobotFaceProps`; `Avatar` (no `perch`, plus `moment`); `AvatarPicker` (Shape and Colour); `newBotValues`. Task 6 adds `picture` to `RobotFace`, `Avatar`, `Avatar.picture` and `bot_out`.

- [ ] **Step 1: Path guard**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && git -C /Users/blckit/Desktop/Code_Projects/roost rev-parse --show-toplevel && git -C /Users/blckit/Desktop/Code_Projects/roost branch --show-current`
Expected: `/Users/blckit/Desktop/Code_Projects/roost` then `night-1`. If either differs, stop.

Then confirm Task 4 has landed and this task has not:

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && test -f web/src/ui/date/DatePicker.tsx && test ! -d web/src/components/robot && test ! -f roost/bots/look.py && echo ready`
Expected: `ready`.

- [ ] **Step 2: Write the failing gateway tests**

Create `tests/test_bot_look.py`:

```python
"""Robot avatars (look & feel redesign V1, "Boxbot"): six heads, three screen styles, every old bird
shape still accepted, and a colour no teammate wears for a new bot. The gateway stores a shape as
sent; the web draws it, so the web's table must give every accepted shape a head."""

from __future__ import annotations

import re
from pathlib import Path
from typing import get_args

from fastapi.testclient import TestClient

from roost.bots.look import avatar_dict, next_bot_color
from roost.bots.models import Avatar, AvatarScreen, AvatarShape
from roost.constants import (
    AVATAR_SHAPES, BOT_DEFAULT_COLORS, LEGACY_AVATAR_SHAPES, ROBOT_HEADS, ROBOT_SCREENS,
)
from roost.gateway.app import create_app

ROOT = Path(__file__).resolve().parents[1]
WEB_LOOK = ROOT / "web" / "src" / "components" / "robot" / "look.ts"
WEB_PALETTE = ROOT / "web" / "src" / "components" / "robot" / "palette.ts"
O = {"Origin": "http://127.0.0.1:18800"}
OLD_BIRD_SHAPES = ("round", "tall", "wide", "egg", "pear", "plump", "crest")   # S1.6


def _web_list(text: str, name: str) -> list[str]:
    block = re.search(rf"{name}[^=]*=\s*\[(.*?)\];", text, re.DOTALL)
    assert block, f"{name} not found"
    return re.findall(r'"([^"]+)"', block.group(1))


def _web_table(text: str, name: str) -> dict[str, str]:
    block = re.search(rf"{name}[^=]*=\s*\{{(.*?)\}};", text, re.DOTALL)
    assert block, f"{name} not found"
    return dict(re.findall(r'(\w+):\s*"(\w+)"', block.group(1)))


def _client() -> TestClient:
    client = TestClient(create_app())
    assert client.post("/api/auth/register", json={"username": "alice", "password": "pw-123456"},
                       headers=O).status_code == 201
    return client


def test_the_shape_lists_are_one_list():
    assert get_args(AvatarShape) == AVATAR_SHAPES == ROBOT_HEADS + LEGACY_AVATAR_SHAPES
    assert get_args(AvatarScreen) == ROBOT_SCREENS
    assert set(OLD_BIRD_SHAPES) <= set(AVATAR_SHAPES)   # every S1.6 value stays valid


def test_every_shape_the_gateway_accepts_has_a_head_on_the_web():
    look = WEB_LOOK.read_text(encoding="utf-8")
    heads = _web_list(look, "ROBOT_HEADS")
    table = _web_table(look, "LEGACY_SHAPE_TO_HEAD")
    assert heads == list(ROBOT_HEADS)
    assert sorted(table) == sorted(LEGACY_AVATAR_SHAPES)
    assert set(table.values()) <= set(ROBOT_HEADS)
    assert [shape for shape in AVATAR_SHAPES if shape not in heads and shape not in table] == []
    assert _web_list(look, "ROBOT_SCREENS") == list(ROBOT_SCREENS)


def test_the_web_and_the_gateway_share_the_default_colours():
    assert _web_list(WEB_PALETTE.read_text(encoding="utf-8"), "BOT_DEFAULT_COLORS") == list(BOT_DEFAULT_COLORS)


def test_a_new_bot_takes_the_first_colour_no_teammate_wears():
    assert next_bot_color([]) == "#8b5cf6"
    assert next_bot_color(["#8B5CF6", "#22c55e"]) == "#3b82f6"
    assert next_bot_color(list(BOT_DEFAULT_COLORS)) == BOT_DEFAULT_COLORS[0]
    assert next_bot_color([*BOT_DEFAULT_COLORS, "#ffffff"]) == BOT_DEFAULT_COLORS[1]


def test_an_avatar_on_the_wire_names_its_screen():
    assert avatar_dict(Avatar("egg", "#14b8a6", "none")) == {
        "shape": "egg", "color": "#14b8a6", "badge": "none", "screen": "glow"}


def test_a_head_and_a_screen_are_stored_and_an_old_bird_shape_is_still_accepted():
    client = _client()
    made = client.post("/api/bots", headers=O, json={"name": "Scout", "job": "finds", "instructions": "",
                                                     "avatar": {"shape": "monitor", "color": "#3b82f6", "screen": "pixel"}})
    assert made.status_code == 201
    assert made.json()["avatar"] == {"shape": "monitor", "color": "#3b82f6", "badge": "none", "screen": "pixel"}
    old = client.patch(f"/api/bots/{made.json()['id']}", headers=O,
                       json={"avatar": {"shape": "egg", "color": "#14b8a6", "badge": "none"}})
    assert old.status_code == 200
    assert old.json()["avatar"] == {"shape": "egg", "color": "#14b8a6", "badge": "none", "screen": "glow"}


def test_an_unknown_shape_or_screen_is_refused():
    client = _client()
    for avatar in ({"shape": "hexagon", "color": "#3b82f6"}, {"shape": "classic", "color": "#3b82f6", "screen": "neon"}):
        body = {"name": "Scout", "job": "finds", "instructions": "", "avatar": avatar}
        assert client.post("/api/bots", headers=O, json=body).status_code == 422


def test_the_templates_wear_robot_heads_and_all_three_screens():
    client = _client()
    looks = [template["avatar"] for template in client.get("/api/templates").json()]
    assert [(look["shape"], look["screen"]) for look in looks] == [
        ("classic", "glow"), ("soft", "pixel"), ("monitor", "signal")]
```

`tests/test_bot_store.py`. Find:

```python
        "avatar": {"shape": "round", "color": "#22c55e", "badge": "none"},
        "template_id": "tmpl-1",
```

Replace with:

```python
        "avatar": {"shape": "round", "color": "#22c55e", "badge": "none", "screen": "glow"},
        "template_id": "tmpl-1",
```

`tests/test_bots_api.py`. Find:

```python
    assert body["avatar"] == VALID_AVATAR
```

Replace with:

```python
    assert body["avatar"] == {**VALID_AVATAR, "screen": "glow"}
```

`tests/test_create_bot.py`. Find:

```python
    assert seo.is_primary is False and team["HiMap Social"].avatar.shape == "round"
```

Replace with:

```python
    social = team["HiMap Social"].avatar   # no shape or colour asked for: a classic head in a colour nobody wears
    assert seo.is_primary is False and (social.shape, social.color, social.screen) == ("classic", "#8b5cf6", "glow")
```

`tests/test_create_bot.py`. Find:

```python
                                         "avatar": {"shape": "egg", "color": "#14b8a6", "badge": "none"}}
```

Replace with:

```python
                                         "avatar": {"shape": "egg", "color": "#14b8a6", "badge": "none",
                                                    "screen": "glow"}}
```

`tests/test_suggest_bot.py`. Find:

```python
        "avatar": {"shape": "wide", "color": "#3b82f6", "badge": "none"},
```

Replace with:

```python
        "avatar": {"shape": "wide", "color": "#8b5cf6", "badge": "none", "screen": "glow"},   # Chief wears green
```

`tests/test_suggest_bot.py`. Find:

```python
        "and optionally a shape (round, tall, wide, egg, pear, plump, crest) and a #RRGGBB color.",
```

Replace with:

```python
        "and optionally a shape (classic, tall, wide, soft, cube, monitor), a screen (glow, pixel, signal) "
        "and a #RRGGBB color.",
```

`tests/test_template_file.py`. Find:

```python
GOOD = {"format": "roost-bot", "version": 1, "name": "Scout", "job": "finds prices", "instructions": "Be brief.",
        "avatar": {"shape": "egg", "color": "#14b8a6"}}
```

Replace with:

```python
GOOD = {"format": "roost-bot", "version": 1, "name": "Scout", "job": "finds prices", "instructions": "Be brief.",
        "avatar": {"shape": "egg", "color": "#14b8a6", "screen": "glow"}}
```

`tests/test_template_file.py`. Find:

```python
    assert r.json() == {"name": "Scout", "job": "finds prices", "instructions": "Be brief.",
                        "avatar": {"shape": "egg", "color": "#14b8a6", "badge": "none"}}
```

Replace with:

```python
    assert r.json() == {"name": "Scout", "job": "finds prices", "instructions": "Be brief.",
                        "avatar": {"shape": "egg", "color": "#14b8a6", "badge": "none", "screen": "glow"}}
```

`tests/test_template_file.py`. Find:

```python
{**GOOD, "avatar": {"shape": "cube", "color": "#000000"}}
```

Replace with:

```python
{**GOOD, "avatar": {"shape": "hexagon", "color": "#000000"}}
```

`tests/test_template_file.py`. Find:

```python
async def test_another_users_bot_cannot_be_shared(client_and_user):
    cfg, client, user_id = client_and_user
    bob = (await register_user(cfg, "bob", "pw-123456")).id
    bobs = await make_bot(cfg, bob, "Secret")
    assert (await client.get(f"/api/bots/{bobs.id}/template")).status_code == 404
```

Replace with:

```python
async def test_another_users_bot_cannot_be_shared(client_and_user):
    cfg, client, user_id = client_and_user
    bob = (await register_user(cfg, "bob", "pw-123456")).id
    bobs = await make_bot(cfg, bob, "Secret")
    assert (await client.get(f"/api/bots/{bobs.id}/template")).status_code == 404


def test_share_carries_the_screen_and_an_older_file_reads_as_glow():
    shared = template_file_for(_bot(avatar=Avatar("monitor", "#3b82f6", "none", "pixel")))
    assert shared.avatar.model_dump() == {"shape": "monitor", "color": "#3b82f6", "screen": "pixel"}
    older = {**GOOD, "avatar": {"shape": "egg", "color": "#14b8a6"}}
    assert read_template_file(older).avatar.screen == "glow"
```

- [ ] **Step 3: Write the failing web tests**

Create `web/tests/robotLook.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import {
  AVATAR_SHAPES, LEGACY_SHAPE_TO_HEAD, ROBOT_HEADS, ROBOT_SIGNAL_STYLE, lookOf, robotHead, robotScreen,
} from "../src/components/robot/look";
import { BOT_DEFAULT_COLORS, ROBOT_COLORS, nextBotColor, shade, surpriseLook, tint } from "../src/components/robot/palette";

describe("the robot look", () => {
  it("draws a head as itself and every old bird shape as a head", () => {
    for (const head of ROBOT_HEADS) expect(robotHead(head)).toBe(head);
    expect(robotHead("round")).toBe("soft");
    expect(robotHead("crest")).toBe("classic");
    expect(robotHead("tall")).toBe("tall"); // an old bird name that is also a head
    for (const shape of AVATAR_SHAPES) expect(ROBOT_HEADS).toContain(robotHead(shape));
    expect(Object.keys(LEGACY_SHAPE_TO_HEAD).sort()).toEqual(["crest", "egg", "pear", "plump", "round"]);
  });

  it("a shape it has never heard of (a newer server) draws the classic head, not a blank", () => {
    expect(robotHead("hexagon")).toBe("classic");
  });

  it("a missing or unknown screen is the default style", () => {
    expect(robotScreen(undefined)).toBe(ROBOT_SIGNAL_STYLE);
    expect(robotScreen("neon")).toBe(ROBOT_SIGNAL_STYLE);
    expect(robotScreen("pixel")).toBe("pixel");
  });

  it("a look to save never carries the picture or an old badge", () => {
    expect(lookOf({ shape: "soft", color: "#14b8a6", badge: "tasks" })).toEqual(
      { shape: "soft", color: "#14b8a6", badge: "none", screen: "glow" });
  });
});

describe("the robot palette", () => {
  it("a new bot takes the first colour nobody wears, in any case", () => {
    expect(nextBotColor([])).toBe("#8b5cf6");
    expect(nextBotColor(["#8B5CF6", "#22c55e"])).toBe("#3b82f6");
  });

  it("once every default colour is worn, they come round again", () => {
    expect(nextBotColor([...BOT_DEFAULT_COLORS])).toBe(BOT_DEFAULT_COLORS[0]);
    expect(nextBotColor([...BOT_DEFAULT_COLORS, "#ffffff"])).toBe(BOT_DEFAULT_COLORS[1]);
  });

  it("tints toward white and shades toward black", () => {
    expect(tint("#000000", 0.5)).toBe("rgb(128, 128, 128)");
    expect(tint("#3b82f6", 0)).toBe("rgb(59, 130, 246)");
    expect(shade("#ffffff", 0.7)).toBe("rgb(179, 179, 179)");
  });

  it("Surprise me always changes the head and the colour", () => {
    const now = { head: "classic" as const, color: ROBOT_COLORS[0][0], screen: "glow" as const };
    for (const roll of [0, 0.3, 0.99]) {
      const next = surpriseLook(now, () => roll);
      expect(next.head).not.toBe(now.head);
      expect(next.color).not.toBe(now.color);
      expect(ROBOT_COLORS.map(([color]) => color)).toContain(next.color);
    }
  });
});
```

Create `web/tests/RobotFace.test.tsx`:

```tsx
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { RobotFace } from "../src/components/robot/RobotFace";
import { RobotSignal } from "../src/components/robot/signals";
import { ROBOT_HEADS, ROBOT_SCREENS, ROBOT_SIGNAL_STYLE } from "../src/components/robot/look";
import { ROBOT_MOMENTS } from "../src/components/robot/moments";

afterEach(() => cleanup());

describe("RobotFace", () => {
  it("draws every head with every moment in every screen style", () => {
    for (const style of ROBOT_SCREENS) {
      for (const head of ROBOT_HEADS) {
        for (const moment of ROBOT_MOMENTS) {
          const { container, unmount } = render(<RobotFace head={head} color="#3b82f6" screen={style} moment={moment} />);
          const svg = container.querySelector("svg.robot");
          expect(svg?.getAttribute("data-head"), `${style} ${head} ${moment}`).toBe(head);
          expect(svg?.querySelector(".robot__head")?.childElementCount).toBeGreaterThan(0);
          expect(svg?.querySelector(".robot__screen")).not.toBeNull();
          const signal = svg?.querySelector(`.robot__signal--${style}[data-moment="${moment}"]`);
          expect(signal?.querySelector("path, circle, rect"), `${style} ${head} ${moment}`).not.toBeNull();
          unmount();
        }
      }
    }
  });

  it("each screen style shows the eight moments eight different ways", () => {
    for (const style of ROBOT_SCREENS) {
      const drawings = ROBOT_MOMENTS.map((moment) => {
        const { container, unmount } = render(<svg><RobotSignal style={style} moment={moment} color="rgb(1, 2, 3)" /></svg>);
        const markup = container.querySelector(".robot__signal")?.innerHTML ?? "";
        unmount();
        return markup;
      });
      expect(new Set(drawings).size, style).toBe(ROBOT_MOMENTS.length);
    }
  });

  it("draws the signal in the bot's colour, lightened, and glows with it", () => {
    const { container } = render(<RobotFace head="classic" color="#000000" moment="done" />);
    const glow = container.querySelector(".robot__signal")?.parentElement;
    expect(glow?.getAttribute("style")).toContain("drop-shadow(0 0 3px rgb(140, 140, 140))");
    expect(container.querySelector(".robot__signal path")?.getAttribute("stroke")).toBe("rgb(140, 140, 140)");
  });

  it("shows the default screen style when none is given", () => {
    const { container } = render(<RobotFace head="soft" color="#14b8a6" />);
    expect(container.querySelector("svg")?.getAttribute("data-screen")).toBe(ROBOT_SIGNAL_STYLE);
    expect(container.querySelector("svg")?.getAttribute("data-moment")).toBe("rest");
  });

  it("wears the star only when asked", () => {
    const { container, rerender } = render(<RobotFace head="classic" color="#8b5cf6" />);
    expect(container.querySelector(".robot__star")).toBeNull();
    rerender(<RobotFace head="classic" color="#8b5cf6" star />);
    expect(container.querySelector(".robot__star")).not.toBeNull();
  });

  it("is still when asked: no animation runs", () => {
    const { container } = render(<RobotFace head="wide" color="#8b5cf6" moment="onit" still />);
    expect(container.querySelector("svg")).toHaveClass("robot", "robot--still");
  });

  it("is an image with a name when titled, and hidden when not", () => {
    const { rerender } = render(<RobotFace head="cube" color="#8b5cf6" title="On it" />);
    expect(screen.getByRole("img", { name: "On it" })).toBeInTheDocument();
    rerender(<RobotFace head="cube" color="#8b5cf6" />);
    expect(screen.queryByRole("img")).toBeNull();
  });
});
```

Replace the whole of `web/tests/Avatar.test.tsx` with: (the robot replaces the bird)

```tsx
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { Avatar } from "../src/components/Avatar";
import { StatusLabel } from "../src/components/StatusLabel";
import { AVATAR_SHAPES, ROBOT_HEADS } from "../src/components/robot/look";
import type { AvatarOut, BotStatus } from "../src/api/types";

afterEach(() => cleanup());

const AVATAR: AvatarOut = { shape: "classic", color: "#8b5cf6", badge: "none", screen: "pixel" };

const STATUSES: Array<[BotStatus, string, string]> = [
  ["resting", "Resting", "rest"],
  ["on_it", "On it", "onit"],
  ["asking_you", "Asking you", "ask"],
  ["stuck", "Stuck", "stuck"],
  ["off_duty", "Off duty", "off"],
];

function mockReducedMotion(reduce: boolean) {
  window.matchMedia = ((query: string) => ({
    matches: reduce && query.includes("prefers-reduced-motion"),
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
  })) as unknown as typeof window.matchMedia;
}

describe("Avatar", () => {
  it.each(STATUSES)("shows %s on its screen and in words", (status, label, moment) => {
    render(<Avatar avatar={AVATAR} status={status} />);
    const svg = document.querySelector("svg.avatar");
    expect(svg).toHaveClass(`avatar--${status}`);
    expect(svg?.getAttribute("data-moment")).toBe(moment);
    expect(svg?.getAttribute("data-screen")).toBe("pixel");
    expect(screen.getByText(label)).toBeInTheDocument();
  });

  it("draws every stored shape, old bird shapes included, as one of the six heads", () => {
    for (const shape of AVATAR_SHAPES) {
      const { container, unmount } = render(<Avatar avatar={{ ...AVATAR, shape }} status="resting" />);
      const head = container.querySelector("svg.avatar")?.getAttribute("data-head");
      expect(ROBOT_HEADS, shape).toContain(head);
      expect(container.querySelector(".robot__head")?.childElementCount, shape).toBeGreaterThan(0);
      unmount();
    }
    const { container } = render(<Avatar avatar={{ ...AVATAR, shape: "egg" }} status="resting" />);
    expect(container.querySelector("svg.avatar")?.getAttribute("data-head")).toBe("soft");
  });

  it("an avatar from before the robots, with no screen, shows the glow style", () => {
    render(<Avatar avatar={{ shape: "round", color: "#10b981", badge: "none" }} status="resting" />);
    expect(document.querySelector("svg.avatar")?.getAttribute("data-screen")).toBe("glow");
  });

  it("shows a moment in place of its status when asked", () => {
    render(<Avatar avatar={AVATAR} status="on_it" moment="think" />);
    expect(document.querySelector("svg.avatar")?.getAttribute("data-moment")).toBe("think");
  });

  it("renders the live activity line when present", () => {
    render(<Avatar avatar={AVATAR} status="on_it" activity="opening a page" />);
    expect(screen.getByText("opening a page")).toBeInTheDocument();
  });

  it("moves when the OS has no preference, and is still when it asks for reduced motion", () => {
    mockReducedMotion(false);
    const { unmount } = render(<Avatar avatar={AVATAR} status="on_it" />);
    expect(document.querySelector("svg.avatar")).not.toHaveClass("avatar--reduced-motion");
    expect(document.querySelector("svg.avatar")).not.toHaveClass("robot--still");
    unmount();
    mockReducedMotion(true);
    render(<Avatar avatar={AVATAR} status="on_it" />);
    expect(document.querySelector("svg.avatar")).toHaveClass("avatar--reduced-motion", "robot--still");
    mockReducedMotion(false);
  });

  it("leaves out the words when label={false} but keeps the status as the image's name", () => {
    render(<Avatar avatar={AVATAR} status="stuck" label={false} />);
    expect(screen.queryByText("Stuck")).toBeNull();
    expect(screen.getByRole("img", { name: "Stuck" })).toBeInTheDocument();
  });

  it("only the main bot wears the star", () => {
    const { container, rerender } = render(<Avatar avatar={AVATAR} status="resting" />);
    expect(container.querySelector(".robot__star")).toBeNull();
    rerender(<Avatar avatar={AVATAR} status="resting" star />);
    expect(container.querySelector(".robot__star")).not.toBeNull();
  });

  it("is hidden from assistive tech when decorative", () => {
    render(<Avatar avatar={AVATAR} status="resting" label={false} decorative />);
    expect(document.querySelector("svg.avatar")?.getAttribute("aria-hidden")).toBe("true");
    expect(screen.queryByRole("img")).toBeNull();
  });
});

describe("StatusLabel", () => {
  it.each(STATUSES)("tags the %s label with its status so the dot can take the status color", (status, label) => {
    render(<StatusLabel status={status} />);
    const wrapper = screen.getByText(label).closest(".status-label");
    expect(wrapper).toHaveClass(`status-label--${status}`);
    expect(wrapper?.querySelector(".status-label__dot")).not.toBeNull();
  });
});
```

`web/tests/BotForm.test.tsx`. Find:

```tsx
import { BotForm } from "../src/components/BotForm";
```

Replace with:

```tsx
import { BotForm, newBotValues } from "../src/components/BotForm";
```

`web/tests/BotForm.test.tsx`. Find:

```tsx
    expect(screen.getAllByRole("radio", { name: /Round|Tall|Wide|Egg|Pear|Plump|Crest/ })).toHaveLength(7);
```

Replace with:

```tsx
    expect(screen.getAllByRole("radio", { name: /^(Classic|Tall|Wide|Soft|Cube|Monitor)$/ })).toHaveLength(6);
```

`web/tests/BotForm.test.tsx`. Find:

```tsx
  it("updates the live preview when a shape is chosen", async () => {
    const user = userEvent.setup();
    render(<BotForm submitLabel="Create bot" onSubmit={vi.fn()} />);
    await user.click(screen.getByRole("radio", { name: "Tall" }));
    expect(screen.getByRole("radio", { name: "Tall" })).toBeChecked();
    expect(screen.getByRole("radio", { name: "Round" })).not.toBeChecked();
    const body = document.querySelector(".bot-form__preview .avatar__body");
    expect(body?.getAttribute("ry")).toBe("34");
  });
```

Replace with:

```tsx
  it("updates the live preview when a head is chosen", async () => {
    const user = userEvent.setup();
    render(<BotForm submitLabel="Create bot" onSubmit={vi.fn()} />);
    expect(screen.getByRole("radio", { name: "Classic" })).toBeChecked();
    await user.click(screen.getByRole("radio", { name: "Monitor" }));
    expect(screen.getByRole("radio", { name: "Monitor" })).toBeChecked();
    expect(screen.getByRole("radio", { name: "Classic" })).not.toBeChecked();
    expect(document.querySelector(".bot-form__preview svg.avatar")?.getAttribute("data-head")).toBe("monitor");
  });

  it("a new bot wears the first colour no teammate wears", () => {
    expect(newBotValues([]).avatar).toEqual({ shape: "classic", color: "#8b5cf6", badge: "none", screen: "glow" });
    expect(newBotValues(["#8b5cf6", "#3b82f6"]).avatar.color).toBe("#14b8a6");
  });
```

`web/tests/BotForm.test.tsx`. Find:

```tsx
      avatar: { shape: "wide", color: "#f97316", badge: "none" },
      template_id: null,
    });
```

Replace with:

```tsx
      avatar: { shape: "wide", color: "#f97316", badge: "none", screen: "glow" },
      template_id: null,
    });
```

`web/tests/NewBot.test.tsx`. Find:

```tsx
vi.mock("../src/hooks/useTemplates", () => ({
```

Replace with:

```tsx
// Chief wears violet and Scout blue, so a new bot starts in teal.
vi.mock("../src/hooks/useLiveStore", () => ({ useLiveState: () => ({ bots: {
  c: makeBot({ id: "c", name: "Chief", avatar: { shape: "classic", color: "#8b5cf6", badge: "none", screen: "glow" } }),
  s: makeBot({ id: "s", name: "Scout", avatar: { shape: "round", color: "#3B82F6", badge: "none" } }),
} }) }));
vi.mock("../src/hooks/useTemplates", () => ({
```

`web/tests/NewBot.test.tsx`. Find:

```tsx
describe("NewBot", () => {
```

Replace with:

```tsx
describe("NewBot", () => {
  it("starts a new bot in a colour no teammate wears", async () => {
    renderPage();
    await userEvent.type(screen.getByLabelText("Name"), "Quill");
    await userEvent.type(screen.getByLabelText("Job"), "Drafts notes");
    await userEvent.click(screen.getByRole("button", { name: "Create bot" }));
    expect(createBotMock).toHaveBeenCalledWith(expect.objectContaining({
      avatar: { shape: "classic", color: "#14b8a6", badge: "none", screen: "glow" },
    }));
  });
```

`web/tests/AvatarEditor.test.tsx`. Find:

```tsx
  it("offers seven shapes and twelve colours, including white and grey", () => {
    render(<AvatarEditor bot={makeBot()} onChange={vi.fn()} />);
    expect(screen.getAllByRole("radio", { name: /Round|Tall|Wide|Egg|Pear|Plump|Crest/ })).toHaveLength(7);
```

Replace with:

```tsx
  it("offers six heads and twelve colours, including white and grey", () => {
    render(<AvatarEditor bot={makeBot()} onChange={vi.fn()} />);
    expect(screen.getAllByRole("radio", { name: /^(Classic|Tall|Wide|Soft|Cube|Monitor)$/ })).toHaveLength(6);
```

`web/tests/AvatarEditor.test.tsx`. Find:

```tsx
  it("saves a new shape at once, with no badge", async () => {
    const onChange = vi.fn();
    const saved = makeBot({ avatar: { shape: "egg", color: "#10b981", badge: "none" } });
    updateBotMock.mockResolvedValue(saved);
    render(<AvatarEditor bot={makeBot()} onChange={onChange} />);
    await userEvent.click(screen.getByRole("radio", { name: "Egg" }));
    expect(updateBotMock).toHaveBeenCalledWith("bot-1", { avatar: { shape: "egg", color: "#10b981", badge: "none" } });
```

Replace with:

```tsx
  it("an old bird shape shows as its head, and a new head saves at once, with no badge", async () => {
    const onChange = vi.fn();
    const saved = makeBot({ avatar: { shape: "cube", color: "#10b981", badge: "none", screen: "glow" } });
    updateBotMock.mockResolvedValue(saved);
    render(<AvatarEditor bot={makeBot()} onChange={onChange} />); // makeBot wears the old "round"
    expect(screen.getByRole("radio", { name: "Soft" })).toBeChecked();
    await userEvent.click(screen.getByRole("radio", { name: "Cube" }));
    expect(updateBotMock).toHaveBeenCalledWith("bot-1", { avatar: { shape: "cube", color: "#10b981", badge: "none", screen: "glow" } });
```

`web/tests/AvatarEditor.test.tsx`. Find:

```tsx
    expect(updateBotMock).toHaveBeenCalledWith("bot-1", { avatar: { shape: "tall", color: "#eab308", badge: "none" } });
```

Replace with:

```tsx
    expect(updateBotMock).toHaveBeenCalledWith("bot-1", { avatar: { shape: "tall", color: "#eab308", badge: "none", screen: "glow" } });
```

`web/tests/team.test.ts`. Find:

```ts
  it("reads a suggestion card body and rejects anything else", () => {
    const card = { name: "Ledger", job: "Keeps the books", avatar: { shape: "wide", color: "#3b82f6", badge: "finance" } };
```

Replace with:

```ts
  it("reads a suggestion card body and rejects anything else", () => {
    const card = { name: "Ledger", job: "Keeps the books", avatar: { shape: "wide", color: "#3b82f6", badge: "finance", screen: "pixel" } };
```

`web/tests/team.test.ts`. Find:

```ts
  it("ignores a card's roles: every bot has every tool now", () => {
    const card = { name: "Life admin", job: "Tasks and money", avatar: { shape: "crest", color: "#3b82f6", badge: "none" } };
```

Replace with:

```ts
  it("ignores a card's roles: every bot has every tool now", () => {
    const card = { name: "Life admin", job: "Tasks and money", avatar: { shape: "crest", color: "#3b82f6", badge: "none", screen: "glow" } };
```

`web/tests/team.test.ts`. Find:

```ts
  it("reads a Created card and refuses a broken one", () => {
    const card = { bot_id: "b", name: "HiMap SEO", job: "SEO", instructions: "", avatar: { shape: "egg", color: "#14b8a6", badge: "none" } };
```

Replace with:

```ts
  it("a card from before the robots shows the glow screen, and an unknown screen is refused", () => {
    const card = { name: "Ledger", job: "Keeps the books", avatar: { shape: "classic", color: "#3b82f6", badge: "none" } };
    expect(parseSuggestion(JSON.stringify(card))?.avatar.screen).toBe("glow");
    expect(parseSuggestion(JSON.stringify({ ...card, avatar: { ...card.avatar, screen: "neon" } }))).toBeNull();
    expect(parseSuggestion(JSON.stringify({ ...card, avatar: { ...card.avatar, shape: "hexagon" } }))).toBeNull();
  });

  it("reads a Created card and refuses a broken one", () => {
    const card = { bot_id: "b", name: "HiMap SEO", job: "SEO", instructions: "", avatar: { shape: "egg", color: "#14b8a6", badge: "none", screen: "signal" } };
```

`web/tests/tokens.test.ts`. Find:

```ts
// Colour data, not styling: the swatches a user picks from. Nothing else in web/src may hold a colour.
const COLOUR_DATA_FILES = ["components/projects/projects.ts"];
// Drawn with hard-coded colours until Task 5 replaces the bird with the robot. Task 5 empties this list.
const PENDING_ROBOT = [
  "components/Avatar.tsx", "components/AvatarPicker.tsx", "components/BotForm.tsx",
  "components/profile/AvatarEditor.tsx", "pages/Login.tsx",
];
```

Replace with:

```ts
// Colour data, not styling: the swatches a user picks from. Nothing else in web/src may hold a colour.
const COLOUR_DATA_FILES = ["components/projects/projects.ts", "components/robot/palette.ts"];
```

`web/tests/tokens.test.ts`. Find:

```ts
    const allowed = new Set([...COLOUR_DATA_FILES, ...PENDING_ROBOT]);
```

Replace with:

```ts
    const allowed = new Set(COLOUR_DATA_FILES);
```

- [ ] **Step 4: Run them to see them fail**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_bot_look.py tests/test_bot_store.py tests/test_bots_api.py tests/test_create_bot.py tests/test_suggest_bot.py tests/test_template_file.py -q`
Expected: ERROR at collection: `ModuleNotFoundError: No module named 'roost.bots.look'`.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && cd web && npx vitest run tests/robotLook.test.ts tests/RobotFace.test.tsx tests/Avatar.test.tsx tests/BotForm.test.tsx tests/NewBot.test.tsx tests/AvatarEditor.test.tsx tests/team.test.ts tests/tokens.test.ts`
Expected: FAIL, 8 files:
- `robotLook`, `RobotFace`, `Avatar`: `Failed to resolve import "../src/components/robot/…"`.
- `BotForm`: 4 failed (`newBotValues is not a function`; no "Classic" radio; 2 radios matched where 6 were wanted).
- `AvatarEditor`: 3 failed; `NewBot`: `starts a new bot in a colour no teammate wears`.
- `team`: 4 failed (no `screen` on a parsed card).
- `tokens`: `keeps colour literals and font sizes out of components` (29 findings: the bird's colours, now that its files are no longer allowed).

- [ ] **Step 5: The gateway: heads, screens and a free colour**

In `roost/constants.py`'s **Bots** section, `roost/bots/`, the bots and templates routes and the team tools:

`roost/constants.py`. Find:

```python
from decimal import Decimal
from pathlib import Path
```

Replace with:

```python
from decimal import Decimal
from pathlib import Path
from typing import Final
```

`roost/constants.py`. Find:

```python
AVATAR_COLOR_PATTERN = r"^#[0-9a-fA-F]{6}$"
DEFAULT_SUGGESTED_COLOR = "#3b82f6"
MAX_SUGGESTIONS_PER_RUN = 3
```

Replace with:

```python
AVATAR_COLOR_PATTERN = r"^#[0-9a-fA-F]{6}$"
MAX_SUGGESTIONS_PER_RUN = 3
```

`roost/constants.py`. Find:

```python
# Our own bird body shapes (S1.6). Old values stay valid; new ones are additive.
AVATAR_SHAPES: tuple[str, ...] = ("round", "tall", "wide", "egg", "pear", "plump", "crest")
```

Replace with:

```python
# Robot avatars (look & feel redesign V1, "Boxbot"): six heads. The S1.6 bird shapes that are not
# head names stay valid and are stored as sent; the web draws each one as a head
# (web/src/components/robot/look.ts LEGACY_SHAPE_TO_HEAD; tests/test_bot_look.py keeps the two in step).
ROBOT_HEADS: tuple[str, ...] = ("classic", "tall", "wide", "soft", "cube", "monitor")
LEGACY_AVATAR_SHAPES: tuple[str, ...] = ("round", "egg", "pear", "plump", "crest")
AVATAR_SHAPES: tuple[str, ...] = ROBOT_HEADS + LEGACY_AVATAR_SHAPES
DEFAULT_ROBOT_HEAD: Final = "classic"
# The screen's signal style; an avatar stored before the robots has none and shows the default.
ROBOT_SCREENS: tuple[str, ...] = ("glow", "pixel", "signal")
DEFAULT_ROBOT_SCREEN: Final = "glow"
# A new bot with no colour chosen takes the first of these no teammate wears
# (web/src/components/robot/palette.ts BOT_DEFAULT_COLORS is the same list).
BOT_DEFAULT_COLORS: tuple[str, ...] = (
    "#8b5cf6", "#3b82f6", "#14b8a6", "#22c55e", "#f97316", "#ec4899", "#ef4444", "#eab308", "#6366f1", "#84cc16",
)
```

`roost/bots/models.py`. Find:

```python
AvatarShape = Literal["round", "tall", "wide", "egg", "pear", "plump", "crest"]
AvatarBadge = Literal["none", "tasks", "finance", "notes", "docs", "inbox"]
```

Replace with:

```python
# The six robot heads, then the S1.6 bird shapes still accepted (roost/constants.py AVATAR_SHAPES).
AvatarShape = Literal["classic", "tall", "wide", "soft", "cube", "monitor", "round", "egg", "pear", "plump", "crest"]
AvatarScreen = Literal["glow", "pixel", "signal"]
AvatarBadge = Literal["none", "tasks", "finance", "notes", "docs", "inbox"]
```

`roost/bots/models.py`. Find:

```python
@dataclass(frozen=True)
class Avatar:
    shape: AvatarShape
    color: str  # "#RRGGBB"
    badge: AvatarBadge
```

Replace with:

```python
@dataclass(frozen=True)
class Avatar:
    shape: AvatarShape
    color: str  # "#RRGGBB"
    badge: AvatarBadge
    screen: AvatarScreen = "glow"  # the robot screen's signal style (redesign V1)
```

Create `roost/bots/look.py`:

```python
"""How a bot looks (look & feel redesign V1, "Boxbot"): the avatar as the wire and the cards carry
it, and the colour a new bot takes when nobody chose one. The gateway stores a shape as sent, an
old bird shape included; only the web draws, so the bird-to-head table lives there
(web/src/components/robot/look.ts)."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from roost.bots.models import Avatar
from roost.constants import BOT_DEFAULT_COLORS


def avatar_dict(avatar: Avatar) -> dict[str, Any]:
    """An avatar on the wire and in a card: its shape, colour, badge and screen."""
    return {"shape": avatar.shape, "color": avatar.color, "badge": avatar.badge, "screen": avatar.screen}


def next_bot_color(used: Iterable[str]) -> str:
    """The first default colour no teammate wears (any case). Once all are worn they come round again."""
    worn = [color.lower() for color in used]
    free = next((color for color in BOT_DEFAULT_COLORS if color not in worn), None)
    return free if free is not None else BOT_DEFAULT_COLORS[len(worn) % len(BOT_DEFAULT_COLORS)]
```

`roost/bots/store.py`. Find:

```python
from roost.config import Config
from roost.crypto.encryption import decrypt_field, encrypt, user_aad
```

Replace with:

```python
from roost.config import Config
from roost.constants import DEFAULT_ROBOT_SCREEN
from roost.crypto.encryption import decrypt_field, encrypt, user_aad
```

`roost/bots/store.py`. Find:

```python
def _avatar_dump(avatar: Avatar) -> str:
    return json.dumps({"shape": avatar.shape, "color": avatar.color, "badge": avatar.badge})


def _avatar_load(raw: str) -> Avatar:
    data = json.loads(raw)
    return Avatar(shape=data["shape"], color=data["color"], badge=data["badge"])
```

Replace with:

```python
def _avatar_dump(avatar: Avatar) -> str:
    return json.dumps({"shape": avatar.shape, "color": avatar.color, "badge": avatar.badge, "screen": avatar.screen})


def _avatar_load(raw: str) -> Avatar:
    """An avatar stored before the robots has no screen: it shows the default style."""
    data = json.loads(raw)
    return Avatar(shape=data["shape"], color=data["color"], badge=data["badge"],
                  screen=data.get("screen", DEFAULT_ROBOT_SCREEN))
```

`roost/bots/service.py`. Find:

```python
from roost.bots.models import Bot
```

Replace with:

```python
from roost.bots.look import avatar_dict
from roost.bots.models import Bot
```

`roost/bots/service.py`. Find:

```python
        "avatar": {
            "shape": bot.avatar.shape,
            "color": bot.avatar.color,
            "badge": bot.avatar.badge,
        },
```

Replace with:

```python
        "avatar": avatar_dict(bot.avatar),
```

`roost/gateway/routes/bots.py`. Find:

```python
from roost.bots.models import Avatar, AvatarBadge, AvatarShape, BotDraft, BotPatch, DuplicateBotName
```

Replace with:

```python
from roost.bots.models import Avatar, AvatarBadge, AvatarScreen, AvatarShape, BotDraft, BotPatch, DuplicateBotName
```

`roost/gateway/routes/bots.py`. Find:

```python
class AvatarIn(BaseModel):
    shape: AvatarShape
    color: str = Field(pattern=_COLOR_PATTERN)
    badge: AvatarBadge = "none"   # old clients send one; S1 writes "none" (badges are not drawn any more)

    def to_avatar(self) -> Avatar:
        return Avatar(shape=self.shape, color=self.color, badge=self.badge)
```

Replace with:

```python
class AvatarIn(BaseModel):
    shape: AvatarShape            # a robot head, or an old bird shape (still accepted, drawn as a head)
    color: str = Field(pattern=_COLOR_PATTERN)
    badge: AvatarBadge = "none"   # old clients send one; S1 writes "none" (badges are not drawn any more)
    screen: AvatarScreen = "glow"  # the robot screen's signal style; a client that sends none gets glow

    def to_avatar(self) -> Avatar:
        return Avatar(shape=self.shape, color=self.color, badge=self.badge, screen=self.screen)
```

`roost/talk/team_tools.py`. Find:

```python
import json
from collections.abc import Awaitable, Callable
```

Replace with:

```python
import json
from collections.abc import Awaitable, Callable, Iterable
```

`roost/talk/team_tools.py`. Find:

```python
from roost.bots.models import Avatar, AvatarShape, Bot, BotDraft, DuplicateBotName
```

Replace with:

```python
from roost.bots.look import avatar_dict, next_bot_color
from roost.bots.models import Avatar, AvatarScreen, AvatarShape, Bot, BotDraft, DuplicateBotName
```

`roost/talk/team_tools.py`. Find:

```python
    AVATAR_COLOR_PATTERN, AVATAR_SHAPES, BOT_NAME_PATTERN, DEFAULT_SUGGESTED_COLOR, HANDOFF_PREVIEW_CHARS,
```

Replace with:

```python
    AVATAR_COLOR_PATTERN, BOT_NAME_PATTERN, DEFAULT_ROBOT_HEAD, DEFAULT_ROBOT_SCREEN, HANDOFF_PREVIEW_CHARS,
```

`roost/talk/team_tools.py`. Find:

```python
    MAX_HANDOFF_DEPTH, MAX_HANDOFF_TASK_LENGTH, MAX_HANDOFFS_PER_RUN, MAX_SUGGESTIONS_PER_RUN,
)
```

Replace with:

```python
    MAX_HANDOFF_DEPTH, MAX_HANDOFF_TASK_LENGTH, MAX_HANDOFFS_PER_RUN, MAX_SUGGESTIONS_PER_RUN,
    ROBOT_HEADS, ROBOT_SCREENS,
)
```

`roost/talk/team_tools.py`. Find:

```python
    "Refused: suggest_bot needs a name (letters, numbers, spaces, . or -, up to 40), a one-line job, "
    f"and optionally a shape ({', '.join(AVATAR_SHAPES)}) and a #RRGGBB color."
```

Replace with:

```python
    "Refused: suggest_bot needs a name (letters, numbers, spaces, . or -, up to 40), a one-line job, "
    f"and optionally a shape ({', '.join(ROBOT_HEADS)}), a screen ({', '.join(ROBOT_SCREENS)}) and a #RRGGBB color."
```

`roost/talk/team_tools.py`. Find:

```python
    "(up to 200), instructions of at most 4000 characters, and optionally a shape and a #RRGGBB color."
```

Replace with:

```python
    "(up to 200), instructions of at most 4000 characters, and optionally a shape, a screen and a #RRGGBB color."
```

`roost/talk/team_tools.py`. Find:

```python
class SuggestBotArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str = Field(min_length=1, max_length=MAX_BOT_NAME_LENGTH, pattern=BOT_NAME_PATTERN)
    job: str = Field(min_length=1, max_length=MAX_BOT_JOB_LENGTH)
    shape: AvatarShape = "round"
    color: str = Field(default=DEFAULT_SUGGESTED_COLOR, pattern=AVATAR_COLOR_PATTERN)
```

Replace with:

```python
class SuggestBotArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str = Field(min_length=1, max_length=MAX_BOT_NAME_LENGTH, pattern=BOT_NAME_PATTERN)
    job: str = Field(min_length=1, max_length=MAX_BOT_JOB_LENGTH)
    shape: AvatarShape = DEFAULT_ROBOT_HEAD
    color: str | None = Field(default=None, pattern=AVATAR_COLOR_PATTERN)   # none: a colour no teammate wears
    screen: AvatarScreen = DEFAULT_ROBOT_SCREEN
```

`roost/talk/team_tools.py`. Find:

```python
    def card(self) -> dict[str, Any]:
        return {"name": self.name, "job": self.job,
                "avatar": {"shape": self.shape, "color": self.color, "badge": "none"}}
```

Replace with:

```python
    def card(self, team_colors: Iterable[str]) -> dict[str, Any]:
        avatar = Avatar(shape=self.shape, color=self.color or next_bot_color(team_colors), badge="none",
                        screen=self.screen)
        return {"name": self.name, "job": self.job, "avatar": avatar_dict(avatar)}
```

`roost/talk/team_tools.py`. Find:

```python
    instructions: str = Field(default="", max_length=MAX_BOT_INSTRUCTIONS_LENGTH)
    shape: AvatarShape = "round"
    color: str = Field(default=DEFAULT_SUGGESTED_COLOR, pattern=AVATAR_COLOR_PATTERN)
```

Replace with:

```python
    instructions: str = Field(default="", max_length=MAX_BOT_INSTRUCTIONS_LENGTH)
    shape: AvatarShape = DEFAULT_ROBOT_HEAD
    color: str | None = Field(default=None, pattern=AVATAR_COLOR_PATTERN)   # none: a colour no teammate wears
    screen: AvatarScreen = DEFAULT_ROBOT_SCREEN
```

`roost/talk/team_tools.py`. Find:

```python
    def draft(self) -> BotDraft:
        return BotDraft(name=self.name, job=self.job, instructions=self.instructions,
                        avatar=Avatar(shape=self.shape, color=self.color, badge="none"))
```

Replace with:

```python
    def draft(self, team_colors: Iterable[str]) -> BotDraft:
        avatar = Avatar(shape=self.shape, color=self.color or next_bot_color(team_colors), badge="none",
                        screen=self.screen)
        return BotDraft(name=self.name, job=self.job, instructions=self.instructions, avatar=avatar)
```

`roost/talk/team_tools.py`. Find:

```python
            "avatar": {"shape": bot.avatar.shape, "color": bot.avatar.color, "badge": bot.avatar.badge}}
```

Replace with:

```python
            "avatar": avatar_dict(bot.avatar)}
```

`roost/talk/team_tools.py`. Find:

```python
            self._scope.user_id, self._scope.thread_id, role="bot", body=json.dumps(args.card()),
```

Replace with:

```python
            self._scope.user_id, self._scope.thread_id, role="bot",
            body=json.dumps(args.card(bot.avatar.color for bot in team)),
```

`roost/talk/team_tools.py`. Find:

```python
        await announce(f"creating {args.name}")
        self._created += 1   # create_bot is not a parallel tool: calls run one by one
        try:
            bot = await self._bots.create(self._scope.user_id, args.draft())
```

Replace with:

```python
        await announce(f"creating {args.name}")
        self._created += 1   # create_bot is not a parallel tool: calls run one by one
        team = await self._bots.list(self._scope.user_id)
        try:
            bot = await self._bots.create(self._scope.user_id, args.draft(member.avatar.color for member in team))
```

`roost/talk/tool_catalog.py`. Find:

```python
from roost.constants import AVATAR_SHAPES, STUCK_REASON_MAX_CHARS
```

Replace with:

```python
from roost.constants import ROBOT_HEADS, ROBOT_SCREENS, STUCK_REASON_MAX_CHARS
```

`roost/talk/tool_catalog.py` (both places: the find matches 2 times; replace each). Find:

```python
            "shape": {"type": "string", "enum": list(AVATAR_SHAPES)},
            "color": {"type": "string", "description": "#RRGGBB"},
```

Replace with:

```python
            "shape": {"type": "string", "enum": list(ROBOT_HEADS), "description": "The robot's head."},
            "screen": {"type": "string", "enum": list(ROBOT_SCREENS), "description": "Its screen's signals."},
            "color": {"type": "string", "description": "#RRGGBB; leave it out for a colour no teammate wears."},
```

`roost/bots/templates.py`. Find:

```python
    avatar=Avatar(shape="tall", color="#eab308", badge="none"),
```

Replace with:

```python
    avatar=Avatar(shape="classic", color="#8b5cf6", badge="none", screen="glow"),
```

`roost/bots/templates.py`. Find:

```python
    avatar=Avatar(shape="round", color="#10b981", badge="none"),
```

Replace with:

```python
    avatar=Avatar(shape="soft", color="#14b8a6", badge="none", screen="pixel"),
```

`roost/bots/templates.py`. Find:

```python
    avatar=Avatar(shape="wide", color="#3b82f6", badge="none"),
```

Replace with:

```python
    avatar=Avatar(shape="monitor", color="#3b82f6", badge="none", screen="signal"),
```

`roost/bots/templates.py`. Find:

```python
from roost.bots.models import Avatar
```

Replace with:

```python
from roost.bots.look import avatar_dict
from roost.bots.models import Avatar
```

`roost/bots/templates.py`. Find:

```python
def template_out(template: BotTemplate) -> dict[str, Any]:
    avatar = template.avatar
    return {"id": template.id, "label": template.label, "name": template.name, "job": template.job,
            "instructions": template.instructions,
            "avatar": {"shape": avatar.shape, "color": avatar.color, "badge": "none"}}
```

Replace with:

```python
def template_out(template: BotTemplate) -> dict[str, Any]:
    return {"id": template.id, "label": template.label, "name": template.name, "job": template.job,
            "instructions": template.instructions, "avatar": avatar_dict(template.avatar)}
```

`roost/bots/template_file.py`. Find:

```python
from roost.bots.models import AvatarShape, Bot
```

Replace with:

```python
from roost.bots.models import AvatarScreen, AvatarShape, Bot
```

`roost/bots/template_file.py`. Find:

```python
class TemplateAvatar(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    shape: AvatarShape
    color: str = Field(pattern=AVATAR_COLOR_PATTERN)
```

Replace with:

```python
class TemplateAvatar(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    shape: AvatarShape
    color: str = Field(pattern=AVATAR_COLOR_PATTERN)
    screen: AvatarScreen = "glow"   # a file shared before the robots has none
```

`roost/bots/template_file.py`. Find:

```python
                        avatar=TemplateAvatar(shape=bot.avatar.shape, color=bot.avatar.color))
```

Replace with:

```python
                        avatar=TemplateAvatar(shape=bot.avatar.shape, color=bot.avatar.color, screen=bot.avatar.screen))
```

`roost/gateway/routes/templates.py`. Find:

```python
            "avatar": {"shape": parsed.avatar.shape, "color": parsed.avatar.color, "badge": "none"}}
```

Replace with:

```python
            "avatar": {"shape": parsed.avatar.shape, "color": parsed.avatar.color, "badge": "none",
                       "screen": parsed.avatar.screen}}
```

- [ ] **Step 6: Run the gateway tests**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_bot_look.py tests/test_bot_store.py tests/test_bots_api.py tests/test_create_bot.py tests/test_suggest_bot.py tests/test_template_file.py tests/test_templates_api.py tests/test_every_bot_tools.py tests/test_main_bot.py -q`
Expected: the gateway tests pass except `test_every_shape_the_gateway_accepts_has_a_head_on_the_web` and `test_the_web_and_the_gateway_share_the_default_colours`, which read `web/src/components/robot/look.ts` and `palette.ts` (the next step writes them).

- [ ] **Step 7: The robot**

`web/src/api/types.ts`. Find:

```ts
export type AvatarShape = "round" | "tall" | "wide" | "egg" | "pear" | "plump" | "crest";
export type AvatarBadge = "none" | "tasks" | "finance" | "notes" | "docs" | "inbox";

export interface AvatarOut {
  shape: AvatarShape;
  color: string; // "#RRGGBB"
  badge: AvatarBadge;
}
```

Replace with:

```ts
// A bot's robot (redesign V1): one of six heads. The S1.6 bird shapes that are not head names stay
// valid and draw as a head (components/robot/look.ts LEGACY_SHAPE_TO_HEAD); nothing migrates.
export type RobotHead = "classic" | "tall" | "wide" | "soft" | "cube" | "monitor";
export type LegacyAvatarShape = "round" | "egg" | "pear" | "plump" | "crest";
export type AvatarShape = RobotHead | LegacyAvatarShape;
// The screen's signal style; an avatar without one (an older card) shows "glow".
export type RobotScreen = "glow" | "pixel" | "signal";
export type AvatarBadge = "none" | "tasks" | "finance" | "notes" | "docs" | "inbox";

export interface AvatarOut {
  shape: AvatarShape;
  color: string; // "#RRGGBB"
  badge: AvatarBadge;
  screen?: RobotScreen;
}
```

Create `web/src/components/robot/look.ts`:

```ts
// How a bot looks (look & feel redesign V1, "Boxbot"): six heads, three screen styles, and the one
// table that draws an old bird shape as a head. Stored avatars keep their old value; nothing migrates.
// roost/constants.py ROBOT_HEADS and LEGACY_AVATAR_SHAPES hold the same names, and
// tests/test_bot_look.py checks that every shape the gateway accepts has a head here.
import type { AvatarOut, AvatarShape, LegacyAvatarShape, RobotHead, RobotScreen } from "../../api/types";

export const ROBOT_HEADS: readonly RobotHead[] = ["classic", "tall", "wide", "soft", "cube", "monitor"];
export const ROBOT_HEAD_LABELS: Readonly<Record<RobotHead, string>> = {
  classic: "Classic", tall: "Tall", wide: "Wide", soft: "Soft", cube: "Cube", monitor: "Monitor",
};
export const DEFAULT_ROBOT_HEAD: RobotHead = "classic";

// The S1.6 bird shapes that are not head names ("tall" and "wide" are both). One entry per line:
// tests/test_bot_look.py reads this table.
export const LEGACY_SHAPE_TO_HEAD: Readonly<Record<LegacyAvatarShape, RobotHead>> = {
  round: "soft",
  egg: "soft",
  pear: "monitor",
  plump: "cube",
  crest: "classic",
};
export const AVATAR_SHAPES: readonly AvatarShape[] = [
  ...ROBOT_HEADS, ...(Object.keys(LEGACY_SHAPE_TO_HEAD) as LegacyAvatarShape[]),
];

export const ROBOT_SCREENS: readonly RobotScreen[] = ["glow", "pixel", "signal"];
export const ROBOT_SCREEN_LABELS: Readonly<Record<RobotScreen, string>> = {
  glow: "Glow icons", pixel: "Pixel icons", signal: "Signals",
};
// The screen style of an avatar that names none (every avatar made before P1).
export const ROBOT_SIGNAL_STYLE: RobotScreen = "glow";

function isHead(shape: string): shape is RobotHead {
  return (ROBOT_HEADS as readonly string[]).includes(shape);
}

/** The head a stored shape draws: a head is itself, a bird maps, anything else is the default. */
export function robotHead(shape: string): RobotHead {
  if (isHead(shape)) return shape;
  return LEGACY_SHAPE_TO_HEAD[shape as LegacyAvatarShape] ?? DEFAULT_ROBOT_HEAD;
}

export function robotScreen(screen: string | null | undefined): RobotScreen {
  return (ROBOT_SCREENS as readonly string[]).includes(screen ?? "") ? (screen as RobotScreen) : ROBOT_SIGNAL_STYLE;
}

// What a look editor sends: the head, colour and screen, never the picture's address.
export type AvatarLook = Pick<AvatarOut, "shape" | "color" | "badge" | "screen">;

export function lookOf(avatar: AvatarOut): AvatarLook {
  return { shape: avatar.shape, color: avatar.color, badge: "none", screen: robotScreen(avatar.screen) };
}
```

Create `web/src/components/robot/palette.ts`:

```ts
// The robots' colours (redesign V1). Colour data, not styling: tokens.test.ts allows this file.
import type { RobotHead, RobotScreen } from "../../api/types";
import { ROBOT_HEADS, ROBOT_SCREENS } from "./look";

// The editor's twelve swatches.
export const ROBOT_COLORS: ReadonlyArray<readonly [string, string]> = [
  ["#8b5cf6", "Violet"], ["#3b82f6", "Blue"], ["#14b8a6", "Teal"], ["#22c55e", "Green"], ["#f97316", "Orange"],
  ["#ec4899", "Pink"], ["#ef4444", "Red"], ["#eab308", "Yellow"], ["#6366f1", "Indigo"], ["#84cc16", "Lime"],
  ["#ffffff", "White"], ["#9ca3af", "Grey"],
];

// A new bot takes the first of these no teammate wears (roost/constants.py BOT_DEFAULT_COLORS, the
// same list: tests/test_bot_look.py compares them). One entry per line.
export const BOT_DEFAULT_COLORS: readonly string[] = [
  "#8b5cf6",
  "#3b82f6",
  "#14b8a6",
  "#22c55e",
  "#f97316",
  "#ec4899",
  "#ef4444",
  "#eab308",
  "#6366f1",
  "#84cc16",
];

export function nextBotColor(used: readonly string[]): string {
  const worn = new Set(used.map((color) => color.toLowerCase()));
  const free = BOT_DEFAULT_COLORS.find((color) => !worn.has(color));
  return free ?? BOT_DEFAULT_COLORS[used.length % BOT_DEFAULT_COLORS.length];
}

function channels(hex: string): [number, number, number] {
  const number = Number.parseInt(hex.slice(1), 16);
  return [(number >> 16) & 255, (number >> 8) & 255, number & 255];
}

const rgb = ([red, green, blue]: number[]) => `rgb(${red}, ${green}, ${blue})`;
const clamp = (value: number) => Math.max(0, Math.min(255, Math.round(value)));

/** Lighter: mixed `amount` (0..1) of the way to white. Signals glow in the bot's colour, tinted. */
export function tint(hex: string, amount: number): string {
  return rgb(channels(hex).map((value) => clamp(value + (255 - value) * amount)));
}

/** Darker: each channel times `factor` (0..1). Rivets, ears and stands. */
export function shade(hex: string, factor: number): string {
  return rgb(channels(hex).map((value) => clamp(value * factor)));
}

export interface SurpriseLook {
  head: RobotHead;
  color: string;
  screen: RobotScreen;
}

function pickOther<T>(items: readonly T[], current: T, random: () => number): T {
  const others = items.filter((item) => item !== current);
  return others[Math.floor(random() * others.length) % others.length];
}

/** "Surprise me": a new head and a new colour, each different from now, and any screen. */
export function surpriseLook(current: SurpriseLook, random: () => number = Math.random): SurpriseLook {
  const colors = ROBOT_COLORS.map(([color]) => color);
  return {
    head: pickOther(ROBOT_HEADS, current.head, random),
    color: pickOther(colors, current.color.toLowerCase(), random),
    screen: ROBOT_SCREENS[Math.floor(random() * ROBOT_SCREENS.length) % ROBOT_SCREENS.length],
  };
}
```

Create `web/src/components/robot/heads.tsx`:

```tsx
import type { ReactElement } from "react";
import type { RobotHead } from "../../api/types";
import { shade, tint } from "./palette";

// The six Boxbot heads (redesign V1), on a 120 x 120 grid, drawn in the bot's colour. Each has a dark
// screen; RobotFace draws the screen and its signal into the box this module gives.
export interface ScreenBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export const HEAD_SCREENS: Readonly<Record<RobotHead, ScreenBox>> = {
  classic: { x: 30, y: 38, width: 60, height: 48 },
  tall: { x: 36, y: 30, width: 48, height: 58 },
  wide: { x: 20, y: 40, width: 80, height: 46 },
  soft: { x: 30, y: 36, width: 60, height: 50 },
  cube: { x: 30, y: 42, width: 50, height: 46 },
  monitor: { x: 22, y: 22, width: 76, height: 56 },
};

const RIVET_RADIUS = 2.6;
const DARK = 0.7; // antennas, ears and stands
const RIVET_DARK = 0.65;

function Rivets({ color, at }: { color: string; at: ReadonlyArray<readonly [number, number]> }) {
  return <>{at.map(([cx, cy]) => <circle key={`${cx}-${cy}`} cx={cx} cy={cy} r={RIVET_RADIUS} fill={shade(color, RIVET_DARK)} />)}</>;
}

// A zigzag antenna, bottom first: the head's top centre, then two folds up.
function Zigzag({ color, d }: { color: string; d: string }) {
  return <path d={d} stroke={shade(color, DARK)} strokeWidth={3.5} fill="none" strokeLinejoin="round" />;
}

function Classic({ color }: { color: string }) {
  return (
    <>
      <Zigzag color={color} d="M60 24 l-6 -9 h12 l-6 -9" />
      <rect x={20} y={24} width={80} height={72} rx={10} fill={color} />
      <Rivets color={color} at={[[28, 32], [92, 32], [28, 88], [92, 88]]} />
    </>
  );
}

function Tall({ color }: { color: string }) {
  return (
    <>
      <Zigzag color={color} d="M60 16 l-5 -7 h10 l-5 -7" />
      <rect x={28} y={16} width={64} height={90} rx={10} fill={color} />
      <Rivets color={color} at={[[35, 23], [85, 23], [35, 99], [85, 99]]} />
    </>
  );
}

// A TV: two antennas with balls, and an ear on each side.
function Wide({ color }: { color: string }) {
  return (
    <>
      <path d="M44 30 l-12 -18 M76 30 l12 -18" stroke={shade(color, DARK)} strokeWidth={3.5} strokeLinecap="round" />
      <circle cx={32} cy={11} r={4} fill={tint(color, 0.3)} />
      <circle cx={88} cy={11} r={4} fill={tint(color, 0.3)} />
      <rect x={10} y={30} width={100} height={66} rx={12} fill={color} />
      <rect x={4} y={52} width={8} height={22} rx={3} fill={shade(color, DARK)} />
      <rect x={108} y={52} width={8} height={22} rx={3} fill={shade(color, DARK)} />
    </>
  );
}

function Soft({ color }: { color: string }) {
  return (
    <>
      <line x1={60} y1={8} x2={60} y2={22} stroke={shade(color, DARK)} strokeWidth={4} strokeLinecap="round" />
      <circle cx={60} cy={8} r={5} fill={tint(color, 0.3)} />
      <rect x={18} y={22} width={84} height={78} rx={26} fill={color} />
    </>
  );
}

// A box seen from a corner: a lit top, a shaded side, the front.
function Cube({ color }: { color: string }) {
  return (
    <>
      <Zigzag color={color} d="M54 28 l-6 -9 h12 l-6 -9" />
      <path d="M22 32 L38 18 H104 L88 32 Z" fill={tint(color, 0.25)} />
      <path d="M88 32 L104 18 V86 L88 100 Z" fill={shade(color, 0.72)} />
      <rect x={22} y={32} width={66} height={68} rx={6} fill={color} />
      <Rivets color={color} at={[[29, 39], [81, 39], [29, 93], [81, 93]]} />
    </>
  );
}

// A screen on a stand, with a small light.
function Monitor({ color }: { color: string }) {
  return (
    <>
      <rect x={14} y={14} width={92} height={74} rx={10} fill={color} />
      <rect x={50} y={88} width={20} height={12} fill={shade(color, DARK)} />
      <rect x={36} y={100} width={48} height={7} rx={3} fill={shade(color, DARK)} />
      <circle cx={96} cy={81} r={2.5} fill={tint(color, 0.5)} />
    </>
  );
}

const HEADS: Readonly<Record<RobotHead, (props: { color: string }) => ReactElement>> = {
  classic: Classic, tall: Tall, wide: Wide, soft: Soft, cube: Cube, monitor: Monitor,
};

export function RobotHeadShape({ head, color }: { head: RobotHead; color: string }) {
  const Head = HEADS[head];
  return <g className="robot__head"><Head color={color} /></g>;
}
```

Create `web/src/components/robot/moments.ts`:

```ts
import type { BotStatus } from "../../api/types";

// What a robot's screen can show (redesign V1): the five statuses and three moments.
export type RobotMoment = "rest" | "onit" | "ask" | "stuck" | "off" | "think" | "msg" | "done";

export const ROBOT_MOMENTS: readonly RobotMoment[] = ["rest", "onit", "ask", "stuck", "off", "think", "msg", "done"];

export const STATUS_MOMENT: Readonly<Record<BotStatus, RobotMoment>> = {
  resting: "rest", on_it: "onit", asking_you: "ask", stuck: "stuck", off_duty: "off",
};
```

Create `web/src/components/robot/signalGlow.tsx`:

```tsx
import type { ReactElement } from "react";
import type { RobotMoment } from "./moments";

// Screen style "glow" (Glow icons, the default): clean glowing line icons, drawn around (0, 0) in the
// ink colour. Animated parts carry a robot-anim class (styles/robot.css).
const SPINNER_DOTS = 8;
const SPINNER_RADIUS = 11;
const LINE = { fill: "none", strokeLinecap: "round", strokeLinejoin: "round" } as const;

function Spinner({ ink }: { ink: string }) {
  return (
    <g className="robot-anim--spin">
      {Array.from({ length: SPINNER_DOTS }, (_, index) => {
        const angle = (index * 2 * Math.PI) / SPINNER_DOTS;
        return (
          <circle key={index} cx={(SPINNER_RADIUS * Math.cos(angle)).toFixed(1)} cy={(SPINNER_RADIUS * Math.sin(angle)).toFixed(1)}
            r={2.6} fill={ink} opacity={(0.2 + index * 0.1).toFixed(2)} />
        );
      })}
    </g>
  );
}

const GLOW: Readonly<Record<RobotMoment, (ink: string) => ReactElement>> = {
  rest: (ink) => <path className="robot-anim--pulse" d="M-16 0 q4 -7 8 0 t8 0 t8 0 t8 0" stroke={ink} strokeWidth={3} {...LINE} />,
  onit: (ink) => <Spinner ink={ink} />,
  ask: (ink) => (
    <>
      <path d="M-15 -11 h30 a4 4 0 0 1 4 4 v12 a4 4 0 0 1 -4 4 h-20 l-7 6 v-6 h-3 a4 4 0 0 1 -4 -4 v-12 a4 4 0 0 1 4 -4z"
        stroke={ink} strokeWidth={2.6} {...LINE} />
      <path d="M-3.5 -4 a3.5 3.5 0 1 1 5 3.2 c-1.5 0.8 -1.5 1.6 -1.5 2.8 M0 5 v0.5" stroke={ink} strokeWidth={2.4} {...LINE} />
    </>
  ),
  stuck: (ink) => (
    <>
      <path d="M0 -13 l14 24 h-28z" stroke={ink} strokeWidth={2.8} {...LINE} />
      <path className="robot-anim--blink" d="M0 -4 v7 M0 7 v0.5" stroke={ink} strokeWidth={3} {...LINE} />
    </>
  ),
  off: (ink) => <path d="M4 -12 a12 12 0 1 0 8 19 a10 10 0 0 1 -8 -19z" fill={ink} opacity={0.65} />,
  think: (ink) => (
    <>
      {[0, 1, 2].map((index) => (
        <circle key={index} className="robot-anim--pulse" style={{ animationDelay: `${index * 0.25}s` }}
          cx={-10 + index * 10} cy={0} r={3.4} fill={ink} />
      ))}
    </>
  ),
  msg: (ink) => (
    <>
      <rect x={-15} y={-10} width={30} height={20} rx={3} stroke={ink} strokeWidth={2.6} fill="none" />
      <path d="M-15 -9 l15 11 l15 -11" stroke={ink} strokeWidth={2.6} {...LINE} />
      <circle className="robot__notify robot-anim--pulse" cx={15} cy={-10} r={4} />
    </>
  ),
  done: (ink) => <path d="M-12 0 l8 8 l16 -16" stroke={ink} strokeWidth={3.6} {...LINE} />,
};

export function glowSignal(moment: RobotMoment, ink: string): ReactElement {
  return GLOW[moment](ink);
}
```

Create `web/src/components/robot/signalPixel.tsx`:

```tsx
import type { ReactElement } from "react";
import type { RobotMoment } from "./moments";

// Screen style "pixel" (Pixel icons): chunky 8-bit icons, drawn around (0, 0). Each map row is one
// line of pixels; "#" is lit.
const PIXEL_MAPS = {
  heart: [".##.##.", "#######", "#######", ".#####.", "..###..", "...#..."],
  question: [".###.", "#...#", "....#", "...#.", "..#..", ".....", "..#.."],
  bang: ["##", "##", "##", "##", "..", "##"],
  moon: ["..###", ".##..", "##...", "##...", "##...", ".##..", "..###"],
  check: ["......#", ".....##", "#...##.", "##.##..", ".###...", "..#...."],
  bubble: ["#######", "#.....#", "#.#.#.#", "#.....#", "#######", ".##....", ".#....."],
  think: ["..#..", ".###.", "#####", ".###.", "..#.."],
} as const;
const GAP = 0.5; // between pixels

interface PixelsProps {
  rows: readonly string[];
  ink: string;
  cell?: number;
  className?: string;
  opacity?: number;
}

function Pixels({ rows, ink, cell = 3.6, className, opacity }: PixelsProps) {
  const left = -(rows[0].length * cell) / 2;
  const top = -(rows.length * cell) / 2;
  return (
    <g className={className} opacity={opacity}>
      {rows.flatMap((row, y) => [...row].map((lit, x) => (lit === "#" ? (
        <rect key={`${x}-${y}`} x={(left + x * cell).toFixed(1)} y={(top + y * cell).toFixed(1)}
          width={cell - GAP} height={cell - GAP} rx={0.6} fill={ink} />
      ) : null)))}
    </g>
  );
}

function LoadingBar({ ink }: { ink: string }) {
  return (
    <>
      {[0, 1, 2, 3].map((index) => (
        <rect key={index} className="robot-anim--seq" style={{ animationDelay: `${index * 0.3}s` }}
          x={-17 + index * 9} y={-4} width={7} height={8} rx={1} fill={ink} />
      ))}
      <rect x={-19} y={-7} width={38} height={14} rx={2} stroke={ink} strokeWidth={1.6} fill="none" opacity={0.5} />
    </>
  );
}

const PIXEL: Readonly<Record<RobotMoment, (ink: string) => ReactElement>> = {
  rest: (ink) => <Pixels rows={PIXEL_MAPS.heart} ink={ink} className="robot-anim--pulse" />,
  onit: (ink) => <LoadingBar ink={ink} />,
  ask: (ink) => <Pixels rows={PIXEL_MAPS.question} ink={ink} />,
  stuck: (ink) => <Pixels rows={PIXEL_MAPS.bang} ink={ink} cell={4} className="robot-anim--blink" />,
  off: (ink) => <Pixels rows={PIXEL_MAPS.moon} ink={ink} cell={3.2} opacity={0.65} />,
  think: (ink) => <Pixels rows={PIXEL_MAPS.think} ink={ink} cell={3.4} className="robot-anim--spin" />,
  msg: (ink) => <Pixels rows={PIXEL_MAPS.bubble} ink={ink} cell={3.4} />,
  done: (ink) => <Pixels rows={PIXEL_MAPS.check} ink={ink} cell={3.4} />,
};

export function pixelSignal(moment: RobotMoment, ink: string): ReactElement {
  return PIXEL[moment](ink);
}
```

Create `web/src/components/robot/signalWave.tsx`:

```tsx
import type { ReactElement } from "react";
import type { RobotMoment } from "./moments";

// Screen style "signal" (Signals): no icons, only motion, like an instrument display. Drawn around (0, 0).
const LINE = { fill: "none", strokeLinecap: "round", strokeLinejoin: "round" } as const;
const GLITCH_BARS: ReadonlyArray<readonly [number, number, number]> = [[-14, -8, 24], [-8, -1, 22], [-16, 6, 26]];

const WAVE: Readonly<Record<RobotMoment, (ink: string) => ReactElement>> = {
  rest: (ink) => <circle className="robot-anim--pulse" r={9} stroke={ink} strokeWidth={3} fill="none" />,
  onit: (ink) => (
    <>
      {[0, 1, 2, 3, 4].map((index) => (
        <rect key={index} className="robot-anim--bob" style={{ animationDelay: `${index * 0.12}s` }}
          x={-14 + index * 6} y={-10} width={4} height={20} rx={2} fill={ink} />
      ))}
    </>
  ),
  ask: (ink) => (
    <>
      <path d="M-15 -6 l6 6 l-6 6" stroke={ink} strokeWidth={3} {...LINE} />
      <rect className="robot-anim--blink" x={-4} y={-8} width={10} height={16} rx={1.5} fill={ink} />
    </>
  ),
  stuck: (ink) => (
    <>
      <g className="robot-anim--glitch">
        {GLITCH_BARS.map(([x, y, width]) => <rect key={`${x}-${y}`} x={x} y={y} width={width} height={4} fill={ink} />)}
      </g>
      <rect className="robot__alert" x={6} y={-1} width={6} height={4} />
    </>
  ),
  off: (ink) => <circle r={3.5} fill={ink} opacity={0.45} />,
  think: (ink) => (
    <circle className="robot-anim--spin" r={10} stroke={ink} strokeWidth={3} fill="none" strokeDasharray="16 48" strokeLinecap="round" />
  ),
  msg: (ink) => (
    <>
      <circle className="robot-anim--ripple" r={12} stroke={ink} strokeWidth={2.5} fill="none" />
      <circle r={4} fill={ink} />
    </>
  ),
  done: (ink) => (
    <>
      <circle r={12} fill={ink} opacity={0.9} />
      <path className="robot__cut" d="M-6 0 l4 4 l8 -8" strokeWidth={3} {...LINE} />
    </>
  ),
};

export function waveSignal(moment: RobotMoment, ink: string): ReactElement {
  return WAVE[moment](ink);
}
```

Create `web/src/components/robot/signals.tsx`:

```tsx
import type { ReactElement } from "react";
import type { RobotScreen } from "../../api/types";
import type { RobotMoment } from "./moments";
import { glowSignal } from "./signalGlow";
import { pixelSignal } from "./signalPixel";
import { waveSignal } from "./signalWave";

export { ROBOT_SIGNAL_STYLE } from "./look";

const STYLES: Readonly<Record<RobotScreen, (moment: RobotMoment, ink: string) => ReactElement>> = {
  glow: glowSignal, pixel: pixelSignal, signal: waveSignal,
};

export interface RobotSignalProps {
  style: RobotScreen; // the bot's screen style
  moment: RobotMoment;
  color: string; // the ink: the bot's colour, lightened
}

// What a robot's screen shows (redesign V1), drawn around (0, 0): RobotFace moves it to the screen's
// middle. Each bot picks its own style; a style draws all eight moments.
export function RobotSignal({ style, moment, color }: RobotSignalProps) {
  return (
    <g className={`robot__signal robot__signal--${style}`} data-moment={moment}>
      {STYLES[style](moment, color)}
    </g>
  );
}
```

Create `web/src/components/robot/RobotFace.tsx`:

```tsx
import type { RobotHead, RobotScreen } from "../../api/types";
import { cx } from "../../ui/cx";
import { HEAD_SCREENS, RobotHeadShape } from "./heads";
import { ROBOT_SIGNAL_STYLE } from "./look";
import type { RobotMoment } from "./moments";
import { tint } from "./palette";
import { RobotSignal } from "./signals";

const VIEW = 120;
const SCREEN_RADIUS = 8;
const INK_TINT = 0.55; // the signal: the bot's colour, lightened to glow on the dark screen
const GLOW_PX = 3;

export interface RobotFaceProps {
  head: RobotHead;
  color: string; // "#RRGGBB"
  screen?: RobotScreen;
  moment?: RobotMoment;
  star?: boolean; // the main bot
  size?: number; // px
  title?: string; // the accessible name; without one the drawing is hidden from assistive tech
  still?: boolean; // no motion: the user prefers reduced motion
  className?: string;
}

function Star() {
  return (
    <g className="robot__star" transform="translate(98 99)">
      <circle r={12} />
      <path className="robot__star-mark" d="M0 -6.5 l2 4 4.4 .7 -3.2 3.1 .8 4.4 -4 -2.1 -4 2.1 .8 -4.4 -3.2 -3.1 4.4 -.7z" />
    </g>
  );
}

// A Boxbot (redesign V1): its head in the bot's colour, a dark screen, and the screen's signal.
export function RobotFace({
  head, color, screen = ROBOT_SIGNAL_STYLE, moment = "rest", star = false, size = 96, title, still = false, className,
}: RobotFaceProps) {
  const box = HEAD_SCREENS[head];
  const ink = tint(color, INK_TINT);
  const a11y = title ? { role: "img", "aria-label": title } : { "aria-hidden": true, focusable: false };
  return (
    <svg className={cx("robot", still && "robot--still", className)} width={size} height={size} viewBox={`0 0 ${VIEW} ${VIEW}`}
      data-head={head} data-screen={screen} data-moment={moment} {...a11y}>
      <RobotHeadShape head={head} color={color} />
      <rect className="robot__screen" x={box.x} y={box.y} width={box.width} height={box.height} rx={SCREEN_RADIUS} />
      <rect className="robot__glare" x={box.x + 3} y={box.y + 3} width={box.width - 6} height={box.height / 3} rx={5} />
      <g transform={`translate(${box.x + box.width / 2} ${box.y + box.height / 2})`}
        style={{ filter: `drop-shadow(0 0 ${GLOW_PX}px ${ink})` }}>
        <RobotSignal style={screen} moment={moment} color={ink} />
      </g>
      {star ? <Star /> : null}
    </svg>
  );
}
```

Create `web/src/styles/robot.css`:

```css
/* ---------------------------------------------------------------------
   Robot avatars (components/robot, redesign V1 "Boxbot"): the dark
   screen, the star, and the signals' motion. Motion runs only when the
   user has no reduced-motion preference, and never on a still robot
   (robot--still, set from the same preference for tests to see).
   --------------------------------------------------------------------- */

.robot {
  display: block;
  overflow: visible;
}

.robot__screen {
  fill: var(--robot-screen);
}

.robot__glare {
  fill: var(--robot-glare);
}

.robot__notify {
  fill: var(--robot-star);
}

.robot__alert {
  fill: var(--robot-alert);
}

.robot__cut {
  stroke: var(--robot-screen);
}

.robot__star circle {
  fill: var(--robot-star);
  stroke: var(--color-panel);
  stroke-width: 3;
}

.robot__star-mark {
  fill: var(--robot-star-mark);
}

.robot [class*="robot-anim--"] {
  transform-box: fill-box;
  transform-origin: center;
}

.robot .robot-anim--bob {
  transform-origin: bottom;
}

@media (prefers-reduced-motion: no-preference) {
  .robot:not(.robot--still) .robot-anim--spin {
    animation: robot-spin 1.1s linear infinite;
  }

  .robot:not(.robot--still) .robot-anim--pulse {
    animation: robot-pulse 2.6s ease-in-out infinite;
  }

  .robot:not(.robot--still) .robot-anim--bob {
    animation: robot-bob 0.9s ease-in-out infinite;
  }

  .robot:not(.robot--still) .robot-anim--blink {
    animation: robot-blink 1s steps(1) infinite;
  }

  .robot:not(.robot--still) .robot-anim--glitch {
    animation: robot-glitch 0.6s steps(2) infinite;
  }

  .robot:not(.robot--still) .robot-anim--ripple {
    animation: robot-ripple 1.8s ease-out infinite;
  }

  .robot:not(.robot--still) .robot-anim--seq {
    animation: robot-seq 1.2s steps(1) infinite;
  }
}

@keyframes robot-spin {
  to {
    transform: rotate(360deg);
  }
}

@keyframes robot-pulse {
  0%,
  100% {
    opacity: 0.55;
    transform: scale(0.92);
  }
  50% {
    opacity: 1;
    transform: scale(1.06);
  }
}

@keyframes robot-bob {
  0%,
  100% {
    transform: scaleY(0.35);
  }
  50% {
    transform: scaleY(1);
  }
}

@keyframes robot-blink {
  50% {
    opacity: 0;
  }
}

@keyframes robot-glitch {
  0% {
    transform: translateX(-2px);
  }
  50% {
    transform: translateX(2px);
  }
}

@keyframes robot-ripple {
  from {
    opacity: 0.9;
    transform: scale(0.4);
  }
  to {
    opacity: 0;
    transform: scale(1.3);
  }
}

@keyframes robot-seq {
  0%,
  24% {
    opacity: 0.2;
  }
  25%,
  100% {
    opacity: 1;
  }
}
```

Replace the whole of `web/src/styles/avatar.css` with: (the bird's poses and the perch branch go)

```css
/* ---------------------------------------------------------------------
   Avatar (redesign V1): the robot (robot.css draws it) with its status
   in words under it. The status label is a coloured dot plus the word,
   always both: colour is never the only signal.
   --------------------------------------------------------------------- */

.avatar-wrap {
  display: inline-flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-2);
}

.status-label {
  --status-color: var(--color-text-secondary);
  display: inline-flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  font-size: var(--fs-caption);
  line-height: 1.35;
}

.avatar-wrap > .status-label {
  align-items: center;
  text-align: center;
}

.status-label__state {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--color-text-secondary);
  font-weight: 500;
  white-space: nowrap;
}

.status-label__dot {
  flex: none;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--status-color);
}

.status-label--resting .status-label__dot {
  background: transparent;
  box-shadow: inset 0 0 0 1.5px var(--color-text-secondary);
}

.status-label--on_it {
  --status-color: var(--status-on-it);
}

.status-label--asking_you {
  --status-color: var(--status-asking);
}

.status-label--stuck {
  --status-color: var(--status-stuck);
}

.status-label--off_duty {
  --status-color: var(--status-off);
}

.status-label--on_it .status-label__state,
.status-label--asking_you .status-label__state,
.status-label--stuck .status-label__state {
  color: var(--status-color);
}

@media (prefers-reduced-motion: no-preference) {
  .status-label--on_it .status-label__dot {
    animation: status-pulse 1.8s ease-in-out infinite;
  }
}

@keyframes status-pulse {
  0%,
  100% {
    box-shadow: 0 0 0 0 var(--color-accent-edge);
  }
  50% {
    box-shadow: 0 0 0 4px transparent;
  }
}

.status-label__activity {
  max-width: 160px;
  overflow: hidden;
  font-family: var(--font-mono);
  color: var(--color-text-secondary);
  text-overflow: ellipsis;
  white-space: nowrap;
}
```

`web/src/styles.css`. Find:

```css
@import "./styles/avatar.css";
```

Replace with:

```css
@import "./styles/avatar.css";
@import "./styles/robot.css";
```

- [ ] **Step 8: The avatar, the picker and every caller**

Replace the whole of `web/src/components/Avatar.tsx` with:

```tsx
import { usePrefersReducedMotion } from "../hooks/usePrefersReducedMotion";
import { cx } from "../ui/cx";
import { RobotFace } from "./robot/RobotFace";
import { robotHead, robotScreen } from "./robot/look";
import { STATUS_MOMENT, type RobotMoment } from "./robot/moments";
import { STATUS_LABELS, StatusLabel } from "./StatusLabel";
import type { AvatarOut, BotStatus } from "../api/types";

// A bot's avatar (redesign V1): its robot, whose screen shows the status, and the status in words
// beside it (spec 7.3: colour is never the only signal). Any stored shape draws: a bird maps to a
// head (robot/look.ts). Reduced motion stills the screen; `avatar--reduced-motion` lets tests see it.
export interface AvatarProps {
  avatar: AvatarOut;
  status: BotStatus;
  activity?: string | null;
  size?: number;
  // `label={false}` drops the words under the robot: only for callers that show StatusLabel beside it.
  label?: boolean;
  // A repeat of a bot named nearby (message avatars): hidden from assistive tech.
  decorative?: boolean;
  // The main bot wears a star (S1.4); no other bot does.
  star?: boolean;
  // A moment instead of the status's own (P2's typing indicator shows "think").
  moment?: RobotMoment;
}

export function Avatar({
  avatar, status, activity = null, size = 96, label = true, decorative = false, star = false, moment,
}: AvatarProps) {
  const reducedMotion = usePrefersReducedMotion();
  return (
    <div className="avatar-wrap">
      <RobotFace className={cx("avatar", `avatar--${status}`, reducedMotion && "avatar--reduced-motion")}
        head={robotHead(avatar.shape)} color={avatar.color} screen={robotScreen(avatar.screen)}
        moment={moment ?? STATUS_MOMENT[status]} star={star} size={size} still={reducedMotion}
        title={decorative ? undefined : STATUS_LABELS[status]} />
      {label ? <StatusLabel status={status} activity={activity} /> : null}
    </div>
  );
}
```

Replace the whole of `web/src/components/AvatarPicker.tsx` with:

```tsx
import { useId } from "react";
import { Avatar } from "./Avatar";
import { ROBOT_HEADS, ROBOT_HEAD_LABELS, robotHead } from "./robot/look";
import { ROBOT_COLORS } from "./robot/palette";
import type { AvatarOut } from "../api/types";

// The six robot heads and twelve colours (redesign V1). A pick keeps the screen style and drops any
// old badge: every bot has every tool.
export function AvatarPicker({ value, onChange }: { value: AvatarOut; onChange: (avatar: AvatarOut) => void }) {
  const group = useId();
  const head = robotHead(value.shape);
  return (
    <div className="avatar-picker">
      <fieldset className="avatar-picker__shapes">
        <legend className="field__label">Shape</legend>
        {ROBOT_HEADS.map((shape) => (
          <label key={shape} className="avatar-picker__shape" title={ROBOT_HEAD_LABELS[shape]}>
            <input type="radio" name={`${group}-shape`} className="sr-only" aria-label={ROBOT_HEAD_LABELS[shape]}
              checked={head === shape} onChange={() => onChange({ ...value, shape, badge: "none" })} />
            <Avatar avatar={{ ...value, shape }} status="resting" size={48} label={false} decorative />
          </label>
        ))}
      </fieldset>
      <fieldset className="avatar-picker__colors">
        <legend className="field__label">Colour</legend>
        {ROBOT_COLORS.map(([color, label]) => (
          <label key={color} className="avatar-picker__swatch" style={{ background: color }} title={label}>
            <input type="radio" name={`${group}-color`} className="sr-only" aria-label={label}
              checked={value.color.toLowerCase() === color} onChange={() => onChange({ ...value, color, badge: "none" })} />
          </label>
        ))}
      </fieldset>
    </div>
  );
}
```

The robot stands on nothing: perch is gone.

`web/src/components/CreatedBotCard.tsx`. Find:

```tsx
      icon={<Avatar avatar={card.avatar} status="resting" size={32} label={false} perch={false} decorative />}
```

Replace with:

```tsx
      icon={<Avatar avatar={card.avatar} status="resting" size={32} label={false} decorative />}
```

The robot stands on nothing: perch is gone.

`web/src/components/SuggestionCard.tsx`. Find:

```tsx
      icon={<Avatar avatar={suggestion.avatar} status="resting" size={32} label={false} perch={false} decorative />}
```

Replace with:

```tsx
      icon={<Avatar avatar={suggestion.avatar} status="resting" size={32} label={false} decorative />}
```

The robot stands on nothing: perch is gone.

`web/src/components/ChatList.tsx`. Find:

```tsx
          <Avatar avatar={bot.avatar} status={bot.status} size={44} label={false} perch={false} decorative star={bot.is_primary} />
```

Replace with:

```tsx
          <Avatar avatar={bot.avatar} status={bot.status} size={44} label={false} decorative star={bot.is_primary} />
```

The robot stands on nothing: perch is gone.

`web/src/components/MessageRow.tsx`. Find:

```tsx
          {runStart ? <Avatar avatar={avatar} status="resting" size={32} label={false} perch={false} decorative /> : null}
```

Replace with:

```tsx
          {runStart ? <Avatar avatar={avatar} status="resting" size={32} label={false} decorative /> : null}
```

The robot stands on nothing: perch is gone.

`web/src/pages/Home.tsx`. Find:

```tsx
      <Avatar avatar={bot.avatar} status={bot.status} activity={bot.activity} size={120} perch={false} label={false} decorative star />
```

Replace with:

```tsx
      <Avatar avatar={bot.avatar} status={bot.status} activity={bot.activity} size={120} label={false} decorative star />
```

The robot stands on nothing: perch is gone.

`web/src/pages/Room.tsx`. Find:

```tsx
            <Avatar avatar={bot.avatar} status={bot.status} size={28} label={false} perch={false} decorative />
```

Replace with:

```tsx
            <Avatar avatar={bot.avatar} status={bot.status} size={28} label={false} decorative />
```

The robot stands on nothing: perch is gone.

`web/src/pages/Chat.tsx`. Find:

```tsx
        <Avatar avatar={bot.avatar} status={bot.status} size={32} label={false} perch={false} decorative star={bot.is_primary} />
```

Replace with:

```tsx
        <Avatar avatar={bot.avatar} status={bot.status} size={32} label={false} decorative star={bot.is_primary} />
```

The robot stands on nothing: perch is gone.

`web/src/pages/Profile.tsx`. Find:

```tsx
          <Avatar avatar={shown.avatar} status={shown.status} activity={shown.activity} size={120} perch={false} label={false} decorative star={shown.is_primary} />
```

Replace with:

```tsx
          <Avatar avatar={shown.avatar} status={shown.status} activity={shown.activity} size={120} label={false} decorative star={shown.is_primary} />
```

`web/src/pages/Login.tsx`. Find:

```tsx
import { Avatar } from "../components/Avatar";
import type { AvatarOut } from "../api/types";

// The Roost bird that sits on the login card's top edge.
const MASCOT: AvatarOut = { shape: "round", color: "#10b981", badge: "none" };
```

Replace with:

```tsx
import { Avatar } from "../components/Avatar";
import { DEFAULT_ROBOT_HEAD, ROBOT_SIGNAL_STYLE } from "../components/robot/look";
import { BOT_DEFAULT_COLORS } from "../components/robot/palette";
import type { AvatarOut } from "../api/types";

// The robot that sits on the login card's top edge.
const MASCOT: AvatarOut = { shape: DEFAULT_ROBOT_HEAD, color: BOT_DEFAULT_COLORS[0], badge: "none", screen: ROBOT_SIGNAL_STYLE };
```

`web/src/pages/Login.tsx`. Find:

```tsx
          <Avatar avatar={MASCOT} status="resting" size={88} perch={false} label={false} decorative />
```

Replace with:

```tsx
          <Avatar avatar={MASCOT} status="resting" size={88} label={false} decorative />
```

`web/src/components/profile/AvatarEditor.tsx`. Find:

```tsx
import { useTemplates } from "../../hooks/useTemplates";
```

Replace with:

```tsx
import { useTemplates } from "../../hooks/useTemplates";
import { DEFAULT_ROBOT_HEAD, ROBOT_SIGNAL_STYLE, lookOf } from "../robot/look";
import { BOT_DEFAULT_COLORS } from "../robot/palette";
```

`web/src/components/profile/AvatarEditor.tsx`. Find:

```tsx
const PLAIN_LOOK: AvatarOut = { shape: "round", color: "#10b981", badge: "none" };

// The profile's look editor (S1.6): a pick saves at once; Reset goes back to the
// bot's template look (or the plain green round bird).
```

Replace with:

```tsx
const PLAIN_LOOK: AvatarOut = { shape: DEFAULT_ROBOT_HEAD, color: BOT_DEFAULT_COLORS[0], badge: "none", screen: ROBOT_SIGNAL_STYLE };

// The profile's look editor (S1.6): a pick saves at once; Reset goes back to the
// bot's template look (or the plain violet classic robot).
```

`web/src/components/profile/AvatarEditor.tsx`. Find:

```tsx
      onChange(await botsApi.updateBot(bot.id, { avatar: { ...avatar, badge: "none" } }));
```

Replace with:

```tsx
      onChange(await botsApi.updateBot(bot.id, { avatar: lookOf(avatar) }));
```

`web/src/components/ShareTemplateDialog.tsx`. Find:

```tsx
import { COLORS, SHAPE_LABELS } from "./AvatarPicker";

const lookInWords = ({ shape, color }: BotOut["avatar"]) => {
  const shapeName = SHAPE_LABELS.find(([id]) => id === shape)?.[1] ?? shape;
  const colorName = COLORS.find(([hex]) => hex === color.toLowerCase())?.[1] ?? color;
  return `${shapeName}, ${colorName.toLowerCase()}`;
};
```

Replace with:

```tsx
import { ROBOT_HEAD_LABELS, ROBOT_SCREEN_LABELS, robotHead, robotScreen } from "./robot/look";
import { ROBOT_COLORS } from "./robot/palette";

// "Classic head, violet, glow icons".
const lookInWords = ({ shape, color, screen }: BotOut["avatar"]) => {
  const colorName = ROBOT_COLORS.find(([hex]) => hex === color.toLowerCase())?.[1] ?? color;
  const screenName = ROBOT_SCREEN_LABELS[robotScreen(screen)];
  return `${ROBOT_HEAD_LABELS[robotHead(shape)]} head, ${colorName.toLowerCase()}, ${screenName.toLowerCase()}`;
};
```

`web/src/lib/team.ts`. Find:

```ts
import type { AvatarBadge, AvatarShape, BotOut, CreatedCardData, SuggestionCardData } from "../api/types";

const SHAPES: readonly AvatarShape[] = ["round", "tall", "wide", "egg", "pear", "plump", "crest"];
const BADGES: readonly AvatarBadge[] = ["none", "tasks", "finance", "notes", "docs", "inbox"];
```

Replace with:

```ts
import type { AvatarBadge, BotOut, CreatedCardData, RobotScreen, SuggestionCardData } from "../api/types";
import { AVATAR_SHAPES as SHAPES, ROBOT_SCREENS, robotScreen } from "../components/robot/look";

const BADGES: readonly AvatarBadge[] = ["none", "tasks", "finance", "notes", "docs", "inbox"];

// A card's screen style: one of the three, or none (a card from before the robots).
const screenOf = (value: unknown): RobotScreen | null =>
  value === undefined ? robotScreen(undefined) : (ROBOT_SCREENS as readonly unknown[]).includes(value) ? (value as RobotScreen) : null;
```

`web/src/lib/team.ts`. Find:

```ts
      SHAPES.includes(avatar?.shape) &&
      typeof avatar?.color === "string" &&
      HEX_COLOR.test(avatar.color) &&
      BADGES.includes(avatar?.badge);
    if (!valid) return null;
    return { name: data.name, job: data.job, avatar: { shape: avatar.shape, color: avatar.color, badge: avatar.badge } };
```

Replace with:

```ts
      SHAPES.includes(avatar?.shape) &&
      typeof avatar?.color === "string" &&
      HEX_COLOR.test(avatar.color) &&
      BADGES.includes(avatar?.badge);
    const screen = screenOf(avatar?.screen);
    if (!valid || screen === null) return null;
    return { name: data.name, job: data.job, avatar: { shape: avatar.shape, color: avatar.color, badge: avatar.badge, screen } };
```

`web/src/lib/team.ts`. Find:

```ts
      && typeof avatar?.color === "string" && HEX_COLOR.test(avatar.color);
    if (!ok) return null;
    return { bot_id: data.bot_id, name: data.name, job: data.job, instructions: data.instructions,
             avatar: { shape: avatar.shape, color: avatar.color, badge: "none" } };
```

Replace with:

```ts
      && typeof avatar?.color === "string" && HEX_COLOR.test(avatar.color);
    const screen = screenOf(avatar?.screen);
    if (!ok || screen === null) return null;
    return { bot_id: data.bot_id, name: data.name, job: data.job, instructions: data.instructions,
             avatar: { shape: avatar.shape, color: avatar.color, badge: "none", screen } };
```

`web/src/components/BotForm.tsx`. Find:

```tsx
import { InstructionsCount } from "./InstructionsCount";
```

Replace with:

```tsx
import { InstructionsCount } from "./InstructionsCount";
import { DEFAULT_ROBOT_HEAD, ROBOT_SIGNAL_STYLE } from "./robot/look";
import { nextBotColor } from "./robot/palette";
```

`web/src/components/BotForm.tsx`. Find:

```tsx
export const DEFAULT_BOT_VALUES: BotFormValues = {
  name: "",
  job: "",
  instructions: "",
  avatar: { shape: "round", color: "#10b981", badge: "none" },
  template_id: null,
};
```

Replace with:

```tsx
// A new bot's form: a classic robot in the first colour no teammate wears (redesign V1).
export function newBotValues(usedColors: readonly string[]): BotFormValues {
  return {
    name: "", job: "", instructions: "", template_id: null,
    avatar: { shape: DEFAULT_ROBOT_HEAD, color: nextBotColor(usedColors), badge: "none", screen: ROBOT_SIGNAL_STYLE },
  };
}
```

`web/src/components/BotForm.tsx`. Find:

```tsx
        <Avatar avatar={values.avatar} status="resting" size={168} perch={false} label={false} decorative />
        <div className="perch-branch perch-branch--short" aria-hidden="true" />
```

Replace with:

```tsx
        <Avatar avatar={values.avatar} status="resting" size={168} label={false} decorative />
```

`web/src/components/BotForm.tsx`. Find:

```tsx
// New bot: name, job, instructions and a look (S1.7), with a live preview
// standing on its own short perch. No roles and no badges: every bot has every tool.
```

Replace with:

```tsx
// New bot: name, job, instructions and a look (S1.7), with a live preview of its robot.
// No roles and no badges: every bot has every tool.
```

`web/src/components/BotForm.tsx`. Find:

```tsx
  const [values, setValues] = useState<BotFormValues>(initial ?? DEFAULT_BOT_VALUES);
```

Replace with:

```tsx
  const [values, setValues] = useState<BotFormValues>(() => initial ?? newBotValues([]));
```

`web/src/pages/NewBot.tsx`. Find:

```tsx
import { BotForm, type BotFormValues } from "../components/BotForm";
import { ErrorNotice } from "../components/ErrorNotice";
import { useTemplates } from "../hooks/useTemplates";
```

Replace with:

```tsx
import { BotForm, newBotValues, type BotFormValues } from "../components/BotForm";
import { ErrorNotice } from "../components/ErrorNotice";
import { useLiveState } from "../hooks/useLiveStore";
import { useTemplates } from "../hooks/useTemplates";
```

`web/src/pages/NewBot.tsx`. Find:

```tsx
  const { templates, error: templatesError } = useTemplates();
```

Replace with:

```tsx
  const { templates, error: templatesError } = useTemplates();
  const usedColors = Object.values(useLiveState().bots).map((bot) => bot.avatar.color);
```

`web/src/pages/NewBot.tsx`. Find:

```tsx
      <BotForm key={formKey} initial={initial} submitLabel="Create bot" onSubmit={(values) => void submit(values)} />
```

Replace with:

```tsx
      <BotForm key={formKey} initial={initial ?? newBotValues(usedColors)} submitLabel="Create bot"
        onSubmit={(values) => void submit(values)} />
```

`web/src/styles/bot-form.css`. Find:

```css
   New bot — live preview on a short perch (left), the form (right).
```

Replace with:

```css
   New bot — a live preview of its robot (left), the form (right).
```

`web/src/styles/bot-form.css`. Find:

```css
/* A 168px bird's feet land at ~150px. */
.bot-form__stage .perch-branch {
  position: absolute;
  top: 149px;
  left: 50%;
  transform: translateX(-50%);
}

```

Delete it.

`web/src/styles/bot-form.css`. Find:

```css
  .bot-form__stage .perch-branch {
    top: 92px;
    width: 112px;
  }

```

Delete it.

`web/src/styles/profile.css`. Find:

```css
.avatar-picker__shapes {
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
```

Replace with:

```css
.avatar-picker__shapes {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
```

`web/src/styles/profile.css`. Find:

```css
  .avatar-picker__shapes {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }
```

Replace with:

```css
  .avatar-picker__shapes {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
```

- [ ] **Step 9: Run the tests to see them pass**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_bot_look.py tests/test_bot_store.py tests/test_bots_api.py tests/test_create_bot.py tests/test_suggest_bot.py tests/test_template_file.py tests/test_templates_api.py tests/test_every_bot_tools.py tests/test_main_bot.py -q`
Expected: PASS (`test_bot_look` has 8 tests).

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && cd web && npx vitest run tests/robotLook.test.ts tests/RobotFace.test.tsx tests/Avatar.test.tsx tests/BotForm.test.tsx tests/NewBot.test.tsx tests/AvatarEditor.test.tsx tests/team.test.ts tests/tokens.test.ts`
Expected: PASS: `robotLook` 8, `RobotFace` 7 (the first draws all 144 head × moment × style robots), `Avatar` 18, `BotForm` 7, `NewBot` 4, `AvatarEditor` 3, `team` 10 and `tokens` 7 tests.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && grep -rn "perch" web/src --include='*.tsx' --include='*.css'`
Expected: no output.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && cd web && npm test && npm run build && npm run size`
Expected: every test file passes, the build succeeds, the entry chunk is within the budget.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest --cov=roost --cov-fail-under=80`
Expected: PASS, with `Required test coverage of 80% reached`.

- [ ] **Step 10: Commit**

Run:

```bash
cd /Users/blckit/Desktop/Code_Projects/roost && \
git add roost/constants.py roost/bots/models.py roost/bots/look.py roost/bots/store.py roost/bots/service.py \
  roost/bots/templates.py roost/bots/template_file.py roost/gateway/routes/bots.py roost/gateway/routes/templates.py \
  roost/talk/team_tools.py roost/talk/tool_catalog.py tests/test_bot_look.py tests/test_bot_store.py \
  tests/test_bots_api.py tests/test_create_bot.py tests/test_suggest_bot.py tests/test_template_file.py \
  web/src/api/types.ts web/src/components/robot/look.ts web/src/components/robot/palette.ts \
  web/src/components/robot/heads.tsx web/src/components/robot/moments.ts web/src/components/robot/signals.tsx \
  web/src/components/robot/signalGlow.tsx web/src/components/robot/signalPixel.tsx \
  web/src/components/robot/signalWave.tsx web/src/components/robot/RobotFace.tsx \
  web/src/components/Avatar.tsx web/src/components/AvatarPicker.tsx web/src/components/BotForm.tsx \
  web/src/components/ShareTemplateDialog.tsx web/src/components/CreatedBotCard.tsx web/src/components/SuggestionCard.tsx \
  web/src/components/ChatList.tsx web/src/components/MessageRow.tsx web/src/components/profile/AvatarEditor.tsx \
  web/src/pages/Home.tsx web/src/pages/Room.tsx web/src/pages/Chat.tsx web/src/pages/Profile.tsx \
  web/src/pages/Login.tsx web/src/pages/NewBot.tsx web/src/lib/team.ts web/src/styles.css \
  web/src/styles/robot.css web/src/styles/avatar.css web/src/styles/bot-form.css web/src/styles/profile.css \
  web/tests/robotLook.test.ts web/tests/RobotFace.test.tsx web/tests/Avatar.test.tsx web/tests/BotForm.test.tsx \
  web/tests/NewBot.test.tsx web/tests/AvatarEditor.test.tsx web/tests/team.test.ts web/tests/tokens.test.ts && \
git commit -m "feat: robot avatars with six heads and three screen styles; old bird shapes still drawn; new bots in a free colour"
```

### Task 6: The avatar editor: Head, Colour, Screen, Surprise me, and a picture of the bot's own

Design P1 "Avatar editor". Today the profile's look editor is the bird picker and a Reset button; there is no way to give a bot a picture (see "Design meets code" 1).
- **`AvatarStudio`** (`web/src/components/avatar/`) is the editor: a big live preview that shows the bot's current status (and the star on the main bot), the Shape, Colour and new Screen pickers, Surprise me (a new head and a new colour, each different from now, and any screen), and, when the bot exists, Upload a picture and Remove picture. The profile's `AvatarEditor` and the New bot form both use it; the New bot form keeps its own preview (name and job beside the robot) and has no Upload, since there is no bot to give a picture to yet.
- **The picture:**
  - In the browser, `shrinkPicture` reads any image the browser can (`createImageBitmap`), crops the middle square and writes it at 256 px as WebP (PNG where WebP cannot be written). A file that is not a picture, or one the browser cannot read, says so in plain words.
  - `POST /api/bots/{id}/picture` takes the raw image, like the PDF upload. The bytes decide what it is (PNG, JPEG or WebP signatures) and must agree with the Content-Type: SVG, GIF and anything else are a 415, more than 512 KB a 413.
  - `BotStore.set_picture` seals it (`enc:v2`, AAD `bots:avatar_picture`) into the avatar JSON's `picture` key. A new look keeps the picture: `update` carries the sealed value over. The Bot carries only a short version tag (`Avatar.picture`), and `bot_out` turns it into the picture's address, `/api/bots/{id}/picture?v={tag}`, so a new picture is a new address and the old one can be cached for good.
  - `GET` serves it with `nosniff`; `DELETE` takes it off. Another user's bot is a 404 everywhere. Every change publishes `bot_updated`, so every avatar of that bot updates live.
  - On the robot, the picture fills the screen, clipped to its rounded box, in place of the signal; the status is still the image's name and the label beside it.

**Files:**
- Create: `roost/bots/picture.py`, `roost/gateway/routes/bot_picture.py`, `tests/test_bot_picture.py`, `web/src/lib/picture.ts`, `web/src/components/avatar/AvatarStudio.tsx`, `web/src/styles/avatar-studio.css`, `web/tests/picture.test.ts`
- Modify:
  - `roost/constants.py`, `roost/bots/{models,store,service}.py`, `roost/gateway/app.py`, `tests/{test_bot_store,test_bots_api,test_bot_look}.py`
  - `web/src/api/{types,bots}.ts`, `web/src/components/icons.tsx`, `web/src/components/robot/RobotFace.tsx`, `web/src/components/{Avatar,AvatarPicker,BotForm}.tsx`, `web/src/components/profile/AvatarEditor.tsx` (replaced), `web/src/styles.css`
  - `web/tests/AvatarEditor.test.tsx` (replaced), `web/tests/{RobotFace,BotForm}.test.tsx`, `web/e2e/profile.spec.ts`
- Test: the new test files and the changed ones

**Interfaces:**
- Consumes: Task 5's `RobotFace`, `HEAD_SCREENS`/`ScreenBox`, `Avatar`, `AvatarPicker`, `robotHead`, `robotScreen`, `lookOf`, `surpriseLook`, `ROBOT_SCREENS`, `ROBOT_SCREEN_LABELS`, `avatar_dict`, `_avatar_dump`/`_avatar_load`; Task 2's `Button`; `apiUpload`, `bot_out`, `RequireOrigin`, `CurrentUser`, `encrypt`/`decrypt`/`user_aad`, `get_user_dek`.
- Produces (Shared Contract "The picture" and "AvatarStudio"): `AVATAR_PICTURE_MAX_BYTES`; `Picture`, `read_picture`, `seal_picture`, `open_picture`, `picture_tag`, `PictureTooBig`, `NotAPicture`, `TOO_BIG_TEXT`, `NOT_A_PICTURE_TEXT`; `BotStore.set_picture`, `BotStore.get_picture`; `Avatar.picture`; the three routes; `AvatarOut.picture`; `uploadPicture`, `removePicture`; `shrinkPicture`, `PictureError`, `PICTURE_SIDE`, `PICTURE_TYPE`, `PICTURE_ACCEPT`; `RobotFace`'s `picture`; `AvatarStudio`; `UploadIcon`, `SparkIcon`. Names Task 7 relies on: the group "Preview", the buttons "Surprise me" and "Remove picture", the file input "Upload a picture", the radios "Glow icons", "Pixel icons", "Signals", and `image.robot__picture`.

- [ ] **Step 1: Path guard**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && git -C /Users/blckit/Desktop/Code_Projects/roost rev-parse --show-toplevel && git -C /Users/blckit/Desktop/Code_Projects/roost branch --show-current`
Expected: `/Users/blckit/Desktop/Code_Projects/roost` then `night-1`. If either differs, stop.

Then confirm Task 5 has landed and this task has not:

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && test -f web/src/components/robot/RobotFace.tsx && test ! -f roost/bots/picture.py && test ! -d web/src/components/avatar && echo ready`
Expected: `ready`.

- [ ] **Step 2: Write the failing gateway tests**

Create `tests/test_bot_picture.py`:

```python
"""A bot's own picture (look & feel redesign P1, the avatar editor's Upload): POST puts it on the
robot's screen, DELETE takes it off, GET serves it. It is sealed (enc:v2) in the avatar JSON, only
PNG, JPEG and WebP get in (by their bytes), and another user's bot is a 404."""

from __future__ import annotations

import json
import re

import httpx
import pytest

from roost.bots.picture import Picture, open_picture, seal_picture
from roost.config import load_config
from roost.constants import AVATAR_PICTURE_MAX_BYTES
from roost.db.connection import db_session, init_db
from roost.gateway.app import create_app
from roost.gateway.auth import register_user
from team_helpers import make_bot

O = {"Origin": "http://127.0.0.1:18800"}
PNG = b"\x89PNG\r\n\x1a\n" + bytes(range(64))
WEBP = b"RIFF\x24\x00\x00\x00WEBPVP8 " + bytes(24)
PICTURE_URL = re.compile(r"^/api/bots/[\w-]+/picture\?v=[0-9a-f]{12}$")
KEY = bytes(range(32))


@pytest.fixture
async def client_and_user():
    cfg = load_config()
    await init_db(cfg)
    app = create_app()
    await register_user(cfg, "alice", "pw-123456")
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://roost.test")
    await client.post("/api/auth/login", json={"username": "alice", "password": "pw-123456"}, headers=O)
    user_id = (await client.get("/api/auth/me")).json()["id"]
    yield cfg, client, user_id
    await client.aclose()


def _upload(client: httpx.AsyncClient, bot_id: str, data: bytes, content_type: str = "image/png"):
    return client.post(f"/api/bots/{bot_id}/picture", content=data, headers={**O, "Content-Type": content_type})


async def test_a_picture_goes_on_the_screen_and_is_served_back(client_and_user):
    cfg, client, user_id = client_and_user
    bot = await make_bot(cfg, user_id, "Scout")
    up = await _upload(client, bot.id, PNG)
    assert up.status_code == 200
    url = up.json()["avatar"]["picture"]
    assert PICTURE_URL.match(url)
    got = await client.get(url)
    assert (got.status_code, got.content, got.headers["content-type"]) == (200, PNG, "image/png")
    assert got.headers["x-content-type-options"] == "nosniff"
    assert "immutable" in got.headers["cache-control"]
    assert (await client.get("/api/bots")).json()[0]["avatar"]["picture"] == url


async def test_the_picture_is_sealed_in_the_avatar_json(client_and_user):
    cfg, client, user_id = client_and_user
    bot = await make_bot(cfg, user_id, "Scout")
    await _upload(client, bot.id, WEBP, "image/webp")
    async with db_session(cfg) as db:
        row = await (await db.execute("SELECT avatar FROM bots WHERE id = ?", (bot.id,))).fetchone()
    stored = json.loads(row["avatar"])
    assert stored["picture"].startswith("enc:v2:")
    assert "UklGR" not in stored["picture"]   # the WebP's base64 start never appears in the clear
    assert {key: stored[key] for key in ("shape", "color", "badge", "screen")} == {
        "shape": "round", "color": "#22c55e", "badge": "none", "screen": "glow"}


async def test_a_new_look_keeps_the_picture_and_a_new_picture_gets_a_new_address(client_and_user):
    cfg, client, user_id = client_and_user
    bot = await make_bot(cfg, user_id, "Scout")
    first = (await _upload(client, bot.id, PNG)).json()["avatar"]["picture"]
    looked = await client.patch(f"/api/bots/{bot.id}", headers=O,
                                json={"avatar": {"shape": "monitor", "color": "#3b82f6", "screen": "signal"}})
    assert looked.json()["avatar"] == {"shape": "monitor", "color": "#3b82f6", "badge": "none", "screen": "signal",
                                       "picture": first}
    second = (await _upload(client, bot.id, WEBP, "image/webp")).json()["avatar"]["picture"]
    assert second != first


async def test_remove_takes_it_off(client_and_user):
    cfg, client, user_id = client_and_user
    bot = await make_bot(cfg, user_id, "Scout")
    url = (await _upload(client, bot.id, PNG)).json()["avatar"]["picture"]
    gone = await client.delete(f"/api/bots/{bot.id}/picture", headers=O)
    assert (gone.status_code, gone.json()["avatar"]["picture"]) == (200, None)
    assert (await client.get(url)).status_code == 404


async def test_only_png_jpeg_and_webp_get_in_and_their_bytes_must_say_so(client_and_user):
    cfg, client, user_id = client_and_user
    bot = await make_bot(cfg, user_id, "Scout")
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
    for data, content_type in ((svg, "image/svg+xml"), (svg, "image/png"), (PNG, "image/jpeg"), (b"GIF89a" + bytes(8), "image/gif")):
        refused = await _upload(client, bot.id, data, content_type)
        assert (refused.status_code, refused.json()["detail"]) == (415, "Upload a PNG, JPEG or WebP picture."), content_type
    big = await _upload(client, bot.id, PNG + bytes(AVATAR_PICTURE_MAX_BYTES))
    assert (big.status_code, big.json()["detail"]) == (413, "That picture is too big (512 KB at most). Try a smaller one.")
    assert (await client.get("/api/bots")).json()[0]["avatar"]["picture"] is None


async def test_another_users_bot_is_a_404_and_an_upload_needs_the_origin(client_and_user):
    cfg, client, user_id = client_and_user
    bob = (await register_user(cfg, "bob", "pw-123456")).id
    bobs = await make_bot(cfg, bob, "Secret")
    assert (await _upload(client, bobs.id, PNG)).status_code == 404
    assert (await client.get(f"/api/bots/{bobs.id}/picture")).status_code == 404
    assert (await client.delete(f"/api/bots/{bobs.id}/picture", headers=O)).status_code == 404
    mine = await make_bot(cfg, user_id, "Scout")
    no_origin = await client.post(f"/api/bots/{mine.id}/picture", content=PNG, headers={"Content-Type": "image/png"})
    assert no_origin.status_code == 403


def test_a_picture_sealed_for_another_key_or_user_does_not_open():
    sealed = seal_picture(Picture("image/png", PNG), KEY, "u1")
    assert open_picture(sealed, KEY, "u1") == Picture("image/png", PNG)
    assert open_picture(sealed, bytes(32), "u1") is None    # another key
    assert open_picture(sealed, KEY, "u2") is None          # another user's AAD
    assert open_picture("enc:v2:bad:bad", KEY, "u1") is None
```

`tests/test_bot_store.py`. Find:

```python
        "avatar": {"shape": "round", "color": "#22c55e", "badge": "none", "screen": "glow"},
        "template_id": "tmpl-1",
```

Replace with:

```python
        "avatar": {"shape": "round", "color": "#22c55e", "badge": "none", "screen": "glow", "picture": None},
        "template_id": "tmpl-1",
```

`tests/test_bots_api.py`. Find:

```python
    assert body["avatar"] == {**VALID_AVATAR, "screen": "glow"}
```

Replace with:

```python
    assert body["avatar"] == {**VALID_AVATAR, "screen": "glow", "picture": None}
```

`tests/test_bot_look.py`. Find:

```python
    assert made.json()["avatar"] == {"shape": "monitor", "color": "#3b82f6", "badge": "none", "screen": "pixel"}
```

Replace with:

```python
    assert made.json()["avatar"] == {"shape": "monitor", "color": "#3b82f6", "badge": "none", "screen": "pixel",
                                     "picture": None}
```

`tests/test_bot_look.py`. Find:

```python
    assert old.json()["avatar"] == {"shape": "egg", "color": "#14b8a6", "badge": "none", "screen": "glow"}
```

Replace with:

```python
    assert old.json()["avatar"] == {"shape": "egg", "color": "#14b8a6", "badge": "none", "screen": "glow",
                                    "picture": None}
```

- [ ] **Step 3: Write the failing web tests**

Create `web/tests/picture.test.ts`:

```ts
import { afterEach, describe, expect, it, vi } from "vitest";
import { PictureError, shrinkPicture } from "../src/lib/picture";

afterEach(() => vi.unstubAllGlobals());

describe("shrinkPicture", () => {
  it("refuses a file that is not a picture, in plain words", async () => {
    await expect(shrinkPicture(new Blob(["%PDF"], { type: "application/pdf" }))).rejects.toThrow(
      new PictureError("That file is not a picture. Pick a PNG, JPEG or WebP."));
  });

  it("says so when the browser can't read the picture", async () => {
    vi.stubGlobal("createImageBitmap", () => Promise.reject(new Error("decode failed")));
    await expect(shrinkPicture(new Blob(["x"], { type: "image/png" }))).rejects.toThrow(
      "Roost could not read that picture. Try another one.");
  });

  it("crops the middle square and writes it at 256 px", async () => {
    const close = vi.fn();
    vi.stubGlobal("createImageBitmap", () => Promise.resolve({ width: 400, height: 200, close }));
    const drawImage = vi.fn();
    const out = new Blob(["webp"], { type: "image/webp" });
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({ drawImage } as unknown as CanvasRenderingContext2D);
    vi.spyOn(HTMLCanvasElement.prototype, "toBlob").mockImplementation(function (callback: BlobCallback) { callback(out); });
    expect(await shrinkPicture(new Blob(["x"], { type: "image/png" }))).toBe(out);
    expect(drawImage).toHaveBeenCalledWith(expect.anything(), 100, 0, 200, 200, 0, 0, 256, 256);
    expect(close).toHaveBeenCalled();
    vi.restoreAllMocks();
  });
});
```

Replace the whole of `web/tests/AvatarEditor.test.tsx` with: (the editor gains Screen, Surprise me and the picture)

```tsx
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AvatarEditor } from "../src/components/profile/AvatarEditor";
import { makeBot } from "./fixtures";

const updateBotMock = vi.fn();
const uploadPictureMock = vi.fn();
const removePictureMock = vi.fn();
vi.mock("../src/api/bots", () => ({
  updateBot: (id: string, p: unknown) => updateBotMock(id, p),
  uploadPicture: (id: string, picture: Blob) => uploadPictureMock(id, picture),
  removePicture: (id: string) => removePictureMock(id),
}));
const shrinkMock = vi.fn();
vi.mock("../src/lib/picture", async (original) => ({
  ...(await original<typeof import("../src/lib/picture")>()),
  shrinkPicture: (file: Blob) => shrinkMock(file),
}));
vi.mock("../src/hooks/useTemplates", () => ({
  useTemplates: () => ({ templates: [{ id: "chief", label: "Main bot", name: "Chief", job: "", instructions: "",
    avatar: { shape: "tall", color: "#eab308", badge: "none" } }], error: null }),
}));

afterEach(() => {
  cleanup();
  for (const mock of [updateBotMock, uploadPictureMock, removePictureMock, shrinkMock]) mock.mockReset();
});

const PNG = new File([new Uint8Array([137, 80, 78, 71])], "me.png", { type: "image/png" });

describe("AvatarEditor", () => {
  it("offers six heads, twelve colours and three screen styles, with a big preview of the bot's status", () => {
    render(<AvatarEditor bot={makeBot({ status: "on_it", is_primary: true })} onChange={vi.fn()} />);
    expect(screen.getAllByRole("radio", { name: /^(Classic|Tall|Wide|Soft|Cube|Monitor)$/ })).toHaveLength(6);
    expect(screen.getByRole("radio", { name: "White" })).toBeInTheDocument();
    expect(screen.getAllByRole("radio", { name: /^(Glow icons|Pixel icons|Signals)$/ })).toHaveLength(3);
    const preview = screen.getByRole("group", { name: "Preview" });
    expect(preview.querySelector("svg.avatar")?.getAttribute("data-moment")).toBe("onit");
    expect(preview.querySelector(".robot__star")).not.toBeNull();
    expect(screen.getByText("How this bot looks everywhere. A picture shows on its screen.")).toBeInTheDocument();
  });

  it("an old bird shape shows as its head, and a new head saves at once, with no badge", async () => {
    const onChange = vi.fn();
    const saved = makeBot({ avatar: { shape: "cube", color: "#10b981", badge: "none", screen: "glow" } });
    updateBotMock.mockResolvedValue(saved);
    render(<AvatarEditor bot={makeBot()} onChange={onChange} />); // makeBot wears the old "round"
    expect(screen.getByRole("radio", { name: "Soft" })).toBeChecked();
    await userEvent.click(screen.getByRole("radio", { name: "Cube" }));
    expect(updateBotMock).toHaveBeenCalledWith("bot-1", { avatar: { shape: "cube", color: "#10b981", badge: "none", screen: "glow" } });
    await vi.waitFor(() => expect(onChange).toHaveBeenCalledWith(saved));
  });

  it("a screen style saves at once and keeps the head and colour", async () => {
    updateBotMock.mockResolvedValue(makeBot());
    render(<AvatarEditor bot={makeBot()} onChange={vi.fn()} />);
    await userEvent.click(screen.getByRole("radio", { name: "Pixel icons" }));
    expect(updateBotMock).toHaveBeenCalledWith("bot-1", { avatar: { shape: "round", color: "#10b981", badge: "none", screen: "pixel" } });
  });

  it("Surprise me saves a new head and a new colour", async () => {
    updateBotMock.mockResolvedValue(makeBot());
    render(<AvatarEditor bot={makeBot({ avatar: { shape: "classic", color: "#8b5cf6", badge: "none", screen: "glow" } })} onChange={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: "Surprise me" }));
    const [, patch] = updateBotMock.mock.calls[0] as [string, { avatar: { shape: string; color: string } }];
    expect(patch.avatar.shape).not.toBe("classic");
    expect(patch.avatar.color).not.toBe("#8b5cf6");
  });

  it("Reset to default uses the bot's template look", async () => {
    updateBotMock.mockResolvedValue(makeBot());
    render(<AvatarEditor bot={makeBot({ template_id: "chief" })} onChange={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: "Reset to default" }));
    expect(updateBotMock).toHaveBeenCalledWith("bot-1", { avatar: { shape: "tall", color: "#eab308", badge: "none", screen: "glow" } });
  });

  it("uploads a picture, shrunk first, and shows it on the screen", async () => {
    const small = new Blob(["webp"], { type: "image/webp" });
    shrinkMock.mockResolvedValue(small);
    const withPicture = makeBot({ avatar: { shape: "round", color: "#10b981", badge: "none", screen: "glow", picture: "/api/bots/bot-1/picture?v=abc123def456" } });
    uploadPictureMock.mockResolvedValue(withPicture);
    const onChange = vi.fn();
    const { rerender } = render(<AvatarEditor bot={makeBot()} onChange={onChange} />);
    await userEvent.upload(screen.getByLabelText("Upload a picture"), PNG);
    expect(shrinkMock).toHaveBeenCalledWith(PNG);
    expect(uploadPictureMock).toHaveBeenCalledWith("bot-1", small);
    await vi.waitFor(() => expect(onChange).toHaveBeenCalledWith(withPicture));
    rerender(<AvatarEditor bot={withPicture} onChange={onChange} />);
    const preview = screen.getByRole("group", { name: "Preview" });
    expect(preview.querySelector("image.robot__picture")?.getAttribute("href")).toBe("/api/bots/bot-1/picture?v=abc123def456");
  });

  it("Remove picture takes it off the screen", async () => {
    removePictureMock.mockResolvedValue(makeBot());
    render(<AvatarEditor bot={makeBot({ avatar: { shape: "soft", color: "#14b8a6", badge: "none", picture: "/api/bots/bot-1/picture?v=1" } })} onChange={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: "Remove picture" }));
    expect(removePictureMock).toHaveBeenCalledWith("bot-1");
  });

  it("says why a picture can't be used, in plain words", async () => {
    const { PictureError } = await import("../src/lib/picture");
    shrinkMock.mockRejectedValue(new PictureError("Roost could not read that picture. Try another one."));
    render(<AvatarEditor bot={makeBot()} onChange={vi.fn()} />);
    await userEvent.upload(screen.getByLabelText("Upload a picture"), PNG);
    expect(await screen.findByRole("alert")).toHaveTextContent("Roost could not read that picture. Try another one.");
    expect(uploadPictureMock).not.toHaveBeenCalled();
  });

  it("shows the gateway's refusal of a picture", async () => {
    const { ApiError } = await import("../src/api/client");
    shrinkMock.mockResolvedValue(new Blob(["x"], { type: "image/webp" }));
    uploadPictureMock.mockRejectedValue(new ApiError(413, "That picture is too big (512 KB at most). Try a smaller one."));
    render(<AvatarEditor bot={makeBot()} onChange={vi.fn()} />);
    await userEvent.upload(screen.getByLabelText("Upload a picture"), PNG);
    expect(await screen.findByRole("alert")).toHaveTextContent("That picture is too big");
  });
});
```

`web/tests/RobotFace.test.tsx`. Find:

```tsx
  it("is still when asked: no animation runs", () => {
```

Replace with:

```tsx
  it("shows the bot's own picture on its screen, in place of the signal", () => {
    const { container } = render(<RobotFace head="monitor" color="#3b82f6" picture="/api/bots/b1/picture?v=0123456789ab" />);
    const picture = container.querySelector("image.robot__picture");
    expect(picture?.getAttribute("href")).toBe("/api/bots/b1/picture?v=0123456789ab");
    expect(picture?.getAttribute("clip-path")).toMatch(/^url\(#robot-screen-/);
    expect(container.querySelector(".robot__signal")).toBeNull();
  });

  it("is still when asked: no animation runs", () => {
```

`web/tests/BotForm.test.tsx`. Find:

```tsx
  it("a new bot wears the first colour no teammate wears", () => {
```

Replace with:

```tsx
  it("Surprise me changes the head and the colour, and a new bot has no Upload yet", async () => {
    const user = userEvent.setup();
    render(<BotForm submitLabel="Create bot" onSubmit={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: "Surprise me" }));
    expect(screen.getByRole("radio", { name: "Classic" })).not.toBeChecked();
    expect(screen.getByRole("radio", { name: "Violet" })).not.toBeChecked();
    expect(screen.queryByLabelText("Upload a picture")).not.toBeInTheDocument();
  });

  it("a new bot wears the first colour no teammate wears", () => {
```

`web/e2e/profile.spec.ts`. Find:

```ts
  // The radios are visually hidden (the bird or swatch is the target), hence force. Each pick
  // saves through a round trip (AvatarEditor) before the DOM reflects it, so click then await
  // the checked state as its own assertion rather than locator.check()'s single-shot verify.
  await detail.getByRole("radio", { name: "Egg" }).click({ force: true });
  await expect(detail.getByRole("radio", { name: "Egg" })).toBeChecked();
  await detail.getByRole("radio", { name: "Teal" }).click({ force: true });
  await expect(detail.getByRole("radio", { name: "Teal" })).toBeChecked();
```

Replace with:

```ts
  // The radios are visually hidden (the robot or swatch is the target), hence force. Each pick
  // saves through a round trip (AvatarEditor) before the DOM reflects it, so click then await
  // the checked state as its own assertion rather than locator.check()'s single-shot verify.
  await detail.getByRole("radio", { name: "Monitor" }).click({ force: true });
  await expect(detail.getByRole("radio", { name: "Monitor" })).toBeChecked();
  await detail.getByRole("radio", { name: "Teal" }).click({ force: true });
  await expect(detail.getByRole("radio", { name: "Teal" })).toBeChecked();
  await detail.getByRole("radio", { name: "Signals" }).click({ force: true });
  await expect(detail.getByRole("radio", { name: "Signals" })).toBeChecked();
```

`web/e2e/profile.spec.ts`. Find:

```ts
  expect(file.avatar).toEqual({ shape: "egg", color: "#14b8a6" });
```

Replace with:

```ts
  expect(file.avatar).toEqual({ shape: "monitor", color: "#14b8a6", screen: "signal" });
```

- [ ] **Step 4: Run them to see them fail**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_bot_picture.py tests/test_bot_store.py tests/test_bots_api.py tests/test_bot_look.py -q`
Expected: ERROR at collection: `ModuleNotFoundError: No module named 'roost.bots.picture'`.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && cd web && npx vitest run tests/picture.test.ts tests/AvatarEditor.test.tsx tests/RobotFace.test.tsx tests/BotForm.test.tsx`
Expected: FAIL, 4 files:
- `picture`, `AvatarEditor`: `Failed to resolve import "../src/lib/picture"`.
- `RobotFace`: `shows the bot's own picture on its screen, in place of the signal` (`expected undefined to be '/api/bots/b1/picture?v=0123456789ab'`).
- `BotForm`: `Surprise me changes the head and the colour, and a new bot has no Upload yet` (no "Surprise me").

- [ ] **Step 5: The gateway keeps a sealed picture**

Create `roost/bots/picture.py`:

```python
"""A bot's own picture (look & feel redesign P1, the avatar editor's Upload): a small PNG, JPEG or
WebP its robot shows on its screen. It is the user's content, so it is stored sealed (``enc:v2``,
AAD ``bots:avatar_picture``) inside the bot's avatar JSON: no schema change, and only the owner's key
opens it. The web shrinks a picture to 256 px before it uploads (``web/src/lib/picture.ts``)."""

from __future__ import annotations

import base64
import binascii
import hashlib
import logging
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag

from roost.constants import AVATAR_PICTURE_MAX_BYTES
from roost.crypto.encryption import decrypt, encrypt, user_aad

logger = logging.getLogger(__name__)

PICTURE_AAD = "bots:avatar_picture"
PICTURE_TAG_CHARS = 12
TOO_BIG_TEXT = f"That picture is too big ({AVATAR_PICTURE_MAX_BYTES // 1024} KB at most). Try a smaller one."
NOT_A_PICTURE_TEXT = "Upload a PNG, JPEG or WebP picture."
# What each kind of file starts with: the bytes say what a picture is, never its Content-Type alone.
_STARTS = (("image/png", b"\x89PNG\r\n\x1a\n"), ("image/jpeg", b"\xff\xd8\xff"))
_WEBP_RIFF, _WEBP_MARK = b"RIFF", b"WEBP"


class PictureTooBig(ValueError):
    """More than AVATAR_PICTURE_MAX_BYTES (HTTP 413)."""


class NotAPicture(ValueError):
    """Not a PNG, JPEG or WebP, or not what its Content-Type says (HTTP 415)."""


@dataclass(frozen=True)
class Picture:
    media_type: str
    data: bytes


def _kind(data: bytes) -> str | None:
    for media_type, start in _STARTS:
        if data.startswith(start):
            return media_type
    return "image/webp" if data[:4] == _WEBP_RIFF and data[8:12] == _WEBP_MARK else None


def read_picture(content_type: str, data: bytes) -> Picture:
    """The upload as a Picture. Raises PictureTooBig or NotAPicture with a sentence for the user."""
    if len(data) > AVATAR_PICTURE_MAX_BYTES:
        raise PictureTooBig(TOO_BIG_TEXT)
    kind = _kind(data)
    if kind is None or content_type.split(";")[0].strip().lower() != kind:
        raise NotAPicture(NOT_A_PICTURE_TEXT)
    return Picture(kind, data)


def seal_picture(picture: Picture, dek: bytes, user_id: str) -> str:
    payload = f"{picture.media_type};{base64.b64encode(picture.data).decode('ascii')}"
    return encrypt(payload, dek, user_aad(user_id, PICTURE_AAD))


def open_picture(sealed: str, dek: bytes, user_id: str) -> Picture | None:
    """None, logged, when a stored picture cannot be opened: the robot shows its screen instead."""
    try:
        media_type, encoded = decrypt(sealed, dek, user_aad(user_id, PICTURE_AAD)).split(";", 1)
        return Picture(media_type, base64.b64decode(encoded, validate=True))
    except (InvalidTag, ValueError, binascii.Error):
        logger.warning("A bot picture of user %s could not be opened", user_id, exc_info=True)
        return None


def picture_tag(sealed: str) -> str:
    """A short version for the picture's address, so a new picture is never shown from the cache."""
    return hashlib.sha256(sealed.encode("ascii")).hexdigest()[:PICTURE_TAG_CHARS]
```

`roost/constants.py`. Find:

```python
# S1 D3 (Ruling 29): the main bot creates at most this many new bots per request.
MAX_BOTS_CREATED_PER_RUN = 3
```

Replace with:

```python
# S1 D3 (Ruling 29): the main bot creates at most this many new bots per request.
MAX_BOTS_CREATED_PER_RUN = 3
# A bot's own picture on its robot's screen (redesign P1, the avatar editor's Upload). The web
# shrinks a picture to 256 px first, which is far under this.
AVATAR_PICTURE_MAX_BYTES = 512 * 1024
```

`roost/bots/models.py`. Find:

```python
    screen: AvatarScreen = "glow"  # the robot screen's signal style (redesign V1)
```

Replace with:

```python
    screen: AvatarScreen = "glow"  # the robot screen's signal style (redesign V1)
    picture: str | None = None  # the uploaded picture's version tag; the picture itself never rides on a Bot
```

`roost/bots/store.py`. Find:

```python
from roost.bots.models import Avatar, Bot, BotDraft, BotPatch, BotStatus, DuplicateBotName
```

Replace with:

```python
from roost.bots.models import Avatar, Bot, BotDraft, BotPatch, BotStatus, DuplicateBotName
from roost.bots.picture import Picture, open_picture, picture_tag, seal_picture
```

`roost/bots/store.py`. Find:

```python
_INSTRUCTIONS_AAD = "bots:instructions"
```

Replace with:

```python
_INSTRUCTIONS_AAD = "bots:instructions"
_PICTURE_KEY = "picture"   # in the avatar JSON: the sealed picture (roost/bots/picture.py)
```

`roost/bots/store.py`. Find:

```python
def _avatar_dump(avatar: Avatar) -> str:
    return json.dumps({"shape": avatar.shape, "color": avatar.color, "badge": avatar.badge, "screen": avatar.screen})


def _avatar_load(raw: str) -> Avatar:
    """An avatar stored before the robots has no screen: it shows the default style."""
    data = json.loads(raw)
    return Avatar(shape=data["shape"], color=data["color"], badge=data["badge"],
                  screen=data.get("screen", DEFAULT_ROBOT_SCREEN))
```

Replace with:

```python
def _avatar_dump(avatar: Avatar, sealed_picture: str | None = None) -> str:
    data = {"shape": avatar.shape, "color": avatar.color, "badge": avatar.badge, "screen": avatar.screen}
    return json.dumps(data if sealed_picture is None else {**data, _PICTURE_KEY: sealed_picture})


def _avatar_load(raw: str) -> Avatar:
    """An avatar stored before the robots has no screen: it shows the default style."""
    data = json.loads(raw)
    sealed = data.get(_PICTURE_KEY)
    return Avatar(shape=data["shape"], color=data["color"], badge=data["badge"],
                  screen=data.get("screen", DEFAULT_ROBOT_SCREEN), picture=picture_tag(sealed) if sealed else None)


async def _sealed_picture(db: aiosqlite.Connection, user_id: str, bot_id: str) -> str | None:
    row = await (await db.execute("SELECT avatar FROM bots WHERE id = ? AND user_id = ?", (bot_id, user_id))).fetchone()
    return None if row is None else json.loads(row["avatar"]).get(_PICTURE_KEY)
```

`roost/bots/store.py`. Find:

```python
        async with db_session(self._config) as db:
            try:
                cursor = await db.execute(
                    "UPDATE bots SET name = ?, name_key = ?, job = ?, instructions = ?, "
                    "avatar = ?, updated_at = ? WHERE id = ? AND user_id = ?",
                    (
                        encrypt(name, dek, user_aad(user_id, _NAME_AAD)),
                        _name_key(dek, name),
                        encrypt(job, dek, user_aad(user_id, _JOB_AAD)),
                        encrypt(instructions, dek, user_aad(user_id, _INSTRUCTIONS_AAD)),
                        _avatar_dump(avatar),
```

Replace with:

```python
        async with db_session(self._config) as db:
            kept = await _sealed_picture(db, user_id, bot_id)   # a new look keeps the bot's picture
            try:
                cursor = await db.execute(
                    "UPDATE bots SET name = ?, name_key = ?, job = ?, instructions = ?, "
                    "avatar = ?, updated_at = ? WHERE id = ? AND user_id = ?",
                    (
                        encrypt(name, dek, user_aad(user_id, _NAME_AAD)),
                        _name_key(dek, name),
                        encrypt(job, dek, user_aad(user_id, _JOB_AAD)),
                        encrypt(instructions, dek, user_aad(user_id, _INSTRUCTIONS_AAD)),
                        _avatar_dump(avatar, kept),
```

`roost/bots/store.py`. Find:

```python
        return dataclasses.replace(
            current, name=name, job=job, instructions=instructions, avatar=avatar, updated_at=now,
        )
```

Replace with:

```python
        return dataclasses.replace(
            current, name=name, job=job, instructions=instructions, updated_at=now,
            avatar=dataclasses.replace(avatar, picture=picture_tag(kept) if kept else None),
        )

    async def set_picture(self, user_id: str, bot_id: str, picture: Picture | None) -> Bot | None:
        """Put the bot's own picture on its screen, or take it off (``None``). The look stays."""
        current = await self.get(user_id, bot_id)
        if current is None:
            return None
        sealed = None if picture is None else seal_picture(picture, await get_user_dek(self._config, user_id), user_id)
        async with db_session(self._config) as db:
            await db.execute(
                "UPDATE bots SET avatar = ?, updated_at = ? WHERE id = ? AND user_id = ?",
                (_avatar_dump(current.avatar, sealed), _now_iso(), bot_id, user_id),
            )
            await db.commit()
        return await self.get(user_id, bot_id)

    async def get_picture(self, user_id: str, bot_id: str) -> Picture | None:
        async with db_session(self._config) as db:
            sealed = await _sealed_picture(db, user_id, bot_id)
        if sealed is None:
            return None
        return open_picture(sealed, await get_user_dek(self._config, user_id), user_id)
```

`roost/bots/service.py`. Find:

```python
        "avatar": avatar_dict(bot.avatar),
```

Replace with:

```python
        "avatar": {**avatar_dict(bot.avatar), "picture": _picture_url(bot)},
```

`roost/bots/service.py`. Find:

```python
def bot_out(bot: Bot, activity: str | None) -> dict[str, Any]:
```

Replace with:

```python
def _picture_url(bot: Bot) -> str | None:
    """Where the web reads the bot's picture (roost/gateway/routes/bot_picture.py), versioned by it."""
    return None if bot.avatar.picture is None else f"/api/bots/{bot.id}/picture?v={bot.avatar.picture}"


def bot_out(bot: Bot, activity: str | None) -> dict[str, Any]:
```

`roost/gateway/app.py`. Find:

```python
from roost.gateway.routes.bots import bots_router
```

Replace with:

```python
from roost.gateway.routes.bot_picture import bot_picture_router
from roost.gateway.routes.bots import bots_router
```

`roost/gateway/app.py`. Find:

```python
    app.include_router(bots_router)
```

Replace with:

```python
    app.include_router(bots_router)
    app.include_router(bot_picture_router)
```

Create `roost/gateway/routes/bot_picture.py`:

```python
"""A bot's own picture (look & feel redesign P1, the avatar editor's Upload): ``POST`` puts one on
its robot's screen, ``DELETE`` takes it off, ``GET`` serves it to the owner's pages. The body is the
raw image, like a PDF upload (``POST /api/documents/pdf``). Every change publishes ``bot_updated``."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response

from roost.bots.models import Bot
from roost.bots.picture import NotAPicture, Picture, PictureTooBig, TOO_BIG_TEXT, read_picture
from roost.bots.service import bot_out
from roost.constants import AVATAR_PICTURE_MAX_BYTES
from roost.gateway.deps import CurrentUser, RequireOrigin

bot_picture_router = APIRouter(prefix="/api/bots", tags=["bots"])
BOT_NOT_FOUND_TEXT = "Bot not found"
NO_PICTURE_TEXT = "This bot has no picture"
# The address carries the picture's version (?v=), so the browser may keep it for good.
PICTURE_HEADERS = {"Cache-Control": "private, max-age=31536000, immutable", "X-Content-Type-Options": "nosniff"}


async def _picture_body(request: Request) -> Picture:
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > AVATAR_PICTURE_MAX_BYTES:
        raise HTTPException(status_code=413, detail=TOO_BIG_TEXT)
    try:
        return read_picture(request.headers.get("content-type", ""), await request.body())
    except PictureTooBig as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except NotAPicture as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc


async def _changed(request: Request, user_id: str, bot: Bot | None) -> dict[str, Any]:
    if bot is None:
        raise HTTPException(status_code=404, detail=BOT_NOT_FOUND_TEXT)
    out = bot_out(bot, request.app.state.activity_board.get(bot.id))
    await request.app.state.events.publish(user_id, {"type": "bot_updated", "bot": out})
    return out


@bot_picture_router.post("/{bot_id}/picture", dependencies=[RequireOrigin])
async def upload_picture(bot_id: str, request: Request, user: CurrentUser):
    picture = await _picture_body(request)
    return await _changed(request, user.id, await request.app.state.bots.set_picture(user.id, bot_id, picture))


@bot_picture_router.delete("/{bot_id}/picture", dependencies=[RequireOrigin])
async def remove_picture(bot_id: str, request: Request, user: CurrentUser):
    return await _changed(request, user.id, await request.app.state.bots.set_picture(user.id, bot_id, None))


@bot_picture_router.get("/{bot_id}/picture")
async def get_picture(bot_id: str, request: Request, user: CurrentUser) -> Response:
    picture = await request.app.state.bots.get_picture(user.id, bot_id)
    if picture is None:
        raise HTTPException(status_code=404, detail=NO_PICTURE_TEXT)
    return Response(content=picture.data, media_type=picture.media_type, headers=PICTURE_HEADERS)
```

- [ ] **Step 6: The web sends and shows it**

`web/src/api/types.ts`. Find:

```ts
  badge: AvatarBadge;
  screen?: RobotScreen;
}
```

Replace with:

```ts
  badge: AvatarBadge;
  screen?: RobotScreen;
  picture?: string | null; // a bot's own picture (GET /api/bots/{id}/picture?v=…), shown on its screen
}
```

`web/src/api/bots.ts`. Find:

```ts
import { apiRequest } from "./client";
```

Replace with:

```ts
import { apiRequest, apiUpload } from "./client";
```

`web/src/api/bots.ts`. Find:

```ts
// The profile's Notifications switch (S1.10).
```

Replace with:

```ts
// A picture on the bot's screen (redesign P1): the raw image, like a PDF upload.
export function uploadPicture(botId: string, picture: Blob): Promise<BotOut> {
  return apiUpload<BotOut>(`/api/bots/${botId}/picture`, picture, picture.type);
}

export function removePicture(botId: string): Promise<BotOut> {
  return apiRequest<BotOut>("DELETE", `/api/bots/${botId}/picture`);
}

// The profile's Notifications switch (S1.10).
```

Create `web/src/lib/picture.ts`:

```ts
// A picture for a bot's screen (redesign P1, the avatar editor's Upload): any image the browser can
// read, cropped square from its middle and shrunk to PICTURE_SIDE px, so the upload stays far under
// the gateway's 512 KB (roost/constants.py AVATAR_PICTURE_MAX_BYTES).
export const PICTURE_SIDE = 256;
export const PICTURE_TYPE = "image/webp"; // a browser that cannot write WebP gives PNG instead
export const PICTURE_ACCEPT = "image/png,image/jpeg,image/webp,image/gif";
const PICTURE_QUALITY = 0.86;

export class PictureError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "PictureError";
  }
}

async function readImage(file: Blob): Promise<ImageBitmap> {
  if (!file.type.startsWith("image/")) throw new PictureError("That file is not a picture. Pick a PNG, JPEG or WebP.");
  try {
    return await createImageBitmap(file);
  } catch {
    throw new PictureError("Roost could not read that picture. Try another one.");
  }
}

export async function shrinkPicture(file: Blob): Promise<Blob> {
  const image = await readImage(file);
  const canvas = document.createElement("canvas");
  canvas.width = PICTURE_SIDE;
  canvas.height = PICTURE_SIDE;
  const context = canvas.getContext("2d");
  if (!context) throw new PictureError("This browser cannot resize pictures. Try another browser.");
  const side = Math.min(image.width, image.height);
  context.drawImage(image, (image.width - side) / 2, (image.height - side) / 2, side, side, 0, 0, PICTURE_SIDE, PICTURE_SIDE);
  image.close();
  const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, PICTURE_TYPE, PICTURE_QUALITY));
  if (!blob) throw new PictureError("Roost could not resize that picture. Try another one.");
  return blob;
}
```

`web/src/components/robot/RobotFace.tsx`. Find:

```tsx
import type { RobotHead, RobotScreen } from "../../api/types";
```

Replace with:

```tsx
import { useId } from "react";
import type { RobotHead, RobotScreen } from "../../api/types";
```

`web/src/components/robot/RobotFace.tsx`. Find:

```tsx
import { HEAD_SCREENS, RobotHeadShape } from "./heads";
```

Replace with:

```tsx
import { HEAD_SCREENS, RobotHeadShape, type ScreenBox } from "./heads";
```

`web/src/components/robot/RobotFace.tsx`. Find:

```tsx
  still?: boolean; // no motion: the user prefers reduced motion
  className?: string;
}
```

Replace with:

```tsx
  still?: boolean; // no motion: the user prefers reduced motion
  picture?: string | null; // the bot's own picture: it fills the screen in place of the signal
  className?: string;
}
```

`web/src/components/robot/RobotFace.tsx`. Find:

```tsx
// A Boxbot (redesign V1): its head in the bot's colour, a dark screen, and the screen's signal.
export function RobotFace({
  head, color, screen = ROBOT_SIGNAL_STYLE, moment = "rest", star = false, size = 96, title, still = false, className,
}: RobotFaceProps) {
```

Replace with:

```tsx
function ScreenPicture({ box, href }: { box: ScreenBox; href: string }) {
  const clip = `robot-screen-${useId().replace(/[^a-zA-Z0-9_-]/g, "")}`;
  return (
    <>
      <clipPath id={clip}>
        <rect x={box.x} y={box.y} width={box.width} height={box.height} rx={SCREEN_RADIUS} />
      </clipPath>
      <image className="robot__picture" href={href} x={box.x} y={box.y} width={box.width} height={box.height}
        preserveAspectRatio="xMidYMid slice" clipPath={`url(#${clip})`} />
    </>
  );
}

// A Boxbot (redesign V1): its head in the bot's colour, a dark screen, and the screen's signal, or
// the bot's own picture on the screen.
export function RobotFace({
  head, color, screen = ROBOT_SIGNAL_STYLE, moment = "rest", star = false, size = 96, title, still = false, picture = null,
  className,
}: RobotFaceProps) {
```

`web/src/components/robot/RobotFace.tsx`. Find:

```tsx
      <g transform={`translate(${box.x + box.width / 2} ${box.y + box.height / 2})`}
        style={{ filter: `drop-shadow(0 0 ${GLOW_PX}px ${ink})` }}>
        <RobotSignal style={screen} moment={moment} color={ink} />
      </g>
```

Replace with:

```tsx
      {picture ? <ScreenPicture box={box} href={picture} /> : (
        <g transform={`translate(${box.x + box.width / 2} ${box.y + box.height / 2})`}
          style={{ filter: `drop-shadow(0 0 ${GLOW_PX}px ${ink})` }}>
          <RobotSignal style={screen} moment={moment} color={ink} />
        </g>
      )}
```

`web/src/components/Avatar.tsx`. Find:

```tsx
        moment={moment ?? STATUS_MOMENT[status]} star={star} size={size} still={reducedMotion}
```

Replace with:

```tsx
        moment={moment ?? STATUS_MOMENT[status]} star={star} size={size} still={reducedMotion} picture={avatar.picture}
```

- [ ] **Step 7: The editor**

`web/src/components/icons.tsx`. Find:

```tsx
export function CalendarIcon() {
```

Replace with:

```tsx
export function UploadIcon() {
  return <Icon><path d="M10 13V3M6 7l4-4 4 4M4 13v3h12v-3" /></Icon>;
}

export function SparkIcon() {
  return <Icon><path d="M10 2.5l1.8 5.7 5.7 1.8-5.7 1.8-1.8 5.7-1.8-5.7-5.7-1.8 5.7-1.8z" /></Icon>;
}

export function CalendarIcon() {
```

`web/src/components/AvatarPicker.tsx`. Find:

```tsx
import { ROBOT_HEADS, ROBOT_HEAD_LABELS, robotHead } from "./robot/look";
```

Replace with:

```tsx
import { ROBOT_HEADS, ROBOT_HEAD_LABELS, ROBOT_SCREENS, ROBOT_SCREEN_LABELS, robotHead, robotScreen } from "./robot/look";
```

`web/src/components/AvatarPicker.tsx`. Find:

```tsx
// The six robot heads and twelve colours (redesign V1). A pick keeps the screen style and drops any
// old badge: every bot has every tool.
```

Replace with:

```tsx
// The six robot heads, twelve colours and three screen styles (redesign V1). A pick changes one of
// them and drops any old badge: every bot has every tool.
```

`web/src/components/AvatarPicker.tsx`. Find:

```tsx
  const head = robotHead(value.shape);
```

Replace with:

```tsx
  const head = robotHead(value.shape);
  const screen = robotScreen(value.screen);
```

`web/src/components/AvatarPicker.tsx`. Find:

```tsx
          </label>
        ))}
      </fieldset>
    </div>
  );
}
```

Replace with:

```tsx
          </label>
        ))}
      </fieldset>
      <fieldset className="avatar-picker__screens">
        <legend className="field__label">Screen</legend>
        {ROBOT_SCREENS.map((style) => (
          <label key={style} className="avatar-picker__screen">
            <input type="radio" name={`${group}-screen`} className="sr-only" checked={screen === style}
              onChange={() => onChange({ ...value, screen: style, badge: "none" })} />
            <Avatar avatar={{ ...value, screen: style, picture: null }} status="on_it" size={40} label={false} decorative />
            <span className="avatar-picker__screen-name">{ROBOT_SCREEN_LABELS[style]}</span>
          </label>
        ))}
      </fieldset>
    </div>
  );
}
```

Create `web/src/components/avatar/AvatarStudio.tsx`:

```tsx
import { Avatar } from "../Avatar";
import { AvatarPicker } from "../AvatarPicker";
import { SparkIcon, UploadIcon } from "../icons";
import { robotHead, robotScreen } from "../robot/look";
import { surpriseLook } from "../robot/palette";
import { Button } from "../../ui/Button";
import { PICTURE_ACCEPT } from "../../lib/picture";
import type { AvatarOut, BotStatus } from "../../api/types";

export interface AvatarStudioProps {
  value: AvatarOut; // the look shown, with its picture when it has one
  onChange: (avatar: AvatarOut) => void;
  status?: BotStatus; // the preview shows this status's signal (the bot's own on its profile)
  star?: boolean;
  preview?: boolean; // the big live preview (the New bot form has its own)
  onUpload?: (file: File) => void; // given: Upload a picture (the bot must exist first)
  onRemovePicture?: () => void; // given, with a picture: Remove picture
  busy?: boolean;
}

function PictureButtons({ hasPicture, busy, onUpload, onRemove }: {
  hasPicture: boolean; busy: boolean; onUpload: (file: File) => void; onRemove?: () => void;
}) {
  return (
    <>
      <label className="btn btn--secondary btn--sm avatar-studio__upload" aria-disabled={busy || undefined}>
        <UploadIcon /> Upload a picture
        <input type="file" accept={PICTURE_ACCEPT} className="sr-only" aria-label="Upload a picture" disabled={busy}
          onChange={(event) => { const file = event.target.files?.[0]; event.target.value = ""; if (file) onUpload(file); }} />
      </label>
      {hasPicture && onRemove ? <Button variant="ghost" size="sm" disabled={busy} onClick={onRemove}>Remove picture</Button> : null}
    </>
  );
}

// The avatar editor (redesign P1): a big live preview showing the bot's status, its head, colour and
// screen style, Surprise me, and a picture of its own for its screen.
export function AvatarStudio({
  value, onChange, status = "resting", star = false, preview = true, onUpload, onRemovePicture, busy = false,
}: AvatarStudioProps) {
  const surprise = () => {
    const next = surpriseLook({ head: robotHead(value.shape), color: value.color, screen: robotScreen(value.screen) });
    onChange({ ...value, shape: next.head, color: next.color, screen: next.screen, badge: "none" });
  };
  return (
    <div className="avatar-studio">
      {preview ? (
        <div className="avatar-studio__preview" aria-label="Preview" role="group">
          <Avatar avatar={value} status={status} star={star} size={160} />
        </div>
      ) : null}
      <div className="avatar-studio__controls">
        <AvatarPicker value={value} onChange={onChange} />
        <div className="avatar-studio__actions">
          <Button size="sm" disabled={busy} onClick={surprise}><SparkIcon /> Surprise me</Button>
          {onUpload ? (
            <PictureButtons hasPicture={Boolean(value.picture)} busy={busy} onUpload={onUpload} onRemove={onRemovePicture} />
          ) : null}
        </div>
      </div>
    </div>
  );
}
```

Replace the whole of `web/src/components/profile/AvatarEditor.tsx` with:

```tsx
import { useState } from "react";
import { AvatarStudio } from "../avatar/AvatarStudio";
import { ErrorNotice } from "../ErrorNotice";
import { useTemplates } from "../../hooks/useTemplates";
import { DEFAULT_ROBOT_HEAD, ROBOT_SIGNAL_STYLE, lookOf } from "../robot/look";
import { BOT_DEFAULT_COLORS } from "../robot/palette";
import { PictureError, shrinkPicture } from "../../lib/picture";
import * as botsApi from "../../api/bots";
import { describeError } from "../../api/client";
import type { AvatarOut, BotOut } from "../../api/types";

const PLAIN_LOOK: AvatarOut = { shape: DEFAULT_ROBOT_HEAD, color: BOT_DEFAULT_COLORS[0], badge: "none", screen: ROBOT_SIGNAL_STYLE };

function useBotChange(onChange: (bot: BotOut) => void) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const run = async (change: () => Promise<BotOut>) => {
    setBusy(true);
    setError(null);
    try {
      onChange(await change());
    } catch (err) {
      setError(err instanceof PictureError ? err.message : describeError(err));
    } finally {
      setBusy(false);
    }
  };
  return { busy, error, run };
}

// The profile's look editor (S1.6, redesign P1): a pick saves at once; Reset goes back to the bot's
// template look (or the plain violet classic robot). Upload puts a picture on its screen.
export function AvatarEditor({ bot, onChange }: { bot: BotOut; onChange: (bot: BotOut) => void }) {
  const { templates } = useTemplates();
  const { busy, error, run } = useBotChange(onChange);
  const defaultLook = templates.find((t) => t.id === bot.template_id)?.avatar ?? PLAIN_LOOK;
  const save = (avatar: AvatarOut) => run(() => botsApi.updateBot(bot.id, { avatar: lookOf(avatar) }));
  const upload = (file: File) => run(async () => botsApi.uploadPicture(bot.id, await shrinkPicture(file)));
  return (
    <section className="info-card avatar-editor" aria-labelledby="look-title">
      <div className="avatar-editor__head">
        <h2 id="look-title" className="info-card__title">Look</h2>
        <button type="button" className="btn btn--quiet btn--small" onClick={() => void save(defaultLook)}>Reset to default</button>
      </div>
      <AvatarStudio value={bot.avatar} status={bot.status} star={bot.is_primary} busy={busy}
        onChange={(avatar) => void save(avatar)} onUpload={(file) => void upload(file)}
        onRemovePicture={() => void run(() => botsApi.removePicture(bot.id))} />
      <p className="avatar-editor__caption">How this bot looks everywhere. A picture shows on its screen.</p>
      {error ? <ErrorNotice message={error} /> : null}
    </section>
  );
}
```

`web/src/components/BotForm.tsx`. Find:

```tsx
import { AvatarPicker } from "./AvatarPicker";
```

Replace with:

```tsx
import { AvatarStudio } from "./avatar/AvatarStudio";
```

`web/src/components/BotForm.tsx`. Find:

```tsx
        <AvatarPicker value={values.avatar} onChange={(avatar) => set({ avatar })} />
```

Replace with:

```tsx
        <AvatarStudio value={values.avatar} preview={false} onChange={(avatar) => set({ avatar })} />
```

Create `web/src/styles/avatar-studio.css`:

```css
/* ---------------------------------------------------------------------
   The avatar editor (redesign P1): a big live preview beside the head,
   colour and screen pickers, Surprise me and the picture buttons.
   --------------------------------------------------------------------- */

.avatar-studio {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: var(--space-6);
  align-items: start;
}

.avatar-studio__preview {
  display: grid;
  place-items: center;
  padding: var(--space-4);
  border-radius: var(--radius-lg);
  background: var(--color-bg);
}

.avatar-studio__controls {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  min-width: 0;
}

.avatar-studio__actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.avatar-studio__upload {
  cursor: pointer;
}

.avatar-studio__upload[aria-disabled="true"] {
  opacity: 0.5;
  cursor: not-allowed;
}

.avatar-picker__screens {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.avatar-picker__screen {
  position: relative;
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-1) var(--space-3) var(--space-1) var(--space-1);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-raised);
  color: var(--color-text-secondary);
  font-size: var(--fs-label);
  cursor: pointer;
}

/* As with the swatches (profile.css), the visually hidden radio sits in the middle of its label, so
   a click on its spot always lands on the label, wherever the layout moves it. */
.avatar-picker__screen input.sr-only {
  inset: 0;
  margin: auto;
}

.avatar-picker__screen:has(input:checked) {
  border-color: var(--color-accent);
  background: var(--color-accent-tint);
  color: var(--color-text);
}

.avatar-picker__screen:has(input:focus-visible) {
  outline: 2px solid var(--color-accent-strong);
  outline-offset: 2px;
}

@media (max-width: 768px) {
  .avatar-studio {
    grid-template-columns: minmax(0, 1fr);
  }
}
```

`web/src/styles.css`. Find:

```css
@import "./styles/profile.css";
```

Replace with:

```css
@import "./styles/profile.css";
@import "./styles/avatar-studio.css";
```

- [ ] **Step 8: Run the tests to see them pass**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_bot_picture.py tests/test_bot_store.py tests/test_bots_api.py tests/test_bot_look.py tests/test_template_file.py -q`
Expected: PASS (`test_bot_picture` has 7 tests).

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && cd web && npx vitest run tests/picture.test.ts tests/AvatarEditor.test.tsx tests/RobotFace.test.tsx tests/BotForm.test.tsx tests/Profile.test.tsx tests/NewBot.test.tsx`
Expected: PASS: `picture` 3, `AvatarEditor` 9, `RobotFace` 8 and `BotForm` 8 tests; `Profile` and `NewBot` unchanged.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && cd web && npm test && npm run build && npm run size`
Expected: every test file passes, the build succeeds, the entry chunk is within the budget.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && df -g /System/Volumes/Data | awk 'NR==2{print $4}'`
Expected: at least 8. Otherwise stop and report.

Run this as one shell call (`computer.spec` makes Scout; `profile.spec` now picks Monitor, Teal and Signals and checks the shared file):

```bash
cd /Users/blckit/Desktop/Code_Projects/roost && cd web && \
port=18800 && if curl -fsS -o /dev/null --max-time 2 http://127.0.0.1:18800/api/health; then port=5173; fi && \
npm run build && ROOST_E2E_PORT=$port npx playwright test e2e/computer.spec.ts e2e/profile.spec.ts
```

Expected: 2 passed.

- [ ] **Step 9: Commit**

Run:

```bash
cd /Users/blckit/Desktop/Code_Projects/roost && \
git add roost/constants.py roost/bots/models.py roost/bots/picture.py roost/bots/store.py roost/bots/service.py \
  roost/gateway/routes/bot_picture.py roost/gateway/app.py tests/test_bot_picture.py tests/test_bot_store.py \
  tests/test_bots_api.py tests/test_bot_look.py web/src/api/types.ts web/src/api/bots.ts web/src/lib/picture.ts \
  web/src/components/icons.tsx web/src/components/robot/RobotFace.tsx web/src/components/Avatar.tsx \
  web/src/components/AvatarPicker.tsx web/src/components/avatar/AvatarStudio.tsx \
  web/src/components/profile/AvatarEditor.tsx web/src/components/BotForm.tsx web/src/styles.css \
  web/src/styles/avatar-studio.css web/tests/picture.test.ts web/tests/AvatarEditor.test.tsx \
  web/tests/RobotFace.test.tsx web/tests/BotForm.test.tsx web/e2e/profile.spec.ts && \
git commit -m "feat: the avatar editor (Head, Colour, Screen, Surprise me) and a bot's own picture on its screen"
```

### Task 7: E2E for the editor and the pickers, the docs, and the final checks

The design's testing list ("edit an avatar"; the pickers) and the docs. Tasks 1–6 built and unit-tested everything; this task proves it in a real browser, records it in CLAUDE.md, and runs every gate once more.
- **`web/e2e/look.spec.ts`** opens Scout's profile: the preview shows Scout's status, Surprise me saves a new head, Pixel icons switches the screen, a real PNG goes through the browser's shrink and the upload and shows on the screen (and the address serves an image), and Remove picture brings the signal back.
- **`web/e2e/pickers.spec.ts`** runs the browser on `America/Los_Angeles` (Review Focus 2): a task due Tomorrow at 09:00 is sent as Madrid's `{tomorrow} 09:00` and comes back in the edit form the same; a project start typed as "tomorrow" is read by the gateway and saved as Madrid's day; an expense's Yesterday is Madrid's yesterday. The expected days come from the web's own `todayIn` and `addDays` (and the project page's `dateLabel`), on Madrid time, so the spec does no date maths of its own.
- **Spec order** (alphabetical, one worker): `computer`, `every-bot`, `look`, `main-bot`, `pickers`, `profile`, `projects`, `records`, `stuck`, `team`. `look` needs Scout (`computer`); `profile` sets its own head, colour and screen afterwards, so nothing leaks. `pickers` leaves a "Water the plants" task, a "Garden plan" project and a 9.90 EUR "Seeds" expense in General; no later spec counts tasks, projects or General's expenses.
- **Docs.** The CLAUDE.md Documentation Map gains the design and this plan (after the projects hub's lines); the Architecture section gains one paragraph on where the look lives. `tests/test_docs.py` pins both, and its existing check keeps every map entry pointing at a file that exists (this plan is committed in this task for that reason).

**Files:**
- Create: `web/e2e/look.spec.ts`, `web/e2e/pickers.spec.ts`
- Modify: `CLAUDE.md`, `tests/test_docs.py`
- Commit also: `docs/plans/2026-10-15-roost-redesign-p1-foundation.md` (this plan, untracked until now)
- Test: the two specs, `tests/test_docs.py`, and every suite once more

**Interfaces:**
- Consumes: the accessible names under Task 4's and Task 6's "Produces"; `signIn`, `openChat`, `openBoard`, `detailPane` (`web/e2e/helpers.ts`); `todayIn`, `addDays` (`web/src/ui/date/dates.ts`); `dateLabel` (`web/src/components/projects/projects.ts`); `formatDueChip` is not used (its labels follow the browser's zone).
- Produces: `tests/test_docs.py` `REDESIGN_DOCS` and `LOOK_PLACES`, so the later steps' docs keep pointing at real files. No code interface.

- [ ] **Step 1: Path guard**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && git -C /Users/blckit/Desktop/Code_Projects/roost rev-parse --show-toplevel && git -C /Users/blckit/Desktop/Code_Projects/roost branch --show-current`
Expected: `/Users/blckit/Desktop/Code_Projects/roost` then `night-1`. If either differs, stop.

Then confirm Task 6 has landed and this task has not:

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && test -f web/src/components/avatar/AvatarStudio.tsx && test ! -f web/e2e/look.spec.ts && grep -c "roost-redesign-p1" CLAUDE.md`
Expected: `0`. Otherwise stop.

Then check that the names the specs use are in the code:

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && for text in '"Open calendar"' 'Pick a day and a time' '"Tomorrow"' '"Yesterday"' '"09:00"' 'date-field__preview--' 'label="When"' 'label="Due"' 'label="Starts"' 'label="Day"' 'Surprise me' 'Remove picture' 'Upload a picture' 'aria-label="Preview"' 'robot__picture' 'Pixel icons'; do grep -rqF -- "$text" web/src || echo "missing: $text"; done`
Expected: no output. If something is listed, stop and reconcile Tasks 4–6 with their "Produces" before writing the specs. Never loosen a spec to fit.

- [ ] **Step 2: Write the specs and the docs test**

Create `web/e2e/look.spec.ts`:

```ts
import { expect, test } from "@playwright/test";
import { detailPane, openChat, signIn } from "./helpers";

// The avatar editor (redesign P1): Surprise me, a screen style, and Scout's own picture on its
// robot's screen. computer.spec (earlier, alphabetically) made Scout; profile.spec (later) picks
// its own head, colour and screen, so nothing here leaks into it.
const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==", "base64");
const PICTURE_URL = /^\/api\/bots\/[^/]+\/picture\?v=[0-9a-f]{12}$/;

test("the avatar editor: Surprise me, a screen style, and Scout's own picture on its screen", async ({ page }) => {
  await signIn(page);
  await openChat(page, "Scout");
  const detail = detailPane(page);
  await detail.getByRole("link", { name: "Open Scout's profile" }).click();
  const robot = detail.getByRole("group", { name: "Preview" }).locator("svg.avatar");
  await expect(robot).toHaveAttribute("data-moment", "rest"); // the preview shows Scout's own status

  const before = await robot.getAttribute("data-head");
  const surprised = page.waitForResponse((r) => /\/api\/bots\/[^/]+$/.test(r.url()) && r.request().method() === "PATCH");
  await detail.getByRole("button", { name: "Surprise me" }).click();
  expect((await surprised).ok()).toBe(true);
  await expect(robot).not.toHaveAttribute("data-head", before ?? "");

  await detail.getByRole("radio", { name: "Pixel icons" }).click({ force: true });
  await expect(detail.getByRole("radio", { name: "Pixel icons" })).toBeChecked();
  await expect(robot).toHaveAttribute("data-screen", "pixel");

  const uploaded = page.waitForResponse((r) => r.url().endsWith("/picture") && r.request().method() === "POST");
  await detail.getByLabel("Upload a picture").setInputFiles({ name: "scout.png", mimeType: "image/png", buffer: PNG });
  expect((await uploaded).status()).toBe(200);
  const picture = robot.locator("image.robot__picture");
  await expect(picture).toHaveAttribute("href", PICTURE_URL);
  const served = await page.request.get((await picture.getAttribute("href"))!);
  expect(served.status()).toBe(200);
  expect(served.headers()["content-type"]).toMatch(/^image\/(webp|png)$/); // shrunk in the browser first

  await detail.getByRole("button", { name: "Remove picture" }).click();
  await expect(robot.locator("image.robot__picture")).toHaveCount(0);
  await expect(robot.locator(".robot__signal--pixel")).toHaveCount(1);
});
```

Create `web/e2e/pickers.spec.ts`:

```ts
import { expect, test } from "@playwright/test";
import { dateLabel } from "../src/components/projects/projects";
import { addDays, todayIn } from "../src/ui/date/dates";
import { detailPane, openBoard, signIn } from "./helpers";

// The date pickers (redesign P1), from a browser far from Madrid: every pick must still be Madrid's
// day and Madrid's clock. The expected days come from the same helpers the web uses, on Madrid time.
test.use({ timezoneId: "America/Los_Angeles" });

const TASK = "Water the plants";
const PROJECT = "Garden plan";

test("a task due at a picked day and time, a project start typed in words, an expense's day from the calendar", async ({ page }) => {
  test.setTimeout(60_000);
  const today = todayIn();
  const tomorrow = addDays(today, 1);
  await signIn(page);
  await openBoard(page);
  const detail = detailPane(page);

  // A task: Tomorrow and 09:00 go out as Madrid's day and wall time, and come back the same.
  await detail.getByRole("tab", { name: "Tasks" }).click();
  await detail.getByLabel("New task").fill(TASK);
  await detail.getByRole("button", { name: "Open calendar" }).click();
  await page.getByRole("button", { name: "Tomorrow", exact: true }).click();
  await page.getByRole("button", { name: "09:00", exact: true }).click();
  await expect(detail.getByLabel("When")).toHaveValue(`${tomorrow} 09:00`);
  const added = page.waitForRequest((r) => r.url().endsWith("/api/tasks") && r.method() === "POST");
  await detail.getByRole("button", { name: "Add", exact: true }).click();
  expect((await added).postDataJSON()).toMatchObject({ title: TASK, due_date: `${tomorrow} 09:00` });
  const row = detail.getByRole("listitem").filter({ hasText: TASK });
  await row.getByRole("button", { name: "Edit" }).click();
  await expect(detail.getByRole("form", { name: `Edit ${TASK}` }).getByLabel("Due")).toHaveValue(`${tomorrow} 09:00`);
  await detail.getByRole("button", { name: "Cancel" }).click();

  // A project: "tomorrow", typed, is read by the gateway and saved as Madrid's day.
  await detail.getByRole("tab", { name: "Projects" }).click();
  await detail.getByRole("button", { name: "New project", exact: true }).click();
  const form = detail.getByRole("form", { name: "New project", exact: true });
  await form.getByLabel("Name", { exact: true }).fill(PROJECT);
  await form.getByLabel("Starts", { exact: true }).fill("tomorrow");
  await expect(form.locator(".date-field__preview--read")).toHaveCount(1);
  await form.getByRole("button", { name: "Create project", exact: true }).click();
  await expect(form).toHaveCount(0);
  await detail.getByRole("list", { name: "Your projects" }).getByRole("link", { name: PROJECT, exact: true }).click();
  await expect(detail.getByText(`Starts ${dateLabel(tomorrow)}`)).toBeVisible();

  // An expense: Yesterday on the calendar is Madrid's yesterday.
  await openBoard(page);
  await detail.getByRole("tab", { name: "Money" }).click();
  await detail.getByRole("textbox", { name: "Amount", exact: true }).fill("9,90");
  await detail.getByRole("textbox", { name: "Note", exact: true }).fill("Seeds");
  await detail.getByRole("button", { name: "Open calendar" }).click();
  await page.getByRole("button", { name: "Yesterday", exact: true }).click();
  const logged = page.waitForRequest((r) => r.url().endsWith("/api/money/expenses") && r.method() === "POST");
  await detail.getByRole("button", { name: "Add expense", exact: true }).click();
  expect((await logged).postDataJSON()).toMatchObject({ amount: "9.90", spent_at: addDays(today, -1) });
});
```

`tests/test_docs.py`. Find:

```python
HUB_DOCS = (
    "docs/plans/2026-10-14-roost-projects-hub-design.md",
    "docs/plans/2026-10-14-roost-projects-hub.md",
)
```

Replace with:

```python
HUB_DOCS = (
    "docs/plans/2026-10-14-roost-projects-hub-design.md",
    "docs/plans/2026-10-14-roost-projects-hub.md",
)
REDESIGN_DOCS = (
    "docs/plans/2026-10-15-roost-look-and-feel-design.md",
    "docs/plans/2026-10-15-roost-redesign-p1-foundation.md",
)
LOOK_PLACES = ("web/src/styles/tokens.css", "web/src/ui/", "web/src/components/robot/", "/api/bots/{id}/picture")
```

`tests/test_docs.py`. Find:

```python
def test_every_file_on_the_documentation_map_exists():
```

Replace with:

```python
def test_the_documentation_map_names_the_redesign_design_and_its_p1_plan():
    assert [path for path in REDESIGN_DOCS if path not in _map_paths()] == []


def test_the_architecture_section_says_where_the_look_lives():
    architecture = _section(CLAUDE_MD.read_text(encoding="utf-8"), ARCHITECTURE_HEADING)
    assert [place for place in LOOK_PLACES if place not in architecture] == []


def test_every_file_on_the_documentation_map_exists():
```

- [ ] **Step 3: Run them to see them fail**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_docs.py -q`
Expected: FAIL, 2 failed and 4 passed: `test_the_documentation_map_names_the_redesign_design_and_its_p1_plan` and `test_the_architecture_section_says_where_the_look_lives`.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && df -g /System/Volumes/Data | awk 'NR==2{print $4}'`
Expected: at least 8. Otherwise stop and report.

Run this as one shell call:

```bash
cd /Users/blckit/Desktop/Code_Projects/roost && cd web && \
port=18800 && if curl -fsS -o /dev/null --max-time 2 http://127.0.0.1:18800/api/health; then port=5173; fi && \
npm run build && ROOST_E2E_PORT=$port npx playwright test e2e/computer.spec.ts e2e/look.spec.ts e2e/pickers.spec.ts
```

Expected: 3 passed. These specs add no code: they are new coverage of Tasks 4–6. If one fails:
- **A name is not found**: check it against Step 1's list and the task that produces it; fix the component, never the spec.
- **A day is off by one**: the picker or a form used the browser's zone (`new Date()`'s local fields, or `toISOString()` on a local midnight). Only `todayIn` reads the clock, and only on Madrid time.
- **The picture never shows**: check the POST's status (413 or 415 means the shrink did not run or wrote another type) and that `bot_out` carries `picture`.

- [ ] **Step 4: The docs**

`CLAUDE.md`. Find:

```markdown
- `docs/plans/2026-10-14-roost-projects-hub.md` — the projects hub plan: Category becomes Project, schema v13, `roost/projects/` (`numbers.py`, `ProjectService`, the project tools), the `/api/projects` and top-up routes, and the Board's Projects tab with a page per project.
```

Replace with:

```markdown
- `docs/plans/2026-10-14-roost-projects-hub.md` — the projects hub plan: Category becomes Project, schema v13, `roost/projects/` (`numbers.py`, `ProjectService`, the project tools), the `/api/projects` and top-up routes, and the Board's Projects tab with a page per project.
- `docs/plans/2026-10-15-roost-look-and-feel-design.md` — the look & feel redesign design: Boxbot robot avatars with three screen styles (V1), canvas (V2), the build order P1–P5 (V3), dark only (V4), and what each step holds.
- `docs/plans/2026-10-15-roost-redesign-p1-foundation.md` — the redesign's P1 plan: `tokens.css` and its guard test, the `web/src/ui/` kit (Radix menus, selects, tabs, sheets, popovers; Madrid date pickers with a lazy calendar), robot avatars and the avatar editor, `/api/dates/parse` and `/api/bots/{id}/picture`.
```

`CLAUDE.md`. Find:

```markdown
Every bot has the project tools. The Board's first tab, Projects, opens a page per project at `/board/projects/:projectId`.
```

Replace with:

```markdown
Every bot has the project tools. The Board's first tab, Projects, opens a page per project at `/board/projects/:projectId`.

The web's look (redesign P1): `web/src/styles/tokens.css` is the one place for colours, font sizes and the other design values (`web/tests/tokens.test.ts` refuses a hard-coded colour or font size anywhere else and keeps every text colour at 4.5:1), and `web/src/ui/` is the kit every screen builds from: buttons and fields, Radix Select, Menu, Tabs, Sheet, Popover and Tooltip, Toast, and the DatePicker and DateTimePicker, whose calendar is a lazy chunk and whose days and times are Madrid's (typed words are read by `GET /api/dates/parse`). Every bot is a robot (`web/src/components/robot/`): one of six heads in its colour, with a screen in one of three styles that shows its status; old bird shapes still draw, through one table in `look.ts`. A picture the user uploads (`/api/bots/{id}/picture`) shows on the robot's screen and is stored sealed in the avatar JSON.
```

- [ ] **Step 5: Full verification**

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest tests/test_docs.py tests/test_vocabulary.py -q`
Expected: PASS (`test_docs` has 6 tests).

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest -q`
Expected: PASS, the whole suite.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && uv run pytest --cov=roost --cov-fail-under=80`
Expected: PASS, with `Required test coverage of 80% reached`.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && cd web && npm test && npm run build && npm run size`
Expected:
- every vitest file passes, the licence gate (`licenseGate.test.ts`, 4 tests) and the token guard (`tokens.test.ts`, 7 tests) included;
- the build succeeds and lists the `Calendar-*` chunk apart from the entry;
- the size check prints the entry within `bundle-budget.json` (about 199 KB gzip of 257 KB when this plan was replayed).

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && df -g /System/Volumes/Data | awk 'NR==2{print $4}'`
Expected: at least 8. Otherwise stop and report.

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && make e2e`
Expected: every spec passes: `computer`, `every-bot`, `look`, `main-bot`, `pickers`, `profile`, `projects`, `records`, `stuck` and `team`. `make e2e` picks port 5173 when the live gateway holds 18800, and never touches `~/Roost/data`.

- [ ] **Step 6: Commit**

This plan is untracked until now; the design and the sketch are already committed. The new map line must never point at an uncommitted file.

Run:

```bash
cd /Users/blckit/Desktop/Code_Projects/roost && \
git add web/e2e/look.spec.ts web/e2e/pickers.spec.ts CLAUDE.md tests/test_docs.py \
  docs/plans/2026-10-15-roost-redesign-p1-foundation.md && \
git commit -m "test: E2E for the avatar editor and the date pickers; docs: the redesign's P1 in CLAUDE.md"
```

Run: `cd /Users/blckit/Desktop/Code_Projects/roost && git status --short`
Expected: none of the five files above is listed.
