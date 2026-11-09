import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../api/api_error.dart';
import '../../theme/tokens.dart';
import 'drawer_sheets.dart';
import 'task_dates.dart';
import 'task_models.dart';
import 'task_repo.dart';

/// The comment thread, oldest first, on the whole task or one of its steps
/// (pick it beside the field). Edit and delete are for your own only.
class DrawerComments extends ConsumerStatefulWidget {
  const DrawerComments({super.key, required this.task});

  final TaskItem task;

  @override
  ConsumerState<DrawerComments> createState() => _DrawerCommentsState();
}

class _DrawerCommentsState extends ConsumerState<DrawerComments> {
  final _text = TextEditingController();
  String? _stepId;   // the step the next comment is about; null: the whole task

  @override
  void dispose() {
    _text.dispose();
    super.dispose();
  }

  Future<void> _run(Future<void> Function() f) async {
    final messenger = ScaffoldMessenger.of(context);
    try {
      await f();
      ref.invalidate(taskCommentsProvider(widget.task.id));
    } on ApiException catch (e) {
      messenger.showSnackBar(SnackBar(content: Text(e.message)));
    }
  }

  Future<void> _send() async {
    final body = _text.text.trim();
    if (body.isEmpty) return;
    _text.clear();
    final stepId = _stepId;
    setState(() => _stepId = null);
    await _run(() =>
        ref.read(taskRepoProvider).addComment(widget.task.id, body, stepId: stepId));
  }

  Future<void> _edit(TaskComment c) async {
    final body = await showEditCommentSheet(context, body: c.body);
    if (body != null && body.isNotEmpty && body != c.body) {
      await _run(() => ref.read(taskRepoProvider).editComment(c.id, body));
    }
  }

  @override
  Widget build(BuildContext context) {
    final comments = ref.watch(taskCommentsProvider(widget.task.id));
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text('Comments',
            style:
                TextStyle(fontSize: Tokens.fsLead, fontWeight: FontWeight.w600)),
        for (final c in comments.value ?? const <TaskComment>[]) _tile(c),
        if (_about() case final step?)
          Padding(
            padding: const EdgeInsets.only(top: Tokens.space2),
            child: InputChip(
              key: const Key('comment-about'),
              label: Text('On “${step.title}”', overflow: TextOverflow.ellipsis),
              onDeleted: () => setState(() => _stepId = null),
            ),
          ),
        Row(
          children: [
            if (widget.task.steps.isNotEmpty) _aboutPicker(),
            Expanded(
              child: TextField(
                key: const Key('comment-add'),
                controller: _text,
                onSubmitted: (_) => _send(),
                decoration: const InputDecoration(
                    hintText: 'Add a comment', isDense: true),
              ),
            ),
            IconButton(onPressed: _send, icon: const Icon(Icons.send)),
          ],
        ),
      ],
    );
  }

  TaskStep? _about() =>
      widget.task.steps.where((s) => s.id == _stepId).firstOrNull;

  Widget _aboutPicker() => PopupMenuButton<String>(
        key: const Key('comment-about-pick'),
        tooltip: 'Comment on a step',
        icon: const Icon(Icons.checklist, size: 20),
        onSelected: (id) => setState(() => _stepId = id.isEmpty ? null : id),
        itemBuilder: (_) => [
          const PopupMenuItem(value: '', child: Text('The whole task')),
          for (final s in widget.task.steps)
            PopupMenuItem(
                value: s.id, child: Text(s.title, overflow: TextOverflow.ellipsis)),
        ],
      );

  Widget _tile(TaskComment c) {
    final when = momentWords(c.createdAt);
    final step = widget.task.steps.where((s) => s.id == c.stepId).firstOrNull;
    return ListTile(
      key: ValueKey('comment-${c.id}'),
      contentPadding: EdgeInsets.zero,
      title: Text(c.body),
      subtitle: Text(
        '${c.isMine ? 'You' : 'A bot'}${step == null ? '' : ' on “${step.title}”'}'
        ' · $when${c.editedAt != null ? ' · edited' : ''}'
        '${c.tainted ? ' · from web content' : ''}',
        style: const TextStyle(fontSize: Tokens.fsCaption),
      ),
      trailing: c.isMine
          ? PopupMenuButton<String>(
              onSelected: (v) => v == 'edit'
                  ? _edit(c)
                  : _run(() => ref.read(taskRepoProvider).deleteComment(c.id)),
              itemBuilder: (_) => const [
                PopupMenuItem(value: 'edit', child: Text('Edit')),
                PopupMenuItem(value: 'delete', child: Text('Delete')),
              ],
            )
          : null,
    );
  }
}
