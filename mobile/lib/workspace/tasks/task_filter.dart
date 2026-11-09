import 'package:flutter/foundation.dart';

import '../../board/tasks/task_models.dart';
import '../workspace_state.dart';
import 'work_projects.dart';

export 'work_projects.dart' show noProject;

/// The date chips. They combine as OR: Today and Overdue shows both.
enum DateFilter {
  today('Today', 'today'),
  overdue('Overdue', 'overdue'),
  upcoming('Upcoming', 'upcoming'),
  noDate('No date', 'nodate');

  const DateFilter(this.label, this.id);
  final String label;

  /// The chip's stable name, kept on the phone and used in keys.
  final String id;

  /// Whether [t] sits in this chip, by the server's `due_bucket`.
  bool holds(TaskItem t) => switch (this) {
        DateFilter.today => t.dueBucket == 'today',
        DateFilter.overdue => t.dueBucket == 'overdue',
        DateFilter.upcoming =>
          const {'tomorrow', 'week', 'later'}.contains(t.dueBucket),
        DateFilter.noDate => t.dueBucket == 'none',
      };
}

const _highPriorities = {'urgent', 'high'};

/// What the Tasks chips have on. Immutable: every toggle returns a new one.
/// Dates and Done are OR'd; High priority and projects each narrow.
@immutable
class TaskFilter {
  const TaskFilter({
    this.dates = const {},
    this.high = false,
    this.done = false,
    this.projects = const {},
  });

  /// Anything unreadable is no filter, so a bad value never hides tasks.
  factory TaskFilter.fromJson(Object? raw) {
    if (raw is! Map) return const TaskFilter();
    final names = raw['dates'] is List ? raw['dates'] as List : const [];
    final projects = raw['projects'] is List ? raw['projects'] as List : const [];
    return TaskFilter(
      dates: {
        for (final d in DateFilter.values)
          if (names.contains(d.id)) d,
      },
      high: raw['high'] == true,
      done: raw['done'] == true,
      projects: {for (final p in projects) if (p is String && p.isNotEmpty) p},
    );
  }

  final Set<DateFilter> dates;
  final bool high;
  final bool done;
  final Set<String> projects;

  bool get isEmpty => dates.isEmpty && !high && !done && projects.isEmpty;

  int get activeCount =>
      dates.length + projects.length + (high ? 1 : 0) + (done ? 1 : 0);

  /// Open tasks show unless only Done is on.
  bool get wantsOpen => dates.isNotEmpty || !done;

  TaskFilter toggleDate(DateFilter d) => _copy(dates: _flip(dates, d));
  TaskFilter toggleHigh() => _copy(high: !high);
  TaskFilter toggleDone() => _copy(done: !done);
  TaskFilter toggleProject(String id) => _copy(projects: _flip(projects, id));

  TaskFilter _copy({
    Set<DateFilter>? dates,
    bool? high,
    bool? done,
    Set<String>? projects,
  }) =>
      TaskFilter(
        dates: dates ?? this.dates,
        high: high ?? this.high,
        done: done ?? this.done,
        projects: projects ?? this.projects,
      );

  /// The narrowing chips (priority and project) for any task, open or done.
  bool narrows(TaskItem t) {
    if (high && !_highPriorities.contains(t.priority)) return false;
    if (projects.isEmpty) return true;
    return projects.contains(t.projectId ?? noProject);
  }

  bool keepsOpen(TaskItem t) =>
      wantsOpen && (dates.isEmpty || dates.any((d) => d.holds(t))) && narrows(t);

  Map<String, Object> toJson() => {
        'dates': [for (final d in DateFilter.values) if (dates.contains(d)) d.id],
        'high': high,
        'done': done,
        'projects': [...projects]..sort(),
      };

  @override
  bool operator ==(Object other) =>
      other is TaskFilter &&
      setEquals(other.dates, dates) &&
      other.high == high &&
      other.done == done &&
      setEquals(other.projects, projects);

  @override
  int get hashCode => Object.hash(
        Object.hashAllUnordered(dates),
        high,
        done,
        Object.hashAllUnordered(projects),
      );
}

Set<T> _flip<T>(Set<T> set, T value) => Set.unmodifiable(
    set.contains(value) ? set.difference({value}) : {...set, value});

/// The tasks the list shows: open ones the chips keep, then done ones when
/// Done is on, narrowed by the words typed in the bottom bar.
List<TaskItem> applyFilter(
  TaskFilter f, {
  required List<TaskItem> open,
  required List<TaskItem> done,
  String typed = '',
}) =>
    [
      for (final t in open)
        if (f.keepsOpen(t) && matchesQuery(t.title, typed)) t,
      if (f.done)
        for (final t in done)
          if (f.narrows(t) && matchesQuery(t.title, typed)) t,
    ];

/// How many open tasks a date chip would show.
int countFor(DateFilter d, List<TaskItem> open) => open.where(d.holds).length;

/// How many open tasks are urgent or high.
int highCount(List<TaskItem> open) =>
    open.where((t) => _highPriorities.contains(t.priority)).length;
