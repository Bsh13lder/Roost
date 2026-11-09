# Server needs (mobile track)

Nothing is blocking M0.

- `GET /api/chats` rows carry no bot group; the app joins them with `GET /api/bots` (`group`), like the web. Fine as is.
- Done (server): M1a: `GET /api/stuck/{card_id}` and `GET /api/routine-proposals/{id}` answer one card in its list's shape, open or closed (its final state); another user's id is 404. The app uses both (Stuck and routine-proposal cards fetch one by id).
- M1a: the live tool-step lines under a reply ("Added a task") are built on the web from `bot_status` activities; the app does not draw them yet. A stored record would serve both.
- Done (server): M4: a Report's body carries `bot_id` (set by the server for the bot that posted it); an older Report has none, so fall back to the message author. The app uses it (Open run log).
- Done (server): M4: `GET /api/chats/search?q=` (1–100 chars) searches message text across your bot chats and rooms (not routine logs or cards), the `search_chat` tool's matching: `{"results": [{chat_kind, chat_id, name, thread_id, message_id, from_you, snippet, created_at, tainted}]}`, best first, at most 30. "Find in Chat" still searches only the messages already loaded. The app uses it on Home search (debounced, 2+ chars; a hit opens its chat).
- Done (server): M4: `GET /api/my-turn` answers the web's My turn in one call: `stuck`, `routine_proposals`, `skill_proposals`, `key_requests`, `questions` (each in its own route's shape, bots still on the team only), `rows` (`{kind, id, bot_id, thread_id, panel, text, created_at}`, the web's words and order) and `count`. Ask cards (`/api/approvals`) are not in it, as the web's My turn does not list them. The app uses it for My turn (rows and count); Ask cards still come from `/api/approvals`.
- Profile: granting a Mac folder (needs the Mac's folder window), adding a connector key, and opening a link outside the app are web-only for now.
- M3 Computer: the app asks for ZRLE, then CopyRect and Raw (`lib/computer/zrle.dart`). ZRLE was tried against a real computer's Xvnc on 2026-10-29: a full screen is about 301 KB instead of 4 MB, and it decodes to exactly the Raw frame's pixels. The gateway's RFB filter passes the encoding list through. Paste from the phone is not built. Trackpad mode is built.
- The app talks plain HTTP to the gateway (127.0.0.1 via `adb reverse`; a Tailscale address later); the Android network security config allows cleartext only to 127.0.0.1 and localhost.
- Done (server): M2a: `POST /api/tasks/{id}/restore` (with the Origin header) is Delete's exact Undo: the same task, id, steps and comments come back; 404 when the id is not one of your deleted tasks. The app's Undo should switch to it. The app's Undo now uses it.
- M2a: the Board's tab counts exist only for Tasks (`GET /api/tasks/counts`). Not adding Money, Notes or Documents counts: the web Board shows a count on the Tasks tab only, so the app should match it.
- Mobile polish: a bot's own picture can be uploaded or removed (Edit look sheet, `image_picker` shrinks it to 256 px), but the phone's Lensbot does not draw it yet; the web does. Nothing the server needs.
- Mobile polish: the Kanban groups by Status, Due date, Project and Priority only; Bot and List need `created_by_bot` and `category` on the task row the app already receives but does not read. Nothing the server needs.
- Workspace (TaskForge layout): nothing blocks; it uses the existing task, counts, projects, money, notes,
  documents, day-notes and parse routes. The Notes tree has one level (a folder per project) because notes and
  documents have no folders of their own; nested folders would need a folder field on both. A task step has no
  time, so the calendar agenda shows tasks and day notes only.
- Slice 3: the chat composer's + (Choose file, Take photo, Photo or video) is not on the phone: the server has no route that attaches a file or picture to a chat message (only `POST /api/documents/pdf` and a bot's picture), and the app has no file picker. It needs a chat attachment route first.
