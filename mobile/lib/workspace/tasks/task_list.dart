import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../board/common/widgets.dart';
import '../../board/tasks/offline/offline_store.dart';
import '../../board/tasks/offline/offline_sync.dart';
import '../../board/tasks/reschedule_sheet.dart';
import '../../board/tasks/task_actions.dart';
import '../../board/tasks/task_models.dart';
import '../../board/tasks/task_repo.dart';
import '../../theme/accent.dart';
import '../../theme/tokens.dart';
import '../workspace_state.dart';
import 'filter_store.dart';
import 'section_header.dart';
import 'task_sections.dart';
import 'tasks_data.dart';
import 'tasks_empty.dart';
import 'todo_meta.dart';
import 'todo_row.dart';
import 'work_projects.dart';

/// The rows in day sections (Overdue, Today, Tomorrow, each later day,
/// No date, Done), each folding with a tap on its header. Pull to refresh.
class TaskList extends ConsumerStatefulWidget {
  const TaskList({super.key});

  @override
  ConsumerState<TaskList> createState() => _TaskListState();
}

class _TaskListState extends ConsumerState<TaskList> {
  /// Rows finished a moment ago, hidden until the reload drops them.
  Set<String> _hidden = const {};

  void _completing(TaskItem t, Future<bool> result) {
    setState(() => _hidden = {..._hidden, t.id});
    result.then((ok) {
      if (!ok && mounted) setState(() => _hidden = _hidden.difference({t.id}));
    });
  }

  @override
  void initState() {
    super.initState();
    // O2: each open list loaded is kept for the offline tasks screen.
    ref.listenManual(taskListProvider(openTasksQuery), (_, next) {
      final open = next.valueOrNull;
      if (open != null && !next.isLoading) {
        ref.read(offlineTasksProvider.notifier).keep(open).ignore();
      }
    }, fireImmediately: true);
  }

  Future<void> _refresh() async {
    // Pull to refresh sends what waits from offline first (O7).
    await ref.read(offlineSyncProvider.notifier).sync();
    reloadTaskLists(ref);
    await ref.read(taskListProvider(openTasksQuery).future).catchError((_) => <TaskItem>[]);
  }

  @override
  Widget build(BuildContext context) {
    ref.listen(shownTasksProvider, (_, next) {
      if (!next.isLoading && next.hasValue && _hidden.isNotEmpty) setState(() => _hidden = const {});
    });
    final shown = ref.watch(shownTasksProvider);
    return shown.when(
      skipLoadingOnRefresh: true,
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => Center(
        child: TextButton(
          onPressed: () => reloadTaskLists(ref),
          child: Text('${errorText(e)}\nTry again', textAlign: TextAlign.center),
        ),
      ),
      data: (all) => RefreshIndicator(
        onRefresh: _refresh,
        child: _list([for (final t in all) if (!_hidden.contains(t.id)) t]),
      ),
    );
  }

  Widget _list(List<TaskItem> tasks) {
    final sections = sectionsOf(tasks);
    final folded = ref.watch(foldedSectionsProvider);
    final projects = {
      for (final p in ref.watch(workProjectsProvider).value ?? const <ProjectInfo>[])
        p.id: (name: p.name, color: p.color),
    };
    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.only(bottom: Tokens.space6),
      children: [
        if (sections.isEmpty)
          TasksEmpty(
            filter: ref.watch(taskFilterProvider),
            typed: ref.watch(workspaceQueryProvider),
            onClear: () => ref.read(taskFilterProvider.notifier).clear(),
          ),
        for (final s in sections)
          _SectionBlock(
            key: ValueKey('block-${s.key}'),
            section: s,
            folded: folded.contains(s.key),
            projects: projects,
            onCompleting: _completing,
          ),
      ],
    );
  }
}

class _SectionBlock extends ConsumerWidget {
  const _SectionBlock({
    super.key,
    required this.section,
    required this.folded,
    required this.projects,
    required this.onCompleting,
  });

  final TaskSection section;
  final bool folded;
  final Map<String, RowProject> projects;
  final void Function(TaskItem, Future<bool>) onCompleting;

  void _toggle(WidgetRef ref) {
    final n = ref.read(foldedSectionsProvider.notifier);
    final now = n.state;
    n.state = now.contains(section.key)
        ? now.difference({section.key})
        : {...now, section.key};
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final rows = Column(children: [
      for (final (i, t) in section.tasks.indexed) ...[
        if (i > 0) const Divider(height: 1, thickness: 1, indent: Tokens.rowIndent, color: Tokens.border),
        TodoRow(
          key: ValueKey('todo-${t.id}'),
          task: t,
          projects: projects,
          onCompleting: onCompleting,
        ),
      ],
    ]);
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      SectionHeader(
        key: Key('section-${section.key}'),
        section: section,
        folded: folded,
        onToggle: () => _toggle(ref),
        action: section.key == 'overdue' ? const _RescheduleAll() : null,
      ),
      ClipRect(
        child: AnimatedSize(
          duration: const Duration(milliseconds: 220),
          curve: Curves.easeInOut,
          alignment: Alignment.topCenter,
          child: folded ? const SizedBox(width: double.infinity) : rows,
        ),
      ),
    ]);
  }
}

/// Overdue's "Reschedule": every overdue task to one day, with Undo.
class _RescheduleAll extends StatelessWidget {
  const _RescheduleAll();

  @override
  Widget build(BuildContext context) => TextButton(
        key: const Key('reschedule-all'),
        style: TextButton.styleFrom(
          visualDensity: VisualDensity.compact,
          tapTargetSize: MaterialTapTargetSize.shrinkWrap,
        ),
        onPressed: () async {
          final actions = TaskActions(context);
          final c = await showRescheduleSheet(context, title: 'Reschedule all overdue');
          if (c != null) await actions.rescheduleAll(c);
        },
        child: Text('Reschedule',
            style: TextStyle(
                color: AccentColors.of(context).strong,
                fontSize: Tokens.fsLabel,
                fontWeight: FontWeight.w600)),
      );
}
