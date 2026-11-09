import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../../board/tasks/task_repo.dart';
import '../calendar/calendar_state.dart';
import '../workspace_state.dart';

/// The day a line that names none gets: the chosen calendar day while the
/// Calendar shows (as on the web's calendar day), none on Tasks or Notes.
final quickDefaultDayProvider = Provider.autoDispose<DateTime?>((ref) {
  final section = ref.watch(workspaceSectionProvider);
  return section == WorkspaceSection.calendar ? ref.watch(workDayProvider) : null;
});

/// "Due Wed 21 Oct": the badge a calendar day's line wears.
String dayBadge(DateTime day) => 'Due ${DateFormat('EEE d MMM').format(day)}';

/// Each tag once (first spelling wins), the most used first.
List<String> rankedTags(Iterable<String> all) {
  final counts = <String, ({String name, int count})>{};
  for (final name in all) {
    final key = name.toLowerCase();
    final seen = counts[key];
    counts[key] = (name: seen?.name ?? name, count: (seen?.count ?? 0) + 1);
  }
  final sorted = counts.values.toList()
    ..sort((a, b) => b.count != a.count ? b.count - a.count : a.name.compareTo(b.name));
  return [for (final t in sorted) t.name];
}

/// The tags your tasks already carry, for "#" suggestions (as the web).
final quickTagsProvider = FutureProvider.autoDispose<List<String>>((ref) async {
  reloadOnTasksChanged(ref);
  final tasks = await ref.watch(taskRepoProvider).query({'status': 'all'});
  return rankedTags(tasks.expand((t) => t.tags));
});
