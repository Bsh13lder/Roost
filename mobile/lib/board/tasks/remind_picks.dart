import 'package:intl/intl.dart';
import 'package:timezone/timezone.dart' as tz;

import '../../util/app_time.dart';

/// One Remind me quick pick and the reminder time it sends (the account's wall time).
class RemindPick {
  const RemindPick(this.label, this.wire);

  final String label;
  final String wire;
}

const _picks = [
  ('At the due time', Duration.zero),
  ('10 min before', Duration(minutes: 10)),
  ('1 hour before', Duration(hours: 1)),
  ('1 day before', Duration(days: 1)),
];

/// "2026-12-01T08:50": a moment as the account's wall time, which the server reads
/// as the account's.
String appWire(DateTime moment) {
  final local = tz.TZDateTime.from(moment.toUtc(), appLocation());
  return DateFormat("yyyy-MM-dd'T'HH:mm").format(local);
}

/// The quick picks for a due date with a time; none for a day with no time
/// (the sheet offers a day and time instead).
List<RemindPick> remindPicks(String? dueDate) {
  if (dueDate == null || !dueDate.contains('T')) return const [];
  final DateTime due;
  try {
    due = parseServerTime(dueDate);
  } on FormatException {
    return const [];
  }
  // "1 day before" is the same account-zone clock the day before, across a summer
  // time change too: subtract on the wall clock, not in hours.
  final local = tz.TZDateTime.from(due, appLocation());
  String dayBefore(int days) => DateFormat("yyyy-MM-dd'T'HH:mm")
      .format(DateTime(local.year, local.month, local.day - days, local.hour, local.minute));
  return [
    for (final (label, before) in _picks)
      RemindPick(label, before.inDays >= 1 ? dayBefore(before.inDays) : appWire(due.subtract(before))),
  ];
}

/// The drawer row's value: when it reminds you, or Off.
String reminderWords(String? reminderAt) => reminderAt == null ? 'Off' : appDayClock(reminderAt);

/// "Tue 1 Dec, 08:50" for a wall time on the account's clock like "2026-12-01T08:50".
String wireWords(String wire) => DateFormat('EEE d MMM, HH:mm').format(DateTime.parse(wire));
