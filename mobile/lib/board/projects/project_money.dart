import 'package:flutter/material.dart';

import '../../theme/tokens.dart';
import '../common/widgets.dart';
import '../money/expense_line.dart';
import '../money/expense_rows.dart';
import '../money/expense_sheet.dart';
import '../money/money_tab.dart';
import 'projects_api.dart';
import 'topups_sheet.dart';

/// How many of a project's newest expenses its page lists before "See all".
const projectExpensesShown = 20;

/// A project's Money, where Money lives on the phone: + Add expense (the
/// quick money line), Top-ups, the expenses and income, and See all.
class ProjectMoney extends StatelessWidget {
  const ProjectMoney({super.key, required this.project, required this.onChanged});

  final Json project;
  final VoidCallback onChanged;

  String get _id => project['id'] as String;

  Future<void> _add(BuildContext context) async {
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (sheet) => Padding(
        padding: EdgeInsets.only(bottom: MediaQuery.viewInsetsOf(sheet).bottom),
        child: SafeArea(
          child: ExpenseLine(
            projectId: _id,
            onAdded: () => Navigator.of(sheet).pop(),
          ),
        ),
      ),
    );
    onChanged();
  }

  Future<void> _topups(BuildContext context) async {
    final changed = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (_) => TopupsSheet(project: project),
    );
    if (changed == true) onChanged();
  }

  void _seeAll(BuildContext context) => Navigator.of(context)
      .push(MaterialPageRoute<void>(
        builder: (_) => Scaffold(
          backgroundColor: Tokens.bg,
          appBar: AppBar(title: Text('${project['name']} · Money')),
          body: MoneyTab(projectId: _id),
        ),
      ))
      .then((_) => onChanged());

  @override
  Widget build(BuildContext context) {
    final expenses = [
      for (final e in (project['expenses'] as List? ?? const []))
        {...Map<String, dynamic>.from(e as Map), 'project_color': project['color']},
    ];
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      SectionTitle('Money',
          trailing: TextButton(
            key: const Key('money-topups'),
            onPressed: () => _topups(context),
            child: const Text('Top-ups'),
          )),
      Padding(
        padding: const EdgeInsets.symmetric(horizontal: Tokens.space4),
        child: OutlinedButton.icon(
          key: const Key('add-expense'),
          icon: const Icon(Icons.add),
          label: const Text('Add expense'),
          onPressed: () => _add(context),
        ),
      ),
      for (final e in expenses.take(projectExpensesShown))
        ExpenseTile(
          expense: e,
          onTap: () => showExpenseSheet(context, e, onChanged),
        ),
      if (expenses.isEmpty) const BoardNote('No expenses yet.'),
      Align(
        alignment: Alignment.centerRight,
        child: TextButton(
          key: const Key('money-all'),
          onPressed: () => _seeAll(context),
          child: const Text('See all, by month'),
        ),
      ),
    ]);
  }
}
