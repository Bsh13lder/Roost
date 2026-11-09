import 'package:flutter/foundation.dart';

/// Minutes in a day: quiet hours are minutes of an account-zone day.
const minutesPerDay = 24 * 60;

/// "23:00" for a minute of the day.
String clockText(int minute) {
  final h = (minute ~/ 60).toString().padLeft(2, '0');
  final m = (minute % 60).toString().padLeft(2, '0');
  return '$h:$m';
}

/// What the phone tells you, stored on the phone (the app and the Stay
/// connected service both read it). Off until you turn Stay connected on.
@immutable
class NotifyPrefs {
  const NotifyPrefs({
    this.stayConnected = false,
    this.needsOk = true,
    this.reports = true,
    this.replies = true,
    this.reminders = true,
    this.quietOn = false,
    this.quietFrom = 23 * 60,
    this.quietTo = 7 * 60,
  });

  /// Anything unreadable is the defaults: a bad file never turns alerts off
  /// halfway or throws in the service.
  factory NotifyPrefs.fromJson(Object? raw) {
    if (raw is! Map) return const NotifyPrefs();
    const d = NotifyPrefs();
    final from = raw['quiet_from'], to = raw['quiet_to'];
    final bools = [
      for (final k in const ['stay_connected', 'needs_ok', 'reports', 'replies', 'reminders', 'quiet_on'])
        raw.containsKey(k) ? raw[k] : null,
    ];
    final minutesOk = [from, to].every((v) => v == null || (v is int && v >= 0 && v < minutesPerDay));
    if (!minutesOk || bools.any((v) => v != null && v is! bool)) return d;
    return NotifyPrefs(
      stayConnected: bools[0] as bool? ?? d.stayConnected,
      needsOk: bools[1] as bool? ?? d.needsOk,
      reports: bools[2] as bool? ?? d.reports,
      replies: bools[3] as bool? ?? d.replies,
      reminders: bools[4] as bool? ?? d.reminders,
      quietOn: bools[5] as bool? ?? d.quietOn,
      quietFrom: from as int? ?? d.quietFrom,
      quietTo: to as int? ?? d.quietTo,
    );
  }

  final bool stayConnected;
  final bool needsOk, reports, replies, reminders;
  final bool quietOn;

  /// Minutes of the account's day; quiet runs from [quietFrom] up to [quietTo],
  /// across midnight when [quietTo] is earlier.
  final int quietFrom, quietTo;

  bool isQuietAt(int minute) {
    if (!quietOn || quietFrom == quietTo) return false;
    return quietFrom < quietTo
        ? minute >= quietFrom && minute < quietTo
        : minute >= quietFrom || minute < quietTo;
  }

  Map<String, Object> toJson() => {
        'stay_connected': stayConnected,
        'needs_ok': needsOk,
        'reports': reports,
        'replies': replies,
        'reminders': reminders,
        'quiet_on': quietOn,
        'quiet_from': quietFrom,
        'quiet_to': quietTo,
      };

  NotifyPrefs copyWith({
    bool? stayConnected,
    bool? needsOk,
    bool? reports,
    bool? replies,
    bool? reminders,
    bool? quietOn,
    int? quietFrom,
    int? quietTo,
  }) =>
      NotifyPrefs(
        stayConnected: stayConnected ?? this.stayConnected,
        needsOk: needsOk ?? this.needsOk,
        reports: reports ?? this.reports,
        replies: replies ?? this.replies,
        reminders: reminders ?? this.reminders,
        quietOn: quietOn ?? this.quietOn,
        quietFrom: quietFrom ?? this.quietFrom,
        quietTo: quietTo ?? this.quietTo,
      );

  @override
  bool operator ==(Object other) =>
      other is NotifyPrefs && mapEquals(other.toJson(), toJson());

  @override
  int get hashCode => Object.hashAll(toJson().values);
}
