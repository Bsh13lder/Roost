import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../api/models.dart';
import '../../board/tasks/task_drawer.dart';
import '../../board/tasks/task_models.dart';
import '../../board/tasks/task_repo.dart';
import '../../theme/tokens.dart';
import 'card_base.dart';
import 'task_card_parts.dart';

const tasksGoneText = 'These tasks are gone.';

/// A long task card shows this many rows and folds the rest (owner,
/// 2026-10-29: "show first 4-5 and after toggle").
const taskCardsShown = 5;
const taskCardsShowLess = 'Show less';
String taskCardsShowMore(int count) => 'Show $count more';

/// A task_cards body (roost/tasks/cards.py), or null for anything else.
({List<String> ids, String verb, int more})? parseTaskCards(String body) {
  final d = decodeBody(body);
  final ids = [
    for (final id in (d?['task_ids'] is List ? d!['task_ids'] as List : const []))
      if (id is String) id
  ];
  if (ids.isEmpty) return null;
  final verb = str(d?['verb']);
  final more = d?['more'];
  return (
    ids: ids,
    verb: const {'added', 'listed'}.contains(verb) ? verb : 'tasks',
    more: more is int && more > 0 ? more : 0,
  );
}

String _heading(String verb, int count) => verb == 'added'
    ? (count == 1 ? 'Added a task' : 'Added $count tasks')
    : 'Your tasks';

/// The tasks a bot added or listed in your chat (2026-10-26, owner: "when I
/// ask task for it showed me beautiful"): one quiet card of task rows under
/// its reply. Tick one to finish it, tap it to open its drawer.
class TaskCardsCard extends ConsumerWidget {
  const TaskCardsCard({super.key, required this.message});
  final Message message;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final data = parseTaskCards(message.body);
    if (data == null) return const SizedBox.shrink();
    final tasks = ref.watch(cardTasksProvider(cardQuery(data.ids)));
    return CardFrame(
      title: _heading(data.verb, data.ids.length),
      children: [
        tasks.when(
          loading: () => const Text('Loading…',
              style: TextStyle(color: Tokens.textFaint)),
          error: (e, _) => Text('$e', style: const TextStyle(color: Tokens.dangerText)),
          data: (list) => list.isEmpty
              ? const Text(tasksGoneText,
                  style: TextStyle(color: Tokens.textFaint))
              : _TaskLines(tasks: list),
        ),
        if (data.more > 0)
          Padding(
            padding: const EdgeInsets.only(top: Tokens.space2),
            child: Text('and ${data.more} more on the Board',
                style: const TextStyle(
                    color: Tokens.textFaint, fontSize: Tokens.fsLabel)),
          ),
      ],
    );
  }
}

/// The first [taskCardsShown] rows, and a toggle for the rest when there are more.
class _TaskLines extends StatefulWidget {
  const _TaskLines({required this.tasks});
  final List<TaskItem> tasks;

  @override
  State<_TaskLines> createState() => _TaskLinesState();
}

class _TaskLinesState extends State<_TaskLines> {
  bool _open = false;

  @override
  Widget build(BuildContext context) {
    final all = widget.tasks;
    final hidden = all.length - taskCardsShown;
    final shown = _open || hidden <= 0 ? all : all.take(taskCardsShown);
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      for (final t in shown) _TaskLine(key: ValueKey(t.id), task: t),
      if (hidden > 0)
        TextButton(
          key: const Key('task-cards-toggle'),
          onPressed: () => setState(() => _open = !_open),
          child: Text(_open ? taskCardsShowLess : taskCardsShowMore(hidden)),
        ),
    ]);
  }
}

class _TaskLine extends ConsumerStatefulWidget {
  const _TaskLine({super.key, required this.task});
  final TaskItem task;

  @override
  ConsumerState<_TaskLine> createState() => _TaskLineState();
}

class _TaskLineState extends ConsumerState<_TaskLine> {
  bool _busy = false;
  String? _problem;

  Future<void> _toggle() async {
    final repo = ref.read(taskRepoProvider);
    final t = widget.task;
    setState(() {
      _busy = true;
      _problem = null;
    });
    try {
      await (t.status == 'done' ? repo.reopen(t.id) : repo.complete(t.id));
      ref.invalidate(taskListProvider);
    } catch (e) {
      if (mounted) setState(() => _problem = '$e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = widget.task;
    final done = t.status == 'done';
    return InkWell(
      key: Key('task-card-${t.id}'),
      onTap: () => openTaskDrawer(context, t.id),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: Tokens.space1),
        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          IconButton(
            key: Key('task-tick-${t.id}'),
            tooltip: done ? 'Open “${t.title}” again' : 'Mark “${t.title}” done',
            onPressed: _busy || t.status == 'failed' ? null : _toggle,
            icon: Icon(done ? Icons.check_circle : Icons.radio_button_unchecked,
                color: done ? Tokens.ok : Tokens.textFaint),
          ),
          Expanded(
            child: Padding(
              padding: const EdgeInsets.only(top: Tokens.space2),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(t.title,
                    style: TextStyle(
                        fontSize: Tokens.fsBody,
                        color: t.isDone ? Tokens.textFaint : Tokens.text,
                        decoration: t.isDone ? TextDecoration.lineThrough : null)),
                TaskFacts(task: t),
                if (_problem != null)
                  Text(_problem!,
                      style: const TextStyle(
                          color: Tokens.dangerText, fontSize: Tokens.fsCaption)),
              ]),
            ),
          ),
        ]),
      ),
    );
  }
}
