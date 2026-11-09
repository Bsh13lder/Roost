# Roost mobile (Flutter): Android first, then iOS

Owner decisions (2026-10-22):
- The app is Flutter, not a web wrapper.
- It must do everything the web does: full parity, the way Grok's app matches Grok's web.
- Android first (the owner's phone), iOS on the Mac after that.
- At the start, only a few important tests. Speed matters more.

## 1. Where and what

- **Location:** `mobile/` in this repo, a Flutter app named `roost_mobile` (Android and iOS targets only).
- **Server:** it talks to the same gateway as the web, through the same `/api/*` routes and the same wire formats. The gateway gets **no change** from the mobile track unless it is reported first (see §6).
- **Reaching the gateway:**
  - **Development on Android:** plug the phone in over USB and run `adb reverse tcp:18800 tcp:18800`. The phone's `127.0.0.1:18800` is then the Mac's gateway. The gateway keeps binding 127.0.0.1 only.
  - **Away from home:** Tailscale (later, M5).
  - **The gateway URL** is a setting on the sign-in screen, default `http://127.0.0.1:18800`.
- **Auth:**
  - Sign in with `POST /api/auth/login`. The session cookie is kept in `flutter_secure_storage`.
  - Every request sends `Origin: <gateway URL>`, because mutating routes check the Origin allowlist (`roost/gateway/origin.py`).
  - The password is never stored or logged.
- **Live updates:** `WS /api/events`, the same event frames the web's `store/live.ts` reads.
- **Computer:** `WS /api/bots/{id}/live` carries RFB (VNC) through `roost/desk/rfb.py`.
  - M3 uses a WebView, which loads the gateway's own web page for the computer (the session cookie is set in the WebView).
  - A native Dart RFB view can come later.

## 2. Packages (licence gate)

Only MIT, BSD or Apache-2.0 packages, checked on pub.dev before they are added:
- flutter_riverpod (MIT)
- go_router (BSD-3)
- dio (MIT)
- web_socket_channel (BSD-3)
- flutter_secure_storage (BSD-3)
- webview_flutter (BSD-3)
- flutter_markdown or its maintained fork (BSD-3)
- intl (BSD-3)
- timezone (BSD-2), so every time is shown in Europe/Madrid.

`mobile/test/license_gate_test.dart` reads `pubspec.yaml` and refuses any dependency missing from its allowlist.

## 3. Look

- **Dark, matching the web:** the colours and sizes are copied from `web/src/styles/tokens.css` into `mobile/lib/theme/tokens.dart`, the one place for colours there.
- **Layout like Grok's mobile app (owner's screenshots):**
  - Home has your initials on the left and + on the right.
  - A row of big bot avatars, with a star on the main bot.
  - Chats under group headings.
  - A bottom bar with a grid button (the Board) and Search.
- **Avatars:** the Lensbot shapes, ported from `web/src/components/robot/lensbot.ts` to a `CustomPainter`.
- **Vocabulary:** the CLAUDE.md vocabulary table applies to every label.

## 4. Screens (full parity), mapped to the web

| Mobile screen | Web source |
|---|---|
| Sign in (gateway URL, username, password) | `web/src/screens/Login*` |
| Home: bots row, chats by group, search, + New bot, My turn | sidebar, Home |
| Settings sheet (initials) | profile / settings |
| Chat: markdown, step lines, day and New lines, reply quote, tapbacks, Stop, Queued, @mentions, composer with + | `web/src/components/chat/` |
| Cards in the chat: Ask, Options, Stuck, Sign-in, Proposal, model suggestion, skill / instruction / routine proposals, Add a key, Report, memory note with Undo | the card components |
| Bot profile: Info (model, effort, approval mode, Browsing actions, memories, Decisions, Skills, Routines, Journal, Connectors, Your Mac: folders, question book), Plan, Documents, Computer, Links | `web/src/components/panel/` |
| Edit bot, Avatar editor, Share as Template, Retire this bot | the edit sheets |
| Computer: live screen, Take control, I'm done, Teach | `ControlScreen.tsx` |
| Board: Tasks (Today · Upcoming · Overdue · Someday · Done, task drawer, steps, comments, quick add), Money, Notes, Documents, Projects | `web/src/components/board/` |
| Routines page | `/routines` |

## 5. Milestones

- **M0 Foundation:**
  - the project, theme, API client (with the Origin header and cookie);
  - sign in, Home, Chat (read, send, live events, markdown);
  - Android debug build.
- **M1 Cards and Profile:** every card in the chat; the Profile's Info tab; Edit bot and Avatar.
- **M2 Board:** Tasks with the drawer and quick add, Money, Notes, Projects. Documents opens read-only first.
- **M3 Computer:** the live screen and Take control through a WebView, Teach, and the Sign-in card flow.
- **M4 The rest:** Plan, Routines page, Skills, Connectors, Journal, Mac folders, search.
- **M5 Away from home:**
  - Tailscale;
  - push notifications (FCM on Android, APNs on iOS; needs a server sender, designed then);
  - the iOS build (needs Xcode fully installed and CocoaPods).

## 6. Rules for the mobile track

- Only `mobile/` changes. If a screen needs something the gateway lacks, write it in `mobile/SERVER_NEEDS.md`, and the chief builds it.
- Never open `~/Roost/data`, never type the owner's password, and never call a real LLM.
- Tests at the start: the licence gate, the API client (cookie, Origin header, error mapping), one widget test for sign-in and one for sending a chat message. More tests come once the screens settle.
- Checks before each commit: `flutter analyze` is clean, `flutter test` passes, and `flutter build apk --debug` builds when the Android licences are accepted.
