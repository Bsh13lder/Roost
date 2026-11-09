# Roost: the account's time zone (owner, 2026-11-09)

Owner request: "why not auto detect". Roost is going public, and every day, clock and "today" was hard-coded to
Europe/Madrid. The zone is now the account's own, detected by the web app.

## Decisions

- **One zone per install.** Roost has one account per install, so the zone is install-wide (the account's), not
  threaded through every call.
- **Effective zone** (`roost/timezones.py`): the account's `users.timezone`, else env `ROOST_TIMEZONE`, else `UTC`.
  `local_tz()` / `local_tz_name()` read a process-wide holder at use time (never captured at import);
  `load_local_tz(config)` fills it at startup, `set_local_tz(name)` replaces it (the PUT below). `zone_city()` gives
  the place for words ("Madrid time", "New York time": the last IANA segment, `_` as a space).
- **Stored moments stay UTC.** Reminders and dues keep their stored moments (a task due "tomorrow 9:00" was already
  resolved). Only days and wall clocks follow the zone: Today / Overdue and the other task views, token usage days,
  daily caps, journal days, money months and days, day notes, routines, the date parser (`nl_time`), quick lines and
  an offline task's `typed_at` reading.
- **Routines** store `next_run_at` in UTC computed from local times; when the zone changes every enabled timed
  routine is planned again (`RoutineStore.replan_all`), so 08:00 stays 08:00 local. A watching routine's next check
  is a plain interval and stays.

## Contract (web and phone build against this)

- Schema v45: `ALTER TABLE users ADD COLUMN timezone TEXT` (an IANA name, plaintext: a setting, not user content).
  The migration sets existing rows to `Europe/Madrid`, so today's owner keeps today's behaviour. A new account starts
  `NULL`. The LazyClaw importer's `SUPPORTED_SCHEMA_VERSIONS` includes 45 (it writes nothing there).
- `GET /api/auth/me` gains `"timezone": "<IANA>" | null` (`null` only for an account that never set one).
- `PUT /api/auth/timezone` with `{"timezone": "<IANA>"}` (extra fields refused, at most 64 characters, a name in
  `zoneinfo.available_timezones()`, never `localtime`) answers 200 `{"timezone": "<IANA>"}`; 422 for a bad name
  (the refusal never echoes the body); 401 when not signed in; 403 for a foreign Origin, like the other auth routes.
- Model-facing words: the instructions' time line names the zone (`... (America/New_York).`), and tool results say
  "<place> time". Tool descriptions say "local time"; the instructions name the zone.
- JSON field names such as `next_run_madrid` stay as they are (wire compatibility with the phone); only their values
  follow the zone.

## Left Madrid-specific on purpose

- `roost/migrate/lazyclaw/`: `EXPECTED_TIMEZONE` reads LazyClaw's own Madrid data.
- Function names such as `madrid_today` and `seconds_until_madrid_midnight` keep their names (now the local day);
  renaming them would churn hundreds of call sites and tests for no behaviour change.
- The test suite runs on Madrid (`ROOST_TIMEZONE=Europe/Madrid` in `tests/conftest.py`, the account zone cleared
  around every test), so its fixed instants keep their meaning.
