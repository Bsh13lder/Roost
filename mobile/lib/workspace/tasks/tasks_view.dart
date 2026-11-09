import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../board/tasks/kanban_view.dart';
import 'filter_bar.dart';
import 'task_list.dart';
import 'work_projects.dart';

/// The Workspace's Tasks: one row of filter chips over every open task in
/// day sections (or the Kanban). The title, layout menu and ⋯ sit in the
/// top bar (`TasksTitle`, `TasksActions`). The bottom bar's text narrows
/// the rows as you type.
class TasksView extends ConsumerWidget {
  const TasksView({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    if (ref.watch(workLayoutProvider) == TaskLayout.kanban) {
      return const KanbanView();
    }
    return const Column(children: [
      FilterBar(),
      Expanded(child: TaskList()),
    ]);
  }
}
