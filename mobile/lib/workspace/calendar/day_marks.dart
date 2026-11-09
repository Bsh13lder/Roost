import 'package:flutter/foundation.dart';

import '../../board/tasks/task_dates.dart';
import '../../board/tasks/task_models.dart';
import '../../routines/occurrences.dart';

/// The clean calendar (2026-10-26): what each account-zone day holds, as the
/// grid's markers and as the day panel's Tasks · Reminders · Routines.
/// Pure rules; the server only lists the month's tasks and routine runs.

const _open = {'todo', 'in_progress'};
const lateWords = 'Late';
const allDayWords = 'All day';
const _clockAllDay = '00:00'; // sorts an all-day task before timed ones
const _offset = r'^-\s*(?:(\d+)\s*d)?\s*(?:(\d+)\s*h)?\s*(?:(\d+)\s*m)?$';

bool isOpenTask(TaskItem t) => _open.contains(t.status);

/// One reminder firing: its account-zone day and "HH:mm".
@immutable
class ReminderFire {
  const ReminderFire(this.day, this.clock);
  final DateTime day;
  final String clock;
}

DateTime? _instant(String? iso) {
  if (iso == null || iso.isEmpty) return null;
  final zoned = RegExp(r'(Z|[+-]\d\d:?\d\d)$').hasMatch(iso);
  return DateTime.tryParse(zoned ? iso : '${iso}Z')?.toUtc();
}

DateTime? _before(String entry, DateTime base) {
  final m = RegExp(_offset, caseSensitive: false).firstMatch(entry.trim());
  if (m == null) return _instant(entry);
  int part(int i) => int.tryParse(m.group(i) ?? '') ?? 0;
  final gap = Duration(days: part(1), hours: part(2), minutes: part(3));
  return gap == Duration.zero ? null : base.subtract(gap);
}

/// When an open task's reminder and advance reminders (stored instants, or
/// offsets like -30m) fire, earliest first; a stray entry is skipped, as
/// the server's reminders job skips it. A finished task's never fire.
List<ReminderFire> reminderFires(TaskItem t) {
  final base = isOpenTask(t) ? _instant(t.reminderAt) : null;
  if (base == null) return const [];
  final moments = <DateTime>{
    base,
    for (final e in t.preReminders) ?_before(e, base),
  }.toList()
    ..sort();
  final seen = <String>{};
  return List.unmodifiable([
    for (final at in moments)
      if (readDue(at.toIso8601String()) case final r? when seen.add('${r.day} ${r.clock}'))
        ReminderFire(r.day, r.clock!),
  ]);
}

/// Open and due before [today].
bool isLate(TaskItem t, DateTime today) {
  final r = readDue(t.dueDate);
  return r != null && isOpenTask(t) && r.day.isBefore(today);
}

/// The day a task sits on: its due day, or [today] when it is late.
DateTime? placedDay(TaskItem t, DateTime today) =>
    isLate(t, today) ? today : readDue(t.dueDate)?.day;

/// One grid cell's markers. Immutable.
@immutable
class DayMarks {
  const DayMarks({
    this.tasks = const [],
    this.reminders = 0,
    this.routines = 0,
    this.botIds = const [],
    this.plans = 0,
  });

  /// The tasks that sit on the day, open ones first, each by time.
  final List<TaskItem> tasks;

  /// Tasks whose reminder fires that day.
  final int reminders;

  /// Routines that run that day.
  final int routines;

  /// The bots that made a task or run a routine that day, first seen first.
  final List<String> botIds;

  /// A bot's own Plan items that day (only its Plan calendar has them).
  final int plans;

  bool get isEmpty => tasks.isEmpty && reminders == 0 && routines == 0 && plans == 0;

  DayMarks withPlans(int count) =>
      DayMarks(tasks: tasks, reminders: reminders, routines: routines, botIds: botIds, plans: count);
}

/// [marks] with each day's Plan item count ("2026-10-23" -> n) added.
Map<DateTime, DayMarks> addPlanMarks(Map<DateTime, DayMarks> marks, Map<String, int> plans) {
  final counted = {
    for (final e in plans.entries) DateTime.parse('${e.key}T00:00:00Z'): e.value,
  };
  final days = {...marks.keys, ...counted.keys};
  return Map.unmodifiable({
    for (final d in days) d: (marks[d] ?? const DayMarks()).withPlans(counted[d] ?? 0),
  });
}

