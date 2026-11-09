import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../board/tasks/task_dates.dart';
import '../../board/tasks/task_models.dart';
import '../../board/tasks/task_repo.dart';
import '../../theme/tokens.dart';
import '../web_mark.dart';

/// The tasks a chat card shows, by id, in the order asked (a deleted one is
/// simply not there); reloaded whenever a task changes anywhere.
final cardTasksProvider = taskListProvider;

String cardQuery(List<String> ids) => 'ids=${ids.join(',')}';

Color _dueColor(String bucket) => switch (bucket) {
      'overdue' => Tokens.dueLate,
      'today' => Tokens.dueToday,
      'tomorrow' => Tokens.dueTomorrow,
      _ => Tokens.dueLater,
    };

const _priorityWords = {'urgent': 'Urgent', 'high': 'High'};

/// A task's quiet facts on a chat card: its due in the account's words, priority,
/// project and the web mark.
class TaskFacts extends ConsumerWidget {
  const TaskFacts({super.key, required this.task});
  final TaskItem task;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final projects = ref.watch(taskProjectsProvider).valueOrNull ?? const [];
    final project = [
      for (final p in projects)
        if (p.id == task.projectId) p.name
    ];
    final due = dueWords(task.dueDate);
    const faint = TextStyle(color: Tokens.textFaint, fontSize: Tokens.fsCaption);
    return Wrap(
      spacing: Tokens.space2,
      runSpacing: 2,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: [
        if (due.isNotEmpty)
          Text(due,
              style: TextStyle(
                  color: task.isDone ? Tokens.textFaint : _dueColor(task.dueBucket),
                  fontSize: Tokens.fsCaption)),
        if (_priorityWords[task.priority] != null)
          Text(_priorityWords[task.priority]!,
              style: TextStyle(
                  color: task.priority == 'urgent'
                      ? Tokens.prioUrgent
                      : Tokens.prioHigh,
                  fontSize: Tokens.fsCaption)),
        if (project.isNotEmpty)
          Row(mainAxisSize: MainAxisSize.min, children: [
            const Icon(Icons.folder_outlined, size: 12, color: Tokens.textFaint),
            const SizedBox(width: 2),
            Text(project.first, style: faint),
          ]),
        if (task.tainted) const WebMark(),
      ],
    );
  }
}
