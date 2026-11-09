# App restructure and polish (web + phone)

Owner decisions, 2026-10-23, after the first day on the phone app ("the bot control is brilliant; the rest needs
polish and fewer places"). Built in small slices; each slice is shown to the owner before the next starts. The web
and the phone app change together unless a slice says otherwise.

- **R1. The phone reaches Roost over Tailscale.** `tailscale serve` on the Mac proxies
  `https://<mac>.<tailnet>.ts.net` (tailnet only, never Funnel) to `127.0.0.1:18800`; Roost still binds 127.0.0.1
  only. The origin is allowed through `ROOST_EXTRA_ORIGINS` (`.env`, not committed). USB with `adb reverse` stays
  as the fallback. This replaces the mobile plan's "plain HTTP only to 127.0.0.1" for the tailnet address
  (HTTPS only there; cleartext stays limited to 127.0.0.1 and localhost). The live screen
  (`WS /api/bots/{id}/live`) still refuses forwarded sockets, except the phone through `tailscale serve`: only
  `X-Forwarded-For`, every hop a Tailscale address (`LIVE_TAILNET_NETWORKS`), and an Origin from
  `ROOST_EXTRA_ORIGINS` (`config.tailnet_origins`). Funnel or any other proxy still gets 4403.
- **R2. Fewer places.** Tasks, Projects and Money become one place: a project holds its tasks and its money, and the
  Tasks views (List · Kanban · Calendar) stay. Notes and Documents become one small, optional Notes tab, which later
  also shows the owner's Obsidian notes.
- **R3. A shorter bot profile.** Routines move into Plan; Computer sits in the middle; model, effort, approval mode
  and the other settings go to the end. The owner's Grok screenshots set the final layout.
- **R4. Calm, polished screens.** Fields and menus get a design pass; TaskForge (the owner's screenshots, ideas
  only, never its code or assets) is the reference for Tasks and Calendar.
- **R5. Phone app basics.** A Settings screen (gateway address, accent colour, sign out, version), a clear "Your Mac
  is offline" screen, a small floating + for a new task, Roost's own app icon, and an update check inside the app.

## Design direction (owner's screenshots, 2026-10-23)

The screenshots live in `docs/design/reference/` (git-ignored: other apps' screens and personal details). Ideas
only: never another app's code, icons, artwork or text. Our bots stay Lensbots.

- **Home (Grok):** your initials top-left (Settings), + top-right; the bots row; chats under group labels; one bottom
  bar: a grid button (the workspace) and a search pill.
- **Bot profile (Grok):** no tabs. Big avatar, name, Edit; one card of rows, each opening its own page: Plan & routines
  (Calendar · Kanban · Text plus the routines, "2 on"), Computer (live view full screen, Take control at the bottom,
  status "Idle"/"On it"), Library (the bot's documents and links by Today / This week), Settings (model, effort,
  approval mode and topics, memory, skills, decisions, question book, journal, Mac folders, apps, Vault); then a
  Notifications switch.
- **Chat (Grok):** ⋯ menu: View profile, Find in chat, Share as template, Retire this bot. The composer's +: Choose
  file, Take photo, Photo or video.
- **Settings (Grok):** grouped rounded cards: Account; Connections (connectors, Mac folders); Appearance (accent);
  Notifications; Gateway; Sign out.
- **Workspace (TaskForge):** a bottom bar "Add or find anything…" plus Tasks · Notes · Calendar. Tasks: Today · Inbox ·
  Upcoming, filter chips (All · a project · No project), rows of checkbox, title and project pills. A project pill
  opens the project page: its tasks, budget, expenses and top-ups (Money is no longer its own tab). Calendar: a month
  grid with dots, the day's agenda below with a now line. Notes: one folder tree of notes and documents with counts.

## Slices

1. **Phone basics (R5, phone only).** Settings, the offline screen, the floating +, the accent colour choice (six
   colours from `tokens`, stored on the phone), the app icon. No server change.
2. **In-app update (R5).** The gateway serves the newest APK and its version (`GET /api/mobile/latest`, signed in);
   the app compares versions and offers Update → Android's own install prompt. The APK is dropped by the build into
   `~/Roost/mobile/` (outside the repo).
3. **Bot profile (R3, web + phone).** Built from the owner's Grok screenshots.
4. **Tasks + Projects + Money (R2, web + phone).** Designed with the owner first (a mockup in `docs/design/`),
   then built.
5. **Notes + Documents (R2, web + phone).** One Notes tab; Obsidian later (owner: decided later; a separate phone
   vault stays possible).
6. **Polish pass (R4).** Every screen, with the owner's pictures and TaskForge ideas.
