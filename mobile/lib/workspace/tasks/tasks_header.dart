import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../board/money/money_tab.dart';
import '../../board/projects/projects_tab.dart';
import '../../theme/tokens.dart';
import '../show_toggles.dart';
import '../workspace_state.dart';
import 'filter_store.dart';
import 'tasks_data.dart';
import 'work_projects.dart';

/// The top bar's title on Tasks: "Tasks" and, small beside it, how many
/// tasks the list shows now.
class TasksTitle extends ConsumerWidget {
  const TasksTitle({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final layout = ref.watch(workLayoutProvider);
    final count = ref.watch(shownTasksProvider).valueOrNull?.length;
    return Row(
      crossAxisAlignment: CrossAxisAlignment.baseline,
      textBaseline: TextBaseline.alphabetic,
      children: [
        Text(layout == TaskLayout.kanban ? 'Kanban' : 'Tasks',
            style: const TextStyle(
                fontSize: Tokens.fsTitle, fontWeight: FontWeight.w700)),
        if (layout == TaskLayout.list && count != null) ...[
          const SizedBox(width: Tokens.space2),
          Text('$count',
              key: const Key('tasks-count'),
              style: const TextStyle(
                  fontSize: Tokens.fsBody, color: Tokens.textSecondary)),
        ],
      ],
    );
  }
}

/// The top bar's buttons on Tasks: Show (Made by bots on the list; Done and
/// Made by bots on the Kanban, kept apart), the layout menu
/// (List · Kanban · Calendar) and ⋯ (Clear filters, All projects, All money).
class TasksActions extends ConsumerWidget {
  const TasksActions({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final layout = ref.watch(workLayoutProvider);
    return Row(mainAxisSize: MainAxisSize.min, children: [
      if (layout == TaskLayout.list)
        const ShowMenuButton(screen: screenTasks, options: [ShowToggle.botMade]),
      if (layout == TaskLayout.kanban)
        const ShowMenuButton(
            screen: screenKanban, options: [ShowToggle.done, ShowToggle.botMade]),
      const _LayoutMenu(),
      const _MoreMenu(),
    ]);
  }
}

class _LayoutMenu extends ConsumerWidget {
  const _LayoutMenu();

  static const _items = [
    ('list', 'List', Icons.view_list_outlined),
    ('kanban', 'Kanban', Icons.view_kanban_outlined),
    ('calendar', 'Calendar', Icons.calendar_month_outlined),
  ];

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final layout = ref.watch(workLayoutProvider);
    return PopupMenuButton<String>(
      key: const Key('layout-menu'),
      tooltip: 'Layout',
      icon: Icon(layout == TaskLayout.kanban
          ? Icons.view_kanban_outlined
          : Icons.view_list_outlined),
      onSelected: (v) {
        if (v == 'calendar') {
          ref.read(workspaceSectionProvider.notifier).state = WorkspaceSection.calendar;
          return;
        }
        ref.read(workLayoutProvider.notifier).state = TaskLayout.values.byName(v);
      },
      itemBuilder: (_) => [
        for (final (id, label, icon) in _items)
          PopupMenuItem(
            value: id,
            child: Row(children: [
              Icon(icon, size: 20, color: Tokens.textSecondary),
              const SizedBox(width: Tokens.space3),
              Expanded(child: Text(label)),
              if (id == layout.name) const Icon(Icons.check, size: 18),
            ]),
          ),
      ],
    );
  }
}

class _MoreMenu extends ConsumerWidget {
  const _MoreMenu();

  void _push(BuildContext context, String title, Widget body) =>
      Navigator.of(context).push(MaterialPageRoute<void>(
        builder: (_) => Scaffold(
          backgroundColor: Tokens.bg,
          appBar: AppBar(title: Text(title)),
          body: body,
        ),
      ));

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final filtered = !ref.watch(taskFilterProvider).isEmpty;
    return PopupMenuButton<String>(
      key: const Key('tasks-more'),
      tooltip: 'More',
      icon: const Icon(Icons.more_horiz),
      onSelected: (v) => switch (v) {
        'clear' => ref.read(taskFilterProvider.notifier).clear(),
        'projects' => _push(context, 'All projects', const ProjectsTab()),
        _ => _push(context, 'All money', const MoneyTab()),
      },
      itemBuilder: (_) => [
        PopupMenuItem(value: 'clear', enabled: filtered, child: const Text('Clear filters')),
        const PopupMenuDivider(),
        const PopupMenuItem(value: 'projects', child: Text('All projects')),
        const PopupMenuItem(value: 'money', child: Text('All money')),
      ],
    );
  }
}
