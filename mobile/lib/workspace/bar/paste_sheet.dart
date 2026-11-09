import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../api/api_error.dart';
import '../../board/tasks/paste_list.dart';
import '../../board/tasks/task_repo.dart';
import '../../theme/tokens.dart';

/// Said when the server could not read the pasted list for a reason it did
/// not name.
const pasteReadFailedText = "Couldn't read the pasted list. Try again.";

const _titleStyle = TextStyle(fontSize: Tokens.fsHeading, fontWeight: FontWeight.w600);
const _faint = TextStyle(color: Tokens.textSecondary, fontSize: Tokens.fsCaption);

/// "Add N tasks?" for a pasted list (as the web's quick add): the server
/// reads each line (`POST /api/tasks/parse-many`), you see the titles and
/// their steps, and Add creates them one at a time. Answers how many were
/// added (0 when none).
Future<int> showPasteSheet(BuildContext context, String text) async {
  final added = await showModalBottomSheet<int>(
    context: context,
    isScrollControlled: true,
    showDragHandle: true,
    builder: (_) => _PasteBody(text: text),
  );
  return added ?? 0;
}

class _PasteBody extends ConsumerStatefulWidget {
  const _PasteBody({required this.text});

  final String text;

  @override
  ConsumerState<_PasteBody> createState() => _PasteBodyState();
}

class _PasteBodyState extends ConsumerState<_PasteBody> {
  PastedList? _list;
  String? _error;
  bool _busy = true;
  int _added = 0;

  @override
  void initState() {
    super.initState();
    _read();
  }

  Future<void> _read() async {
    try {
      final list = await ref.read(taskRepoProvider).parseMany(widget.text);
      if (mounted) setState(() => _list = list);
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } catch (_) {
      if (mounted) setState(() => _error = pasteReadFailedText);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _add() async {
    final list = _list;
    if (list == null || !list.ready) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final added = await addPastedTasks(ref.read(taskRepoProvider), list.tasks);
      if (mounted) Navigator.pop(context, _added + added.length);
    } on PasteAddProblem catch (e) {
      if (!mounted) return;
      setState(() {
        _added += list.count - e.left.length;
        _list = list.withTasks(e.left);
        _error = e.message;
        _busy = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final list = _list;
    final count = list?.count ?? 0;
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(Tokens.space4, 0, Tokens.space4, Tokens.space4),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(list == null ? 'Pasted tasks' : '${addTasksLabel(count)}?', style: _titleStyle),
            const SizedBox(height: Tokens.space2),
            if (list == null && _busy) const LinearProgressIndicator(),
            if (list != null) Flexible(child: _PasteRows(list: list)),
            if (list?.problem != null) _note(list!.problem!, 'paste-problem', Tokens.textSecondary),
            if (_error != null) _note(_error!, 'paste-error', Tokens.dangerText),
            const SizedBox(height: Tokens.space3),
            _actions(list),
          ],
        ),
      ),
    );
  }

  Widget _note(String words, String key, Color color) => Padding(
        padding: const EdgeInsets.only(top: Tokens.space2),
        child: Text(words, key: Key(key), style: TextStyle(color: color, fontSize: Tokens.fsLabel)),
      );

  Widget _actions(PastedList? list) {
    final canAdd = !_busy && list != null && list.ready && list.count > 0;
    return Row(mainAxisAlignment: MainAxisAlignment.end, children: [
      TextButton(
        key: const Key('paste-cancel'),
        onPressed: _busy && list != null ? null : () => Navigator.pop(context, _added),
        child: const Text('Cancel'),
      ),
      const SizedBox(width: Tokens.space2),
      FilledButton(
        key: const Key('paste-add'),
        onPressed: canAdd ? _add : null,
        child: Text(addTasksLabel(list?.count ?? 0)),
      ),
    ]);
  }
}

/// The titles the server read, each with how many steps it holds.
class _PasteRows extends StatelessWidget {
  const _PasteRows({required this.list});

  final PastedList list;

  @override
  Widget build(BuildContext context) => ListView(
        shrinkWrap: true,
        children: [
          for (final (i, t) in list.tasks.indexed)
            Padding(
              key: Key('paste-row-$i'),
              padding: const EdgeInsets.symmetric(vertical: Tokens.space1),
              child: Row(children: [
                Expanded(
                  child: Text(t.reading.title,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(fontSize: Tokens.fsBody)),
                ),
                if (t.steps.isNotEmpty)
                  Text(t.steps.length == 1 ? '1 step' : '${t.steps.length} steps', style: _faint),
              ]),
            ),
        ],
      );
}
