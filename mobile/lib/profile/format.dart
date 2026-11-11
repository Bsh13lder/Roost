import 'dart:convert';

import 'package:intl/intl.dart';

import '../util/app_time.dart';

/// "22 Oct, 14:19" on the account's clock for a server timestamp; empty
/// text if unreadable.
String appShort(String iso) {
  if (iso.isEmpty) return '';
  try {
    return DateFormat('d MMM, HH:mm').format(appMoment(parseServerTime(iso)));
  } on FormatException {
    return '';
  }
}

/// "12:40" when [iso] is today on the account's clock, else "22 Oct, 12:40"
/// (the web's zoneClock); empty text if unreadable.
String appClockOrShort(String iso, {DateTime? now}) {
  if (iso.isEmpty) return '';
  try {
    final moment = parseServerTime(iso);
    final today = appDay(now ?? DateTime.now().toUtc()) == appDay(moment);
    return today ? appClock(iso) : appShort(iso);
  } on FormatException {
    return '';
  }
}

/// A decision memory is stored as {"q","a"} JSON, or "question Decision: answer".
({String question, String answer})? parseDecision(String text) {
  final t = text.trim();
  if (t.startsWith('{')) {
    try {
      final data = jsonDecode(t);
      if (data is! Map) return null;
      final q = (data['q'] as String? ?? '').trim();
      final a = (data['a'] as String? ?? '').trim();
      return q.isNotEmpty && a.isNotEmpty ? (question: q, answer: a) : null;
    } on FormatException {
      return null;
    }
  }
  final i = t.indexOf(' Decision: ');
  if (i < 0) return null;
  return (question: t.substring(0, i), answer: t.substring(i + 11));
}
