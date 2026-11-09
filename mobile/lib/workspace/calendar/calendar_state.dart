import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../board/tasks/task_dates.dart';
import '../../live/live_connection.dart';
import 'day_notes_api.dart';

/// The month the Workspace calendar shows ("2026-10"), the account's to start.
final workMonthProvider = StateProvider.autoDispose<String>(
    (_) => isoDay(appToday()).substring(0, 7));

/// The day whose agenda shows under the grid.
final workDayProvider =
    StateProvider.autoDispose<DateTime>((_) => appToday());

String shiftMonthBy(String month, int by) {
  final d = DateTime.parse('$month-01');
  return isoDay(DateTime.utc(d.year, d.month + by, 1)).substring(0, 7);
}

/// A month's day notes; reloaded when the gateway says they changed.
final monthDayNotesProvider =
    FutureProvider.autoDispose.family<List<DayNote>, String>((ref, month) {
  final sub = ref
      .read(frameBusProvider)
      .stream
      .where((f) => f['type'] == 'day_notes_changed')
      .listen((_) => ref.invalidateSelf());
  ref.onDispose(sub.cancel);
  final first = DateTime.parse('$month-01');
  final last = DateTime.utc(first.year, first.month + 1, 0);
  return ref
      .watch(dayNotesApiProvider)
      .range(isoDay(first), isoDay(last));
});
