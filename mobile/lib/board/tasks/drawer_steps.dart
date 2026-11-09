import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../api/api_error.dart';
import '../../theme/tokens.dart';
import '../common/widgets.dart';
import 'drawer_money.dart';
import 'drawer_money_view.dart';
import 'drawer_sheets.dart';
import 'task_models.dart';
import 'task_repo.dart';

/// Steps of one task: add, check, rename (tap the text), reorder (drag the
/// handle), and from each step's menu its own budget, an expense, a comment,
/// or delete. Every number on a step comes from the server.
class DrawerSteps extends ConsumerStatefulWidget {
  const DrawerSteps(
      {super.key, required this.task, required this.spentByStep, this.money});

  final TaskItem task;
  final Map<String, String> spentByStep;
  final TaskMoneyView? money;

  @override
  ConsumerState<DrawerSteps> createState() => _DrawerStepsState();
}

class _DrawerStepsState extends ConsumerState<DrawerSteps> {
  final _add = TextEditingController();
  late List<TaskStep> _steps = widget.task.steps;

  @override
  void dispose() {
    _add.dispose();
    super.dispose();
  }

  TaskRepo get _repo => ref.read(taskRepoProvider);

  Future<void> _run(Future<void> Function() f) async {
    final messenger = ScaffoldMessenger.of(context);
    try {
      await f();
      ref.invalidate(taskDetailProvider(widget.task.id));
      ref.invalidate(taskListProvider);
      final fresh = await ref.read(taskDetailProvider(widget.task.id).future);
      if (mounted) setState(() => _steps = TaskItem.fromJson(fresh).steps);
    } on ApiException catch (e) {
      messenger.showSnackBar(SnackBar(content: Text(e.message)));
    }
  }

  Future<void> _rename(TaskStep s) async {
    final c = TextEditingController(text: s.title);
    final title = await showDialog<String>(
      context: context,
      builder: (d) => AlertDialog(
        title: const Text('Edit step'),
        content: TextField(controller: c, autofocus: true),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(d), child: const Text('Cancel')),
          TextButton(
              onPressed: () => Navigator.pop(d, c.text.trim()),
              child: const Text('Save')),
        ],
      ),
    );
    c.dispose();
    if (title != null && title.isNotEmpty && title != s.title) {
      await _run(() => _repo.patchStep(widget.task.id, s.id, {'title': title}));
    }
  }

  Future<void> _budget(TaskStep s) async {
    final money = widget.money;
    if (money == null) return;
    final pick = await showBudgetSheet(context,
        title: 'Budget for “${s.title}”',
        currency: money.currency,
        current: money.step(s.id)?.planned);
    if (pick == null) return;
    await _run(() => _repo.setStepBudget(widget.task.id, s.id, pick.amount));
  }

  Future<void> _comment(TaskStep s) async {
    final body = await showCommentSheet(context, title: s.title);
    if (body == null || body.isEmpty) return;
    await _run(() => _repo.addComment(widget.task.id, body, stepId: s.id));
    if (mounted) snack(context, 'Comment added.');
  }

  void _act(String action, TaskStep s) {
    switch (action) {
      case 'budget':
        _budget(s);
      case 'expense':
        addTaskExpense(context, ref,
            taskId: widget.task.id,
            steps: _steps,
            currency: widget.money?.currency ?? '',
            stepId: s.id);
      case 'comment':
        _comment(s);
      case 'delete':
        _run(() => _repo.deleteStep(widget.task.id, s.id));
    }
  }

  Future<void> _addStep() async {
    final text = _add.text.trim();
    if (text.isEmpty) return;
    _add.clear();
    await _run(() => _repo.addStep(widget.task.id, text));
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text('Steps',
            style:
                TextStyle(fontSize: Tokens.fsLead, fontWeight: FontWeight.w600)),
        ReorderableListView(
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          buildDefaultDragHandles: false,
          onReorder: (from, to) {
            final step = _steps[from];
            final position = to > from ? to - 1 : to;
            _run(() => _repo.moveStep(widget.task.id, step.id, position));
          },
          children: [
            for (var i = 0; i < _steps.length; i++) _stepTile(_steps[i], i),
          ],
        ),
        Row(
          children: [
            Expanded(
              child: TextField(
                key: const Key('step-add'),
                controller: _add,
                onSubmitted: (_) => _addStep(),
                decoration: const InputDecoration(
                    hintText: 'Add a step', isDense: true),
              ),
            ),
            IconButton(onPressed: _addStep, icon: const Icon(Icons.add)),
          ],
        ),
      ],
    );
  }

  String? _moneyWords(TaskStep s) {
    final money = widget.money;
    final line = money?.step(s.id);
    if (money != null && line != null) return line.words(money.currency);
    final spent = widget.spentByStep[s.id];
    return spent == null || spent == '0' || spent == '0.00' ? null : 'Spent $spent';
  }

  Widget _stepTile(TaskStep s, int index) {
    final words = _moneyWords(s);
    final over = widget.money?.step(s.id)?.isOver ?? false;
    return ListTile(
      key: ValueKey('drawer-step-${s.id}'),
      contentPadding: EdgeInsets.zero,
      dense: true,
      leading: Checkbox(
        value: s.done,
        onChanged: (v) => _run(() => _repo
            .patchStep(widget.task.id, s.id, {'done': v == true})),
      ),
      title: GestureDetector(
        onTap: () => _rename(s),
        child: Text(s.title,
            style: TextStyle(
                decoration: s.done ? TextDecoration.lineThrough : null,
                color: s.done ? Tokens.textFaint : Tokens.text)),
      ),
      subtitle: words == null
          ? null
          : Text(words,
              style: TextStyle(
                  fontSize: Tokens.fsCaption,
                  color: over ? Tokens.dangerText : Tokens.textSecondary)),
      trailing: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          PopupMenuButton<String>(
            key: Key('step-menu-${s.id}'),
            tooltip: 'More for ${s.title}',
            icon: const Icon(Icons.more_vert, size: 20),
            onSelected: (v) => _act(v, s),
            itemBuilder: (_) => [
              if (widget.money != null)
                const PopupMenuItem(value: 'budget', child: Text('Budget…')),
              if (widget.money != null)
                const PopupMenuItem(value: 'expense', child: Text('Add expense…')),
              const PopupMenuItem(value: 'comment', child: Text('Comment…')),
              const PopupMenuItem(value: 'delete', child: Text('Delete step')),
            ],
          ),
          ReorderableDragStartListener(
            index: index,
            child: const Icon(Icons.drag_handle, size: 20),
          ),
        ],
      ),
    );
  }
}
