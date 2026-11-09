import 'package:intl/intl.dart';
import 'package:timezone/timezone.dart' as tz;

import '../util/app_time.dart';

const _weekdaySpanDays = 6; // within this many account-zone days the weekday says enough

/// When a routine runs next, in words (owner, 2026-10-26, like Grok's "Next
/// run: in 10 hr."): "in 30 min" or "in 3 h" while it is today, then
/// "tomorrow 09:00", "Sat 09:00", or the date. "" for no time.
String nextRunWords(String? iso, DateTime now) {
  if (iso == null || iso.isEmpty) return '';
  final DateTime when;
  try {
    when = parseServerTime(iso);
  } on FormatException {
    return '';
  }
  final ahead = when.difference(now.toUtc());
  if (ahead <= Duration.zero) return 'now';
  final days = appDay(when).difference(appDay(now)).inDays;
  if (days == 0) {
    if (ahead < const Duration(hours: 1)) {
      final minutes = (ahead.inSeconds / 60).ceil();
      return 'in ${minutes < 1 ? 1 : minutes} min';
    }
    return 'in ${(ahead.inMinutes / 60).round()} h';
  }
  final local = tz.TZDateTime.from(when, appLocation());
  final clock = DateFormat('HH:mm').format(local);
  if (days == 1) return 'tomorrow $clock';
  if (days <= _weekdaySpanDays) return '${DateFormat('EEE').format(local)} $clock';
  return '${DateFormat('EEE d MMM').format(local)} $clock';
}
