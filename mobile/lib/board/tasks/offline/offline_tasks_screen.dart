import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../theme/tokens.dart';
import '../../../workspace/tasks/section_header.dart';
import '../../../workspace/tasks/task_sections.dart';
import '../task_models.dart';
import 'offline_parts.dart';
import 'offline_queue.dart';
import 'offline_store.dart';
import 'offline_sync.dart';

/// Where the offline tasks screen lives; opened from the offline screen.
const offlineTasksPath = '/offline-tasks';

const offlineTasksTitle = 'My tasks';
const offlineTasksLine = 'Offline. Changes sync when Roost is back.';
const waitingTitle = 'Waiting to sync';
const _waitingKey = 'waiting';

/// Your tasks with no connection (O1): the kept open list, the lines added
/// here waiting to sync, a tick on any of them, and the lines that could
/// not sync. Pull to refresh tries to sync.
class OfflineTasksScreen extends ConsumerStatefulWidget {
  const OfflineTasksScreen({super.key});

  @override
  ConsumerState<OfflineTasksScreen> createState() =>
      _OfflineTasksScreenState();
}

class _OfflineTasksScreenState extends ConsumerState<OfflineTasksScreen> {
  Set<String> _folded = const {};

  void _toggle(String key) => setState(() => _folded = _folded.contains(key)
      ? _folded.difference({key})
      : {..._folded, key});

  Future<void> _tick(String id, String title) =>
      ref.read(offlineTasksProvider.notifier).done(id, title: title);

  @override
  Widget build(BuildContext context) {
    final tasks = ref.watch(offlineTasksProvider);
    return Scaffold(
      appBar: AppBar(
        title: const Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(offlineTasksTitle),
            Text(offlineTasksLine,
                style: TextStyle(
                    color: Tokens.textSecondary, fontSize: Tokens.fsLabel)),
          ],
        ),
      ),
      body: SafeArea(
        child: Column(children: [
          Expanded(
            child: tasks.when(
              skipLoadingOnRefresh: true,
              skipLoadingOnReload: true,
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (e, _) => const Center(child: Text(offlineUnreadable)),
              data: (t) => RefreshIndicator(
                onRefresh: () => ref.read(offlineSyncProvider.notifier).sync(),
                child: _list(t),
              ),
            ),
          ),
          OfflineAddLine(
            onAdd: (text) => ref.read(offlineTasksProvider.notifier).add(text),
          ),
        ]),
      ),
    );
  }

  Widget _list(OfflineTasks t) {
    final waiting = t.waitingAdds;
    final ticked = t.tickedIds;
    final sections = sectionsOf(keptWithTicks(t));
    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.only(bottom: Tokens.space6),
      children: [
        if (t.notes.isNotEmpty)
          OfflineNotes(
            notes: t.notes,
            onDismiss: () =>
                ref.read(offlineTasksProvider.notifier).clearNotes(),
          ),
        if (waiting.isEmpty && sections.isEmpty) const OfflineEmpty(),
        if (waiting.isNotEmpty)
          ..._section(
            TaskSection(
              key: _waitingKey,
              title: waitingTitle,
              tasks: [for (final a in waiting) _asTask(a, ticked)],
            ),
          ),
        for (final s in sections) ..._section(s),
      ],
    );
  }

  /// A waiting add drawn as a row: its raw line is its title (O3).
  TaskItem _asTask(QueuedAdd a, Set<String> ticked) => TaskItem(
        id: a.clientId,
        title: a.text,
        status: ticked.contains(a.clientId) ? 'done' : 'todo',
        priority: 'medium',
      );

  List<Widget> _section(TaskSection s) => [
        SectionHeader(
          key: Key('offline-section-${s.key}'),
          section: s,
          folded: _folded.contains(s.key),
          onToggle: () => _toggle(s.key),
        ),
        if (!_folded.contains(s.key))
          for (final task in s.tasks)
            OfflineRow(
              key: ValueKey('offline-row-${task.id}'),
              task: task,
              onTick: () => _tick(task.id, task.title),
            ),
      ];
}
