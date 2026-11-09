import 'package:intl/intl.dart';

import '../../util/app_time.dart';

/// Every day and time on the Board is on the account's clock.
DateTime appToday([DateTime? now]) => appDay(now ?? DateTime.now());

String isoDay(DateTime d) => DateFormat('yyyy-MM-dd').format(d);

/// The account's clock now, "HH:mm".
String appNowClock([DateTime? now]) =>
    DateFormat('HH:mm').format(appMoment(now ?? DateTime.now()));

/// "2026-10-23" or "2026-10-23T09:00:00+02:00" to the account's day and
/// clock.
({DateTime day, String? clock})? readDue(String? due) {
  if (due == null || due.length < 10) return null;
  final day = DateTime.tryParse(due.substring(0, 10));
  if (day == null) return null;
  if (due.length > 10 && due.contains('T')) {
    final at = DateTime.tryParse(due);
    if (at != null) {
      final m = appMoment(at);
      return (
        day: DateTime.utc(m.year, m.month, m.day),
        clock: DateFormat('HH:mm').format(m),
      );
    }
  }
  return (day: DateTime.utc(day.year, day.month, day.day), clock: null);
}

/// "Today", "Tomorrow", "Fri 23 Oct", with " 09:00" when timed.
String dueWords(String? due, {DateTime? today}) {
  final r = readDue(due);
  if (r == null) return '';
  final gap = r.day.difference(today ?? appToday()).inDays;
  final word = switch (gap) {
    0 => 'Today',
    1 => 'Tomorrow',
    -1 => 'Yesterday',
    _ => DateFormat('EEE d MMM').format(r.day),
  };
  return r.clock == null ? word : '$word ${r.clock}';
}

/// "Fri 23 Oct, 09:00" on the account's clock for a stored moment.
String momentWords(String? iso) {
  if (iso == null || iso.isEmpty) return '';
  final zoned = RegExp(r'(Z|[+-]\d\d:?\d\d)$').hasMatch(iso);
  final at = DateTime.tryParse(zoned ? iso : '${iso}Z');
  if (at == null) return iso;
  return DateFormat('EEE d MMM, HH:mm').format(appMoment(at));
}

/// The reschedule sheet's quick picks, from the account's [today].
List<({String label, DateTime? day})> reschedulePicks(DateTime today) {
  final toSaturday = (DateTime.saturday - today.weekday + 7) % 7;
  final toMonday = (DateTime.monday - today.weekday + 7) % 7;
  final nextMonday = today.add(Duration(days: toMonday == 0 ? 7 : toMonday));
  return [
    (label: 'Today', day: today),
    (label: 'Tomorrow', day: today.add(const Duration(days: 1))),
    (label: 'This weekend', day: today.add(Duration(days: toSaturday))),
    (label: 'Next Monday', day: nextMonday),
    (label: '+1 week', day: today.add(const Duration(days: 7))),
    (label: 'No date', day: null),
  ];
}
