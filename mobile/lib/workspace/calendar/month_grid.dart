/// Every day the month's grid shows ("2026-10"): Monday first, whole weeks,
/// so the first row may start in the month before and the last end after.
List<DateTime> monthGrid(String month) {
  final first = DateTime.parse('$month-01');
  final start = DateTime.utc(first.year, first.month, 1 - (first.weekday - 1));
  final last = DateTime.utc(first.year, first.month + 1, 0);
  final end = DateTime.utc(last.year, last.month, last.day + (7 - last.weekday));
  final count = end.difference(start).inDays + 1;
  return [
    for (var i = 0; i < count; i++)
      DateTime.utc(start.year, start.month, start.day + i),
  ];
}
