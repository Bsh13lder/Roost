import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../theme/tokens.dart';
import '../common/format.dart';
import '../common/widgets.dart';
import '../money/expense_sheet.dart';
import 'drawer_money_view.dart';
import 'drawer_sheets.dart';
import 'task_dates.dart';
import 'task_models.dart';
import 'task_repo.dart';

/// What was spent on each step, from `GET /api/tasks/{id}` `money.steps`.
Map<String, String> stepSpent(Map<String, dynamic> detail) {
  final m = detail['money'];
  final steps = m is Map ? m['steps'] : null;
  if (steps is! Map) return const {};
  return {for (final e in steps.entries) '${e.key}': '${e.value}'};
}

/// Adds an expense from the drawer (the whole task, or [stepId]) and reloads
/// the task. Errors show as a snack bar in the server's words.
Future<void> addTaskExpense(BuildContext context, WidgetRef ref,
    {required String taskId,
    required List<TaskStep> steps,
    required String currency,
    String? stepId}) async {
  final pick = await showAddExpenseSheet(context,
      steps: steps, currency: currency, stepId: stepId);
  if (pick == null || !context.mounted) return;
  try {
    await ref.read(taskRepoProvider).addExpense(taskId,
        amount: pick.amount, stepId: pick.stepId, note: pick.note, day: pick.day);
    ref.invalidate(taskDetailProvider(taskId));
    if (context.mounted) snack(context, 'Expense added.');
  } catch (e) {
    if (context.mounted) snack(context, errorText(e));
  }
}

/// Money on a task: its budget, spent and left (General's currency for a task
/// in no project), its expenses (tap one to edit or delete it), and Add
/// expense. The server reckons every number; this only shows them.
class DrawerMoney extends ConsumerWidget {
  const DrawerMoney({super.key, required this.detail});

  final Map<String, dynamic> detail;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final view = TaskMoneyView.fromDetail(detail);
    if (view == null) return const SizedBox.shrink();
    final task = TaskItem.fromJson(detail);
    final titles = {for (final s in task.steps) s.id: s.title};
    return Padding(
      padding: const EdgeInsets.only(bottom: Tokens.space6),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            const Expanded(
              child: Text('Money',
                  style: TextStyle(fontSize: Tokens.fsLead, fontWeight: FontWeight.w600)),
            ),
            TextButton.icon(
              key: const Key('money-add'),
              icon: const Icon(Icons.add, size: 18),
              label: const Text('Add expense'),
              onPressed: () => addTaskExpense(context, ref,
                  taskId: task.id, steps: task.steps, currency: view.currency),
            ),
          ]),
          if (!view.inProject)
            Padding(
              padding: const EdgeInsets.only(bottom: Tokens.space2),
              child: Text('In no project, so its money counts in General, in ${view.currency}.',
                  style: const TextStyle(color: Tokens.textSecondary, fontSize: Tokens.fsLabel)),
            ),
          _Figures(line: view.task, currency: view.currency),
          for (final e in view.expenses)
            _ExpenseTile(
              expense: e,
              stepTitle: titles[e['step_id']],
              onChanged: () => ref.invalidate(taskDetailProvider(task.id)),
            ),
        ],
      ),
    );
  }
}

class _Figures extends StatelessWidget {
  const _Figures({required this.line, required this.currency});

  final MoneyLine line;
  final String currency;

  @override
  Widget build(BuildContext context) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            _stat('Planned', line.planned),
            _stat('Spent', line.spent),
            _stat('Left', line.left, color: line.isOver ? Tokens.danger : null),
          ]),
          if (line.hasBudget) ...[
            const SizedBox(height: Tokens.space2),
            ToneBar(percent: line.usedPercent, tone: line.tone),
          ],
        ],
      );

  Widget _stat(String label, String? value, {Color? color}) => Expanded(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(label,
                style: const TextStyle(fontSize: Tokens.fsCaption, color: Tokens.textSecondary)),
            Text(value == null ? 'None' : formatMoney(value, currency),
                overflow: TextOverflow.ellipsis, style: TextStyle(color: color)),
          ],
        ),
      );
}

class _ExpenseTile extends StatelessWidget {
  const _ExpenseTile({required this.expense, required this.onChanged, this.stepTitle});

  final Map<String, dynamic> expense;
  final String? stepTitle;
  final VoidCallback onChanged;

  @override
  Widget build(BuildContext context) {
    final e = expense;
    final isVoid = e['status'] == 'void';
    final when = momentWords(e['spent_at'] as String?);
    return ListTile(
      key: ValueKey('expense-${e['id']}'),
      contentPadding: EdgeInsets.zero,
      dense: true,
      title: Text('${e['description'] ?? e['vendor'] ?? 'Expense'}',
          overflow: TextOverflow.ellipsis,
          style: TextStyle(decoration: isVoid ? TextDecoration.lineThrough : null)),
      subtitle: Text(stepTitle == null ? when : '$when · for “$stepTitle”',
          overflow: TextOverflow.ellipsis),
      trailing: Text(formatMoney('${e['amount']}', '${e['currency']}')),
      onTap: () => showExpenseSheet(context, e, onChanged),
    );
  }
}
