import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../theme/tokens.dart';
import '../../workspace/show_toggles.dart';
import 'kanban_groups.dart';
import 'task_actions.dart';
import 'task_dates.dart';
import 'task_drawer.dart';
import 'task_models.dart';
import 'task_repo.dart';
import 'task_row.dart' show priorityColor;

final kanbanGroupProvider =
    StateProvider<KanbanGroup>((_) => KanbanGroup.status);

/// The Tasks Kanban: columns side by side (swipe across), cards you open, and
/// "Move to…" in place of dragging. Show (in the top bar) hides finished
/// and bot-made cards for the Kanban alone.
class KanbanView extends ConsumerWidget {
  const KanbanView({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final group = ref.watch(kanbanGroupProvider);
    final tasks = ref.watch(kanbanTasksProvider);
    final projects = ref.watch(taskProjectsProvider).value ?? const [];
    final show = ref.watch(screenTogglesProvider(screenKanban));
    return Column(children: [
      _GroupChips(group: group),
      Expanded(
        child: tasks.when(
          loading: () => const Center(child: CircularProgressIndicator()),
          error: (e, _) => Center(
            child: TextButton(
              onPressed: () => ref.invalidate(kanbanTasksProvider),
              child: Text('$e\nTry again', textAlign: TextAlign.center),
            ),
          ),
          data: (all) {
            final list = visibleTasks(
                kanbanShown(all, done: show.done, botMade: show.botMade), group);
            final columns = columnsFor(group, list, projects);
            return RefreshIndicator(
              onRefresh: () async => ref.invalidate(kanbanTasksProvider),
              child: ListView(
                scrollDirection: Axis.horizontal,
                padding: const EdgeInsets.all(Tokens.space2),
                children: [
                  for (final c in columns)
                    _Column(
                      column: c,
                      group: group,
                      columns: columns,
                      tasks: [
                        for (final t in list)
                          if (columnOf(t, group) == c.key) t,
                      ],
                    ),
                ],
              ),
            );
          },
        ),
      ),
    ]);
  }
}

class _GroupChips extends ConsumerWidget {
  const _GroupChips({required this.group});
  final KanbanGroup group;

  @override
  Widget build(BuildContext context, WidgetRef ref) => SizedBox(
        height: 44,
        child: ListView(
          scrollDirection: Axis.horizontal,
          padding: const EdgeInsets.symmetric(horizontal: Tokens.space3),
          children: [
            for (final g in KanbanGroup.values)
              Padding(
                padding: const EdgeInsets.only(right: Tokens.space2),
                child: ChoiceChip(
                  key: Key('group-${g.name}'),
                  label: Text(g.label),
                  selected: g == group,
                  onSelected: (_) =>
                      ref.read(kanbanGroupProvider.notifier).state = g,
                ),
              ),
          ],
        ),
      );
}

class _Column extends StatelessWidget {
  const _Column({
    required this.column,
    required this.group,
    required this.columns,
    required this.tasks,
  });

  final KanbanColumn column;
  final KanbanGroup group;
  final List<KanbanColumn> columns;
  final List<TaskItem> tasks;

  @override
  Widget build(BuildContext context) {
    return Container(
      key: Key('column-${column.key}'),
      width: 260,
      margin: const EdgeInsets.only(right: Tokens.space2),
      decoration: BoxDecoration(
        color: Tokens.panel,
        borderRadius: BorderRadius.circular(Tokens.radiusMd),
        border: Border.all(color: Tokens.border),
      ),
      child: Column(children: [
        Padding(
          padding: const EdgeInsets.all(Tokens.space3),
          child: Row(children: [
            Expanded(
              child: Text(column.label,
                  style: const TextStyle(fontWeight: FontWeight.w600)),
            ),
            Text('${tasks.length}',
                style: const TextStyle(color: Tokens.textSecondary)),
          ]),
        ),
        Expanded(
          child: tasks.isEmpty
              ? const Center(
                  child: Text('Nothing here.',
                      style: TextStyle(color: Tokens.textFaint)))
              : ListView(
                  padding: const EdgeInsets.symmetric(horizontal: Tokens.space2),
                  children: [
                    for (final t in tasks)
                      _Card(task: t, group: group, columns: columns),
                  ],
                ),
        ),
      ]),
    );
  }
}

class _Card extends StatelessWidget {
  const _Card({required this.task, required this.group, required this.columns});

  final TaskItem task;
  final KanbanGroup group;
  final List<KanbanColumn> columns;

  Future<void> _moveTo(BuildContext context) async {
    final actions = TaskActions(context);
    final here = columnOf(task, group);
    final target = await showModalBottomSheet<KanbanColumn>(
      context: context,
      showDragHandle: true,
      builder: (c) => SafeArea(
        child: ListView(shrinkWrap: true, children: [
          const Padding(
            padding: EdgeInsets.symmetric(horizontal: Tokens.space4),
            child: Text('Move to…',
                style: TextStyle(
                    fontSize: Tokens.fsHeading, fontWeight: FontWeight.w600)),
          ),
          for (final col in columns)
            if (col.dropTarget && col.key != here)
              ListTile(
                key: Key('move-${col.key}'),
                title: Text(col.label),
                onTap: () => Navigator.pop(c, col),
              ),
        ]),
      ),
    );
    if (target != null) {
      await actions.moveCard(task, group, target.key, target.label);
    }
  }

  @override
  Widget build(BuildContext context) {
    final due = dueWords(task.dueDate);
    return Card(
      color: Tokens.raised,
      margin: const EdgeInsets.only(bottom: Tokens.space2),
      child: InkWell(
        borderRadius: BorderRadius.circular(Tokens.radiusMd),
        onTap: () => openTaskDrawer(context, task.id),
        onLongPress: () => _moveTo(context),
        child: Padding(
          padding: const EdgeInsets.fromLTRB(
              Tokens.space3, Tokens.space2, Tokens.space1, Tokens.space2),
          child: Row(children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(task.title,
                      maxLines: 3,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        decoration:
                            task.isDone ? TextDecoration.lineThrough : null,
                        color: task.isDone ? Tokens.textFaint : Tokens.text,
                      )),
                  if (due.isNotEmpty || task.priority != 'medium')
                    Wrap(spacing: Tokens.space2, children: [
                      if (due.isNotEmpty)
                        Text(due,
                            style: TextStyle(
                                fontSize: Tokens.fsCaption,
                                color: task.isOverdue
                                    ? Tokens.danger
                                    : Tokens.textSecondary)),
                      if (task.priority != 'medium')
                        Text(task.priority,
                            style: TextStyle(
                                fontSize: Tokens.fsCaption,
                                color: priorityColor(task.priority) ==
                                        Colors.transparent
                                    ? Tokens.textSecondary
                                    : priorityColor(task.priority))),
                    ]),
                ],
              ),
            ),
            IconButton(
              key: Key('move-card-${task.id}'),
              tooltip: 'Move to…',
              icon: const Icon(Icons.drive_file_move_outline, size: 20),
              onPressed: () => _moveTo(context),
            ),
          ]),
        ),
      ),
    );
  }
}
