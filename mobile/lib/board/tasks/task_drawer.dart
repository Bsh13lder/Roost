import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../api/api_error.dart';
import '../../theme/tokens.dart';
import '../common/format.dart';
import 'drawer_comments.dart';
import 'drawer_money.dart';
import 'drawer_money_view.dart';
import 'drawer_sheets.dart';
import 'drawer_steps.dart';
import 'remind_picks.dart';
import 'remind_sheet.dart';
import 'reschedule_sheet.dart';
import 'task_actions.dart';
import 'task_dates.dart';
import 'task_models.dart';
import 'task_repo.dart';

/// The full-screen task drawer.
Future<void> openTaskDrawer(BuildContext context, String taskId) {
  return Navigator.of(context).push(MaterialPageRoute<void>(
    fullscreenDialog: true,
    builder: (_) => TaskDrawer(taskId: taskId),
  ));
}

const _priorities = ['urgent', 'high', 'medium', 'low'];

class TaskDrawer extends ConsumerWidget {
  const TaskDrawer({super.key, required this.taskId});

  final String taskId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final detail = ref.watch(taskDetailProvider(taskId));
    return Scaffold(
      appBar: AppBar(
        title: const Text('Task'),
        actions: [
          detail.maybeWhen(
            data: (d) => IconButton(
              key: const Key('drawer-delete'),
              icon: const Icon(Icons.delete_outline),
              onPressed: () async {
                final nav = Navigator.of(context);
                final gone =
                    await TaskActions(context).delete(TaskItem.fromJson(d));
                if (gone) nav.maybePop();
              },
            ),
            orElse: () => const SizedBox.shrink(),
          ),
        ],
      ),
      body: detail.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text('$e')),
        data: (d) => _DrawerBody(key: ValueKey(taskId), detail: d),
      ),
    );
  }
}

class _DrawerBody extends ConsumerStatefulWidget {
  const _DrawerBody({super.key, required this.detail});

  final Map<String, dynamic> detail;

  @override
  ConsumerState<_DrawerBody> createState() => _DrawerBodyState();
}

class _DrawerBodyState extends ConsumerState<_DrawerBody> {
  late final TaskItem _task = TaskItem.fromJson(widget.detail);
  late final _title = TextEditingController(text: _task.title);
  late final _notes = TextEditingController(text: _task.description ?? '');
  late String _priority = _task.priority;
  late String? _projectId = _task.projectId;
  late bool _starred = _task.starred;
  bool _saving = false;

  @override
  void dispose() {
    _title.dispose();
    _notes.dispose();
    super.dispose();
  }

  bool get _changed =>
      _title.text.trim() != _task.title ||
      _notes.text != (_task.description ?? '') ||
      _priority != _task.priority ||
      _projectId != _task.projectId ||
      _starred != _task.starred;

  Future<void> _save() async {
    if (_title.text.trim().isEmpty) return;
    setState(() => _saving = true);
    final messenger = ScaffoldMessenger.of(context);
    try {
      await ref.read(taskRepoProvider).update(_task.id, {
        'title': _title.text.trim(),
        'description': _notes.text,
        'priority': _priority,
        'project_id': _projectId,
        'starred': _starred,
      });
      ref.invalidate(taskListProvider);
      ref.invalidate(taskDetailProvider(_task.id));
      messenger.showSnackBar(const SnackBar(content: Text('Saved.')));
      if (mounted) Navigator.of(context).maybePop();
    } on ApiException catch (e) {
      messenger.showSnackBar(SnackBar(content: Text(e.message)));
      if (mounted) setState(() => _saving = false);
    }
  }

  /// Due applies at once, like the web.
  Future<void> _due() async {
    final actions = TaskActions(context);
    final c = await showRescheduleSheet(context, title: 'Due');
    if (c == null) return;
    await actions.reschedule(_task, c);
    ref.invalidate(taskDetailProvider(_task.id));
  }

  /// Remind me applies at once too: the reminder alone, no advance one.
  Future<void> _remind() async {
    final messenger = ScaffoldMessenger.of(context);
    final c = await showRemindSheet(context, dueDate: _task.dueDate, hasReminder: _task.reminderAt != null);
    if (c == null) return;
    try {
      await ref.read(taskRepoProvider).update(_task.id, {
        'reminder_at': c.wire,
        if (c.wire != null) 'pre_reminders': <String>[],
      });
      ref.invalidate(taskListProvider);
      ref.invalidate(taskDetailProvider(_task.id));
    } on ApiException catch (e) {
      messenger.showSnackBar(SnackBar(content: Text(e.message)));
    }
  }

  String _budgetWords() {
    final money = TaskMoneyView.fromDetail(widget.detail);
    final slice = widget.detail['allocated_budget'] as String?;
    if (money == null || slice == null) return 'Add a budget';
    return formatMoney(slice, money.currency);
  }

