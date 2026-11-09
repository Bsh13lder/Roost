import 'package:flutter/foundation.dart';
import 'package:intl/intl.dart';

import '../../board/tasks/task_dates.dart';
import '../../board/tasks/task_models.dart';

/// How a section header reads: late is red, done is quiet.
enum SectionTone { late, normal, done }

/// One collapsible group of rows: Overdue, Today, Tomorrow, a later day,
/// No date or Done.
@immutable
class TaskSection {
  const TaskSection({
    required this.key,
    required this.title,
    required this.tasks,
    this.tone = SectionTone.normal,
  });

  /// Stable across reloads ("overdue", "2026-10-27"), so a folded section
  /// stays folded.
  final String key;
  final String title;
  final List<TaskItem> tasks;
  final SectionTone tone;
}

const _fixed = {
  'overdue': ('Overdue', SectionTone.late),
  'today': ('Today', SectionTone.normal),
  'tomorrow': ('Tomorrow', SectionTone.normal),
};

/// The section a task belongs in, from the server's `due_bucket` (the account's
/// day) and, for later days, the due day itself.
String sectionKeyOf(TaskItem t) {
  if (t.isDone) return 'done';
  if (_fixed.containsKey(t.dueBucket)) return t.dueBucket;
  final due = readDue(t.dueDate);
  return due == null ? 'none' : isoDay(due.day);
}

String _titleOf(String key) {
  final fixed = _fixed[key];
  if (fixed != null) return fixed.$1;
  if (key == 'none') return 'No date';
  if (key == 'done') return 'Done';
  return DateFormat('EEE d MMM').format(DateTime.parse(key));
}

SectionTone _toneOf(String key) =>
    _fixed[key]?.$2 ?? (key == 'done' ? SectionTone.done : SectionTone.normal);

/// Rank: the fixed three first, then days in date order, No date, Done.
int _compareKeys(String a, String b) {
  int rank(String k) => switch (k) {
        'overdue' => 0,
        'today' => 1,
        'tomorrow' => 2,
        'none' => 4,
        'done' => 5,
        _ => 3,
      };
  final byRank = rank(a).compareTo(rank(b));
  return byRank != 0 ? byRank : a.compareTo(b);
}

/// Groups [tasks] into sections in Todoist's order, each keeping the order
/// the server sent (by due, then priority).
List<TaskSection> sectionsOf(List<TaskItem> tasks) {
  final groups = <String, List<TaskItem>>{};
  for (final t in tasks) {
    (groups[sectionKeyOf(t)] ??= []).add(t);
  }
  final keys = groups.keys.toList()..sort(_compareKeys);
  return [
    for (final k in keys)
      TaskSection(
        key: k,
        title: _titleOf(k),
        tasks: List.unmodifiable(groups[k]!),
        tone: _toneOf(k),
      ),
  ];
}
