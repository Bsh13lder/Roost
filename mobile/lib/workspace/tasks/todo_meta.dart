import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../../board/common/widgets.dart';
import '../../board/tasks/task_dates.dart';
import '../../board/tasks/task_models.dart';
import '../../theme/tokens.dart';

/// A project as a row shows it: its name and colour.
typedef RowProject = ({String name, String? color});

/// "Today", "Tomorrow 09:00", "Mon 20 Oct" from the server's `due_bucket`
/// (the account's day) and the due itself; empty with no due.
String rowDueWords(TaskItem t) {
  final due = readDue(t.dueDate);
  if (due == null) return '';
  final word = switch (t.dueBucket) {
    'today' => 'Today',
    'tomorrow' => 'Tomorrow',
    _ => DateFormat('EEE d MMM').format(due.day),
  };
  return due.clock == null ? word : '$word ${due.clock}';
}

/// Late red, today green, tomorrow violet, later grey.
Color dueTone(TaskItem t) => switch (t.dueBucket) {
      'overdue' when !t.isDone => Tokens.dueLate,
      'today' => Tokens.dueToday,
      'tomorrow' => Tokens.dueTomorrow,
      _ => Tokens.dueLater,
    };

/// The small line under a title: due in colour, a repeat mark, steps done,
/// comments, the bot that made it, and the project with its dot on the
/// right. Null when there is nothing.
class TodoMeta extends StatelessWidget {
  const TodoMeta({super.key, required this.task, this.project, this.onProject, this.maker});

  final TaskItem task;
  final RowProject? project;
  final VoidCallback? onProject;

  /// The name of the bot that made the task; null for yours.
  final String? maker;

  bool get isEmpty =>
      rowDueWords(task).isEmpty &&
      task.repeatText == null &&
      task.steps.isEmpty &&
      task.commentCount == 0 &&
      maker == null &&
      project == null;

  @override
  Widget build(BuildContext context) {
    final t = task;
    final due = rowDueWords(t);
    final items = <Widget>[
      if (due.isNotEmpty)
        _Bit(key: Key('due-${t.id}'), icon: Icons.event_outlined, text: due, color: dueTone(t)),
      if (t.repeatText != null)
        Tooltip(
          key: Key('repeat-${t.id}'),
          message: t.repeatText!,
          child: Icon(Icons.repeat, size: Tokens.metaIcon, color: dueTone(t)),
        ),
      if (t.steps.isNotEmpty)
        _Bit(
          key: Key('steps-${t.id}'),
          icon: Icons.checklist_rtl,
          text: '${t.stepsDone}/${t.steps.length}',
          color: Tokens.textSecondary,
        ),
      if (t.commentCount > 0)
        _Bit(
          key: Key('comments-${t.id}'),
          icon: Icons.chat_bubble_outline,
          text: '${t.commentCount}',
          color: Tokens.textSecondary,
        ),
      if (maker != null)
        Flexible(
          child: _Bit(
            key: Key('maker-${t.id}'),
            icon: Icons.smart_toy_outlined,
            text: maker!,
            color: Tokens.textFaint,
          ),
        ),
    ];
    return Row(children: [
      for (final (i, w) in items.indexed) ...[
        if (i > 0) const SizedBox(width: Tokens.space3),
        w,
      ],
      const Spacer(),
      if (project != null) _ProjectTag(id: t.id, project: project!, onTap: onProject),
    ]);
  }
}

class _Bit extends StatelessWidget {
  const _Bit({super.key, required this.icon, required this.text, required this.color});

  final IconData icon;
  final String text;
  final Color color;

  @override
  Widget build(BuildContext context) => Row(mainAxisSize: MainAxisSize.min, children: [
        Icon(icon, size: Tokens.metaIcon, color: color),
        const SizedBox(width: Tokens.space1),
        Flexible(
          child: Text(text,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(fontSize: Tokens.fsCaption, color: color)),
        ),
      ]);
}

/// The project's name then its dot, right-aligned; a tap opens the project.
class _ProjectTag extends StatelessWidget {
  const _ProjectTag({required this.id, required this.project, this.onTap});

  final String id;
  final RowProject project;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) => InkWell(
        key: Key('pill-$id'),
        onTap: onTap,
        borderRadius: BorderRadius.circular(Tokens.radiusSm),
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 130),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: Tokens.space1),
            child: Row(mainAxisSize: MainAxisSize.min, children: [
              Flexible(
                child: Text(project.name,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                        fontSize: Tokens.fsCaption, color: Tokens.textSecondary)),
              ),
              const SizedBox(width: Tokens.space1),
              Container(
                width: Tokens.dotSize,
                height: Tokens.dotSize,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: project.color == null ? Tokens.textFaint : hexColor(project.color),
                ),
              ),
            ]),
          ),
        ),
      );
}