  /// The task's budget applies at once, like Due. A task in no project counts
  /// it in General's currency.
  Future<void> _budget() async {
    final money = TaskMoneyView.fromDetail(widget.detail);
    if (money == null) return;
    final messenger = ScaffoldMessenger.of(context);
    final pick = await showBudgetSheet(context,
        title: 'Budget for this task',
        currency: money.currency,
        current: widget.detail['allocated_budget'] as String?);
    if (pick == null) return;
    try {
      await ref.read(taskRepoProvider).update(_task.id, {'allocated_budget': pick.amount});
      ref.invalidate(taskListProvider);
      ref.invalidate(taskDetailProvider(_task.id));
    } on ApiException catch (e) {
      messenger.showSnackBar(SnackBar(content: Text(e.message)));
    }
  }

  Future<void> _project() async {
    final projects = await ref.read(taskProjectsProvider.future);
    if (!mounted) return;
    final r = await pickProject(context, projects);
    if (r != null) setState(() => _projectId = r.project?.id);
  }

  @override
  Widget build(BuildContext context) {
    final projects = ref.watch(taskProjectsProvider).value ?? const [];
    final project = projects.where((p) => p.id == _projectId).firstOrNull;
    return ListView(
      padding: const EdgeInsets.all(Tokens.space4),
      children: [
        TextField(
          key: const Key('drawer-title'),
          controller: _title,
          onChanged: (_) => setState(() {}),
          style: const TextStyle(fontSize: Tokens.fsHeading),
          decoration: const InputDecoration(hintText: 'Title'),
        ),
        const SizedBox(height: Tokens.space3),
        _prop('Due', _due,
            _task.dueDate == null ? 'No date' : dueWords(_task.dueDate)),
        _prop('Remind me', _remind, reminderWords(_task.reminderAt), key: const Key('drawer-remind')),
        _prop('Project', _project, project?.name ?? 'No project'),
        _prop('Budget', _budget, _budgetWords(), key: const Key('drawer-budget')),
        _priorityRow(),
        SwitchListTile(
          contentPadding: EdgeInsets.zero,
          title: const Text('Starred'),
          value: _starred,
          onChanged: (v) => setState(() => _starred = v),
        ),
        TextField(
          controller: _notes,
          onChanged: (_) => setState(() {}),
          minLines: 2,
          maxLines: 6,
          decoration: const InputDecoration(hintText: 'Notes'),
        ),
        const SizedBox(height: Tokens.space3),
        FilledButton(
          key: const Key('drawer-save'),
          onPressed: _changed && !_saving ? _save : null,
          child: const Text('Save changes'),
        ),
        const SizedBox(height: Tokens.space6),
        DrawerSteps(
            task: _task,
            spentByStep: stepSpent(widget.detail),
            money: TaskMoneyView.fromDetail(widget.detail)),
        const SizedBox(height: Tokens.space6),
        DrawerMoney(detail: widget.detail),
        DrawerComments(task: TaskItem.fromJson(widget.detail)),
        const SizedBox(height: Tokens.space6),
        DrawerActivity(task: _task),
      ],
    );
  }

  Widget _prop(String label, VoidCallback onTap, String value, {Key? key}) => ListTile(
        key: key,
        contentPadding: EdgeInsets.zero,
        title: Text(label,
            style: const TextStyle(color: Tokens.textSecondary)),
        trailing: Text(value),
        onTap: onTap,
      );

  Widget _priorityRow() => Padding(
        padding: const EdgeInsets.symmetric(vertical: Tokens.space2),
        child: SegmentedButton<String>(
          showSelectedIcon: false,
          segments: [
            for (final p in _priorities)
              ButtonSegment(
                  value: p,
                  label: Text(p[0].toUpperCase() + p.substring(1),
                      style: const TextStyle(fontSize: Tokens.fsCaption))),
          ],
          selected: {_priority},
          onSelectionChanged: (s) => setState(() => _priority = s.first),
        ),
      );
}

class DrawerActivity extends StatelessWidget {
  const DrawerActivity({super.key, required this.task});

  final TaskItem task;

  @override
  Widget build(BuildContext context) {
    final lines = <String>[
      if (task.createdAt != null)
        'Made ${momentWords(task.createdAt)}${task.owner == 'user' ? '' : ' by a bot'}',
      if (task.updatedAt != null && task.updatedAt != task.createdAt)
        'Last changed ${momentWords(task.updatedAt)}',
      if (task.completedAt != null) 'Finished ${momentWords(task.completedAt)}',
    ];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text('Activity',
            style: TextStyle(
                fontSize: Tokens.fsLead, fontWeight: FontWeight.w600)),
        const SizedBox(height: Tokens.space2),
        for (final l in lines)
          Padding(
            padding: const EdgeInsets.only(bottom: Tokens.space1),
            child: Text(l,
                style: const TextStyle(
                    color: Tokens.textSecondary, fontSize: Tokens.fsLabel)),
          ),
        const SizedBox(height: Tokens.space8),
      ],
    );
  }
}
