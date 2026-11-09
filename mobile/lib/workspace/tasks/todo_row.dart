import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../board/tasks/reschedule_sheet.dart';
import '../../board/tasks/task_actions.dart';
import '../../board/tasks/task_drawer.dart';
import '../../board/tasks/task_models.dart';
import '../../board/tasks/task_row.dart' show openProjectPage, showTaskMenu;
import '../../live/live_connection.dart';
import '../../theme/tokens.dart';
import 'todo_check.dart';
import 'todo_meta.dart';

/// One task the Todoist way: the priority check, the title (two lines at
/// most) and a small meta line. Swipe right to finish, left to reschedule;
/// tap opens the task, long-press the menu.
class TodoRow extends ConsumerWidget {
  const TodoRow({
    super.key,
    required this.task,
    required this.projects,
    required this.onCompleting,
  });

  final TaskItem task;
  final Map<String, RowProject> projects;

  /// Called as a swipe or tap finishes the task, with whether it worked,
  /// so the list can hide the row at once and bring it back on a failure.
  final void Function(TaskItem task, Future<bool> result) onCompleting;

  void _complete(BuildContext context) {
    onCompleting(task, TaskActions(context).done(task));
  }

  Future<bool> _reschedule(BuildContext context) async {
    final actions = TaskActions(context);
    final c = await showRescheduleSheet(context);
    if (c != null) await actions.reschedule(task, c);
    return false;
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final row = _body(context, ref);
    if (task.isDone) return row;
    return Dismissible(
      key: ValueKey('row-${task.id}'),
      background: const _SwipeBack(done: true),
      secondaryBackground: const _SwipeBack(done: false),
      confirmDismiss: (dir) async => dir == DismissDirection.startToEnd
          ? true
          : _reschedule(context),
      onDismissed: (_) => _complete(context),
      child: row,
    );
  }

  Widget _body(BuildContext context, WidgetRef ref) {
    final t = task;
    final project = t.projectId == null ? null : projects[t.projectId];
    final maker = t.createdByBot == null
        ? null
        : ref.watch(liveProvider.select((s) => s.bots[t.createdByBot]?.name));
    final meta = TodoMeta(
      task: t,
      project: project,
      maker: maker,
      onProject: () => openProjectPage(context, t.projectId!),
    );
    return Material(
      key: task.isDone ? ValueKey('row-${task.id}') : null,
      color: Tokens.bg,
      child: InkWell(
        onTap: () => openTaskDrawer(context, t.id),
        onLongPress: () => showTaskMenu(context, ref, t),
        child: ConstrainedBox(
          constraints: const BoxConstraints(minHeight: Tokens.rowMinHeight),
          child: Padding(
            padding: const EdgeInsets.fromLTRB(
                Tokens.space2, Tokens.space2, Tokens.space4, Tokens.space2),
            child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
              TodoCheck(
                key: Key('check-${t.id}'),
                priority: t.priority,
                done: t.isDone,
                onChanged: () => t.isDone
                    ? TaskActions(context).reopen(t)
                    : _complete(context),
              ),
              const SizedBox(width: Tokens.space1),
              Expanded(child: _texts(t, meta)),
            ]),
          ),
        ),
      ),
    );
  }

  Widget _texts(TaskItem t, TodoMeta meta) => Padding(
        padding: const EdgeInsets.only(top: Tokens.space2),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(
            t.title,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              fontSize: Tokens.fsRow,
              height: 1.3,
              color: t.isDone ? Tokens.textFaint : Tokens.text,
              decoration: t.isDone ? TextDecoration.lineThrough : null,
            ),
          ),
          if (!meta.isEmpty) ...[
            const SizedBox(height: Tokens.space1),
            meta,
          ],
        ]),
      );
}

/// What shows under a row as it slides: green with a tick to finish,
/// violet with a clock to move.
class _SwipeBack extends StatelessWidget {
  const _SwipeBack({required this.done});

  final bool done;

  @override
  Widget build(BuildContext context) => ColoredBox(
        color: done ? Tokens.swipeDone : Tokens.swipeLater,
        child: Align(
          alignment: done ? Alignment.centerLeft : Alignment.centerRight,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: Tokens.space6),
            child: Row(mainAxisSize: MainAxisSize.min, children: [
              TweenAnimationBuilder<double>(
                tween: Tween(begin: 0.5, end: 1),
                duration: const Duration(milliseconds: 220),
                curve: Curves.easeOutBack,
                builder: (_, v, child) => Transform.scale(scale: v, child: child),
                child: Icon(done ? Icons.check_circle : Icons.schedule,
                    color: Tokens.onAccent),
              ),
              const SizedBox(width: Tokens.space2),
              Text(done ? 'Done' : 'Reschedule',
                  style: const TextStyle(
                      color: Tokens.onAccent, fontWeight: FontWeight.w600)),
            ]),
          ),
        ),
      );
}
