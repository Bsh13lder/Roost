// The task drawer's money as the server reckoned it (`GET /api/tasks/{id}`
// `money` and `expenses`). Immutable; the phone never adds money up.

import '../common/format.dart';

/// Planned, spent and left for the task or one step, with its bar.
class MoneyLine {
  const MoneyLine({
    required this.spent,
    this.planned,
    this.left,
    this.usedPercent,
    this.tone,
  });

  factory MoneyLine.fromJson(Map<String, dynamic> j) => MoneyLine(
        planned: j['planned'] as String?,
        spent: j['spent'] as String? ?? '0.00',
        left: j['left'] as String?,
        usedPercent: (j['used_percent'] as num?)?.toInt(),
        tone: j['tone'] as String?,
      );

  final String? planned;
  final String spent;
  final String? left;
  final int? usedPercent;
  final String? tone;

  bool get hasBudget => planned != null && left != null;
  bool get isOver => (left ?? '').startsWith('-');
  bool get spentAny => (double.tryParse(spent) ?? 0) != 0;

  /// "€12.50 of €20.00 · €7.50 left", "€25.00 of €20.00 · €5.00 over", or
  /// "€12.50 spent" without a budget; null when nothing is planned or spent.
  String? words(String currency) {
    if (hasBudget) {
      final rest = formatMoney(unsigned(left!), currency);
      return '${formatMoney(spent, currency)} of ${formatMoney(planned!, currency)}'
          ' · $rest ${isOver ? 'over' : 'left'}';
    }
    return spentAny ? '${formatMoney(spent, currency)} spent' : null;
  }
}

/// The whole drawer's money: the task's line, each step's, and its expenses.
class TaskMoneyView {
  const TaskMoneyView({
    required this.currency,
    required this.task,
    this.steps = const {},
    this.expenses = const [],
    this.inProject = true,
  });

  /// Null when the server sent no money block (an older gateway).
  static TaskMoneyView? fromDetail(Map<String, dynamic> detail) {
    final m = detail['money'];
    if (m is! Map) return null;
    final money = m.cast<String, dynamic>();
    final steps = money['steps_money'];
    return TaskMoneyView(
      currency: money['currency'] as String? ?? '',
      task: MoneyLine.fromJson(money),
      inProject: detail['project_id'] != null,
      steps: {
        if (steps is Map)
          for (final e in steps.entries)
            '${e.key}': MoneyLine.fromJson((e.value as Map).cast<String, dynamic>()),
      },
      expenses: [
        for (final e in (detail['expenses'] as List? ?? const []))
          if (e is Map) e.cast<String, dynamic>(),
      ],
    );
  }

  final String currency;
  final MoneyLine task;
  final Map<String, MoneyLine> steps;
  final List<Map<String, dynamic>> expenses;
  final bool inProject;

  MoneyLine? step(String id) => steps[id];
}
