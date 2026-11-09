import 'package:intl/intl.dart';
import 'package:timezone/data/latest.dart' as tzdata;
import 'package:timezone/timezone.dart' as tz;

/// The zone used before the account's is known and none was kept.
const fallbackZoneName = 'UTC';

bool _ready = false;

/// The one place that holds the account's zone (owner, 2026-11-09): set from
/// `/api/auth/me` or the kept copy, read by every day and clock on the phone.
String _zoneName = fallbackZoneName;

void _init() {
  if (_ready) return;
  tzdata.initializeTimeZones();
  _ready = true;
}

/// "UTC" is not always in the bundled database, so it is answered here.
tz.Location _lookup(String name) {
  _init();
  return name == fallbackZoneName ? tz.UTC : tz.getLocation(name);
}

/// Whether [name] is an IANA zone the bundled tz database knows.
bool isKnownZone(String? name) {
  if (name == null || name.isEmpty) return false;
  try {
    _lookup(name);
    return true;
  } on tz.LocationNotFoundException {
    return false;
  }
}

/// Makes [name] the account's zone; false, and nothing changes, when it is
/// null or a zone the phone doesn't know.
bool setAppZone(String? name) {
  if (!isKnownZone(name)) return false;
  _zoneName = name!;
  return true;
}

/// The account's IANA zone name ("Europe/Madrid").
String appZoneName() => _zoneName;

/// The account's zone, its data loaded once.
tz.Location appLocation() => _lookup(_zoneName);

/// "Madrid" for "Europe/Madrid", "New York" for "America/New_York", "UTC"
/// for "UTC": the words for which clock a time is on.
String zoneCity([String? name]) =>
    (name ?? _zoneName).split('/').last.replaceAll('_', ' ');

/// Parses a server timestamp; one with no zone is UTC.
DateTime parseServerTime(String iso) {
  final hasZone = RegExp(r'(Z|[+-]\d\d:?\d\d)$').hasMatch(iso);
  return DateTime.parse(hasZone ? iso : '${iso}Z').toUtc();
}

/// A moment on the account's clock.
tz.TZDateTime appMoment(DateTime moment) =>
    tz.TZDateTime.from(moment.toUtc(), appLocation());

/// "Fri 23 Oct, 09:00" on the account's clock.
String appDayClock(String iso) =>
    DateFormat('EEE d MMM, HH:mm').format(appMoment(parseServerTime(iso)));

/// The account's calendar day of a moment, as a plain date (no time).
DateTime appDay(DateTime moment) {
  final local = appMoment(moment);
  return DateTime.utc(local.year, local.month, local.day);
}

/// Minutes since midnight on the account's clock (quiet hours).
int appMinuteOfDay(DateTime moment) {
  final local = appMoment(moment);
  return local.hour * 60 + local.minute;
}

/// "14:19" on the account's clock.
String appClock(String iso) =>
    DateFormat('HH:mm').format(appMoment(parseServerTime(iso)));
