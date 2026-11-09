import 'package:intl/intl.dart';

import '../../util/app_time.dart';

const _symbols = {'EUR': '€', 'USD': 'US\$', 'GBP': '£'};

/// The account's today as `YYYY-MM-DD`.
String appTodayIso() =>
    DateFormat('yyyy-MM-dd').format(appMoment(DateTime.now()));

/// The account's month as `YYYY-MM`.
String appMonth() => appTodayIso().substring(0, 7);

/// An amount the server sent, for display only: `€12.50`, `US$20.00`.
String formatMoney(String amount, String currency) {
  final n = double.tryParse(amount) ?? 0;
  final code = currency.isEmpty ? 'EUR' : currency;
  final symbol = _symbols[code];
  final text = NumberFormat('#,##0.00', 'en_IE').format(n.abs());
  final sign = n < 0 ? '-' : '';
  return symbol != null ? '$sign$symbol$text' : '$sign$code $text';
}

/// A server amount without its minus sign ("over by" lines).
String unsigned(String amount) =>
    amount.startsWith('-') ? amount.substring(1) : amount;

/// `Tue 13 Oct` from `2026-10-13`.
String dayLabel(String day) {
  final d = DateTime.tryParse(day);
  return d == null ? day : DateFormat('EEE d MMM').format(d);
}

/// `October 2026` from `2026-10`.
String monthLabel(String month) {
  final d = DateTime.tryParse('$month-15');
  return d == null ? month : DateFormat('MMMM yyyy').format(d);
}

String shiftMonth(String month, int delta) {
  final parts = month.split('-');
  final index = int.parse(parts[0]) * 12 + (int.parse(parts[1]) - 1) + delta;
  final y = index ~/ 12;
  final m = (index % 12) + 1;
  return '$y-${m.toString().padLeft(2, '0')}';
}

String lastDayOfMonth(String month) {
  final next = shiftMonth(month, 1).split('-');
  final d = DateTime(int.parse(next[0]), int.parse(next[1]), 0);
  return DateFormat('yyyy-MM-dd').format(d);
}

/// Monday of the week that holds [day] (`YYYY-MM-DD`).
String mondayOf(String day) {
  final d = DateTime.parse(day);
  return isoDay(d.subtract(Duration(days: d.weekday - 1)));
}

String isoDay(DateTime d) => DateFormat('yyyy-MM-dd').format(d);

/// `21 Oct` for a server timestamp.
String shortDate(String iso) {
  final d = DateTime.tryParse(iso);
  return d == null ? '' : DateFormat('d MMM').format(d.toLocal());
}
