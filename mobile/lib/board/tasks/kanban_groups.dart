import 'task_dates.dart';
import 'task_models.dart';

/// What the Kanban groups by (the web adds Bot and List; a phone starts with
/// the four that move a card).
enum KanbanGroup {
  status('Status'),
  due('Due date'),
  project('Project'),
  priority('Priority');

  const KanbanGroup(this.label);
  final String label;
}

const noProjectKey = 'none';

class KanbanColumn {
  const KanbanColumn(this.key, this.label, {this.dropTarget = true});
  final String key, label;

  /// Overdue is where late tasks are, never where one is sent.
  final bool dropTarget;
}

/// What moving a card to a column does to the grouped field.
sealed class KanbanMove {
  const KanbanMove();
}

class PatchMove extends KanbanMove {
  const PatchMove(this.patch);
  final Map<String, dynamic> patch;
}

class DayMove extends KanbanMove {
  const DayMove(this.day);
  final DateTime? day;
}

class CompleteMove extends KanbanMove {
  const CompleteMove();
}

class ReopenMove extends KanbanMove {
  const ReopenMove([this.then]);
  final Map<String, dynamic>? then;
}

class PickDayMove extends KanbanMove {
  const PickDayMove();
}

class NoMove extends KanbanMove {
  const NoMove();
}

const _statusColumns = [
  KanbanColumn('todo', 'To do'),
  KanbanColumn('in_progress', 'On it'),
  KanbanColumn('done', 'Done'),
];
const _dueColumns = [
  KanbanColumn('overdue', 'Overdue', dropTarget: false),
  KanbanColumn('today', 'Today'),
  KanbanColumn('tomorrow', 'Tomorrow'),
  KanbanColumn('week', 'This week'),
  KanbanColumn('later', 'Later'),
  KanbanColumn('none', 'No date'),
];
const _priorityColumns = [
  KanbanColumn('urgent', 'Urgent'),
  KanbanColumn('high', 'High'),
  KanbanColumn('medium', 'Medium'),
  KanbanColumn('low', 'Low'),
];

List<KanbanColumn> columnsFor(
  KanbanGroup group,
  List<TaskItem> tasks,
  List<ProjectRef> projects,
) {
  switch (group) {
    case KanbanGroup.status:
      return _statusColumns;
    case KanbanGroup.due:
      return _dueColumns;
    case KanbanGroup.priority:
      return _priorityColumns;
    case KanbanGroup.project:
      final used = {for (final t in tasks) t.projectId};
      return [
        for (final p in projects)
          if (used.contains(p.id)) KanbanColumn(p.id, p.name),
        const KanbanColumn(noProjectKey, 'No project'),
      ];
  }
}

String columnOf(TaskItem t, KanbanGroup group) => switch (group) {
      KanbanGroup.status =>
        t.isDone ? 'done' : (t.status == 'in_progress' ? 'in_progress' : 'todo'),
      KanbanGroup.due => t.dueBucket,
      KanbanGroup.priority => t.priority,
      KanbanGroup.project => t.projectId ?? noProjectKey,
    };

/// A finished task whose day has passed would only crowd Overdue.
List<TaskItem> visibleTasks(List<TaskItem> tasks, KanbanGroup group) =>
    group == KanbanGroup.due
        ? [for (final t in tasks) if (!(t.isDone && t.isOverdue)) t]
        : tasks;

/// The cards Show keeps: finished ones only while [done], a bot's only
/// while [botMade]. The same list when nothing is cut.
List<TaskItem> kanbanShown(List<TaskItem> tasks,
        {required bool done, required bool botMade}) =>
    done && botMade
        ? tasks
        : [
            for (final t in tasks)
              if ((done || !t.isDone) && (botMade || t.createdByBot == null)) t,
          ];

KanbanMove moveFor(KanbanGroup group, String key, TaskItem from,
    {DateTime? today}) {
  switch (group) {
    case KanbanGroup.status:
      if (key == 'done') return const CompleteMove();
      final status = key == 'in_progress' ? 'in_progress' : 'todo';
      if (from.isDone) {
        return ReopenMove(status == 'todo' ? null : {'status': status});
      }
      return PatchMove({'status': status});
    case KanbanGroup.due:
      final now = today ?? appToday();
      return switch (key) {
        'today' => DayMove(now),
        'tomorrow' => DayMove(now.add(const Duration(days: 1))),
        'none' => const DayMove(null),
        'week' || 'later' => const PickDayMove(),
        _ => const NoMove(),
      };
    case KanbanGroup.project:
      return PatchMove({'project_id': key == noProjectKey ? null : key});
    case KanbanGroup.priority:
      return PatchMove({'priority': key});
  }
}
