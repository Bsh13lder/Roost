import '../common/format.dart';

/// The Money period: the month on screen, Today, This week, or a custom span.
enum Period { month, today, week, custom }

String periodName(Period p) => switch (p) {
      Period.month => 'Whole month',
      Period.today => 'Today',
      Period.week => 'This week',
      Period.custom => 'Custom range…',
    };

String periodLabel(Period p, ({String from, String to})? custom) {
  if (p == Period.custom && custom != null) {
    return custom.from == custom.to
        ? dayLabel(custom.from)
        : '${dayLabel(custom.from)}–${dayLabel(custom.to)}';
  }
  return periodName(p);
}

/// The days a period covers; the server filters and adds, a future last day is
/// clamped there.
({String from, String to}) periodSpan(
  Period p,
  String month,
  String today,
  ({String from, String to})? custom,
) =>
    switch (p) {
      Period.today => (from: today, to: today),
      Period.week => (from: mondayOf(today), to: today),
      Period.custom when custom != null => custom,
      _ => (from: '$month-01', to: lastDayOfMonth(month)),
    };