int _byTime(TaskItem a, TaskItem b, DateTime today) {
  final open = (isOpenTask(a) ? 0 : 1).compareTo(isOpenTask(b) ? 0 : 1);
  if (open != 0) return open;
  String key(TaskItem t) => isLate(t, today) ? '' : readDue(t.dueDate)?.clock ?? _clockAllDay;
  return key(a).compareTo(key(b));
}

/// [list] by [_byTime], keeping the given order among equals.
List<TaskItem> _sortedByTime(List<TaskItem> list, DateTime today) {
  final indexed = [...list.indexed]..sort((a, b) {
      final c = _byTime(a.$2, b.$2, today);
      return c != 0 ? c : a.$1.compareTo(b.$1);
    });
  return List.unmodifiable([for (final (_, t) in indexed) t]);
}

/// Every day's markers from the month's [tasks] and [routines].
Map<DateTime, DayMarks> buildDayMarks({
  required List<TaskItem> tasks,
  required RoutineDays routines,
  required DateTime today,
}) {
  final placed = <DateTime, List<TaskItem>>{};
  final reminded = <DateTime, Set<String>>{};
  for (final t in tasks) {
    final day = placedDay(t, today);
    if (day != null) (placed[day] ??= []).add(t);
    for (final f in reminderFires(t)) {
      (reminded[f.day] ??= {}).add(t.id);
    }
  }
  final runs = {
    for (final e in routines.entries) DateTime.parse('${e.key}T00:00:00Z'): e.value,
  };
  final days = {...placed.keys, ...reminded.keys, ...runs.keys};
  return Map.unmodifiable({
    for (final day in days) day: _marks(placed[day] ?? const [], reminded[day]?.length ?? 0, runs[day] ?? const [], today),
  });
}

DayMarks _marks(List<TaskItem> onDay, int reminders, List<RoutineDayEntry> runs, DateTime today) {
  final sorted = _sortedByTime(onDay, today);
  final bots = <String>{
    for (final t in sorted) ?t.createdByBot,
    for (final r in runs)
      if (r.botId.isNotEmpty) r.botId,
  };
  return DayMarks(
    tasks: sorted,
    reminders: reminders,
    routines: runs.length,
    botIds: List.unmodifiable(bots),
  );
}

/// A task row in the day panel: "Late", "All day" or its account-zone clock.
@immutable
class PlanTask {
  const PlanTask(this.time, this.task, {this.late = false});
  final String time;
  final TaskItem task;
  final bool late;
}

/// A reminder row: its first time that day, "08:30 +2" when it fires more.
@immutable
class PlanReminder {
  const PlanReminder(this.time, this.task);
  final String time;
  final TaskItem task;
}

/// One day as the panel lists it. Immutable.
@immutable
class DayPlan {
  const DayPlan({this.tasks = const [], this.reminders = const [], this.routines = const []});
  final List<PlanTask> tasks;
  final List<PlanReminder> reminders;
  final List<RoutineDayEntry> routines;

  bool get isEmpty => tasks.isEmpty && reminders.isEmpty && routines.isEmpty;
}

/// What [day] holds: its tasks (open first, Late, All day, then by clock),
/// the reminders that fire on it, and its routine runs.
DayPlan dayPlan(DateTime day, List<TaskItem> tasks, RoutineDays routines, DateTime today) {
  final onDay = _sortedByTime([for (final t in tasks) if (placedDay(t, today) == day) t], today);
  final reminders = <PlanReminder>[];
  for (final t in tasks) {
    final clocks = [for (final f in reminderFires(t)) if (f.day == day) f.clock];
    if (clocks.isEmpty) continue;
    final more = clocks.length > 1 ? ' +${clocks.length - 1}' : '';
    reminders.add(PlanReminder('${clocks.first}$more', t));
  }
  reminders.sort((a, b) => a.time.compareTo(b.time));
  return DayPlan(
    tasks: List.unmodifiable([
      for (final t in onDay)
        isLate(t, today)
            ? PlanTask(lateWords, t, late: true)
            : PlanTask(readDue(t.dueDate)?.clock ?? allDayWords, t),
    ]),
    reminders: List.unmodifiable(reminders),
    routines: routines[isoDay(day)] ?? const [],
  );
}
