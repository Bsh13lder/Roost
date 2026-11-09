# Phone notifications: Stay connected

Owner decision, 2026-10-23: the phone gets alerts by **staying connected** to the Mac over Tailscale. An Android
foreground service keeps one `/api/events` socket open and shows a small "Roost" notification while it runs.
Alerts come at once, and nothing goes through Google or Firebase. The Mac stays on, so the socket has someone to
talk to.

## Decisions

- **N1. One socket, the same events.** The service reads the frames the app already gets (`message`,
  `text_delta`, `message_done`, `snapshot`, `bot_updated`). No new server event was needed. Every frame the server
  sends was already there for the web and the app.
- **N2. What alerts.**
  - Needs your OK: Ask, Proposal and options cards (`approval` messages), Stuck and Sign-in cards (`stuck`), and
    routine, skill, instructions and connector proposals.
  - Reports: a `report` message whose source is not a reminder.
  - Task reminders: a `report` whose source is `reminder`. These are the existing reminder sender's Reports.
  - Replies: a bot's text reply, alerted once `message_done` arrives and taken from its streamed text.
  - Each alert opens that bot's chat when tapped.
- **N3. Never noise.**
  - One alert per card or message id, remembered for the newest 500.
  - Nothing about the chat open on screen.
  - Replies only while the app is away.
  - The bot's own Notifications switch (`bots.notify`) counts.
  - Each kind has its own switch.
  - Quiet hours (Madrid) hush everything except your own task reminders.
- **N4. No secrets.** An alert is a bot's name, a card's step title (titles never carry typed text) or the first
  line of a bot's words, cut to 120 characters. Text from a tainted message starts "From web content ·".
- **N5. Remind me.** The web and phone drawers get quick picks before a timed due: at the due time, 10 min, 1 hour,
  or 1 day before, counted on Madrid's clock. They also offer a day and time, or Off.
  - A reminder set there reminds you only then: `pre_reminders: []` goes next to `reminder_at` on
    `PATCH /api/tasks/{id}`. The PATCH refuses advance reminders without a reminder time.
  - Bots set it through `update_task`'s new `reminder_at` and `pre_reminders`.

## Pieces

- **Alert rules.** `mobile/lib/notify/alert_rules.dart` (`AlertBook`, pure) decides which frame becomes an alert.
  `notify_prefs.dart` holds the switches and quiet hours, stored with the plugin's shared data so the service's
  own isolate reads them (`notify_store.dart`).
- **The pump.** `alert_pump.dart` keeps the socket with a backoff and resumes from the last cursor. It says
  "Connected to your Mac" or "Reconnecting…" in the service's notification.
- **The service.** `stay_connected.dart` runs it (`flutter_foreground_task`, MIT): foreground service type
  `remoteMessaging`, restarted after a reboot or an app update.
- **Showing alerts.** `local_alerts.dart` shows them (`flutter_local_notifications`, BSD-3) on four channels.
  `alert_taps.dart` turns a tap into `/chat/<bot>`.
- **The app's side.** The app tells the service what is on screen (`appFocusProvider`: whether the app is in
  front, and the chat that is open). It also starts the service again on launch when the switch is on.
- **Settings → Notifications.** Stay connected (it asks for Android's notification permission first), the four
  kinds, quiet hours, a button that lets Roost run in the background (Xiaomi stops background apps), then each
  bot's own switch.

## Not yet

- iOS: the plugin only wakes there every 15 minutes or so, so the phone app stays Android first.
- Alerts don't carry a picture of the card, and you can't answer Yes or No from the notification.
