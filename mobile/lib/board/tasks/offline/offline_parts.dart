import 'package:flutter/material.dart';

import '../../../theme/tokens.dart';
import '../../../workspace/tasks/todo_check.dart';
import '../task_models.dart';

const offlineUnreadable = "Your kept tasks couldn't be read.";
const offlineEmptyLine =
    'No tasks kept on this phone yet. Open Tasks once while Roost is '
    'reachable, and they stay here for times like this.';
const offlineAddHint = 'Add a task';
const offlineNotesDismiss = 'OK';

/// One task row: the round check and the title. A done row (ticked here,
/// waiting to sync) is struck through and its check does nothing.
class OfflineRow extends StatelessWidget {
  const OfflineRow({super.key, required this.task, required this.onTick});

  final TaskItem task;
  final VoidCallback onTick;

  @override
  Widget build(BuildContext context) {
    final done = task.isDone;
    return ConstrainedBox(
      constraints: const BoxConstraints(minHeight: Tokens.rowMinHeight),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: Tokens.space4),
        child: Row(children: [
          TodoCheck(
            key: Key('offline-check-${task.id}'),
            priority: task.priority,
            done: done,
            onChanged: done ? () {} : onTick,
          ),
          const SizedBox(width: Tokens.space3),
          Expanded(
            child: Text(
              task.title,
              style: TextStyle(
                color: done ? Tokens.textSecondary : Tokens.text,
                decoration: done ? TextDecoration.lineThrough : null,
              ),
            ),
          ),
        ]),
      ),
    );
  }
}

/// The "Couldn't sync" lines (O7), each listed until you dismiss them.
class OfflineNotes extends StatelessWidget {
  const OfflineNotes({super.key, required this.notes, required this.onDismiss});

  final List<String> notes;
  final VoidCallback onDismiss;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.all(Tokens.space3),
      padding: const EdgeInsets.all(Tokens.space3),
      decoration: BoxDecoration(
        color: Tokens.warnTint,
        borderRadius: BorderRadius.circular(Tokens.radiusMd),
      ),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              for (final n in notes)
                Text(n, style: const TextStyle(color: Tokens.warnText)),
            ],
          ),
        ),
        TextButton(
          key: const Key('offline-notes-dismiss'),
          onPressed: onDismiss,
          child: const Text(offlineNotesDismiss),
        ),
      ]),
    );
  }
}

class OfflineEmpty extends StatelessWidget {
  const OfflineEmpty({super.key});

  @override
  Widget build(BuildContext context) => const Padding(
        key: Key('offline-empty'),
        padding: EdgeInsets.all(Tokens.space6),
        child: Text(offlineEmptyLine,
            textAlign: TextAlign.center,
            style: TextStyle(color: Tokens.textSecondary)),
      );
}

/// The add line: a typed quick line is kept as typed and read by Roost when
/// it syncs (O3, O4).
class OfflineAddLine extends StatefulWidget {
  const OfflineAddLine({super.key, required this.onAdd});

  final Future<void> Function(String text) onAdd;

  @override
  State<OfflineAddLine> createState() => _OfflineAddLineState();
}

class _OfflineAddLineState extends State<OfflineAddLine> {
  final _text = TextEditingController();

  @override
  void dispose() {
    _text.dispose();
    super.dispose();
  }

  Future<void> _add() async {
    final line = _text.text.trim();
    if (line.isEmpty) return;
    _text.clear();
    await widget.onAdd(line);
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.fromLTRB(
          Tokens.space3, Tokens.space2, Tokens.space2, Tokens.space2),
      decoration: const BoxDecoration(
        color: Tokens.panel,
        border: Border(top: BorderSide(color: Tokens.border)),
      ),
      child: Row(children: [
        Expanded(
          child: TextField(
            key: const Key('offline-add-field'),
            controller: _text,
            textInputAction: TextInputAction.done,
            decoration: const InputDecoration(hintText: offlineAddHint),
            onSubmitted: (_) => _add(),
          ),
        ),
        IconButton(
          key: const Key('offline-add'),
          tooltip: offlineAddHint,
          icon: const Icon(Icons.add_circle),
          onPressed: _add,
        ),
      ]),
    );
  }
}
