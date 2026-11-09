import '../common/format.dart';
import 'money_api.dart';

/// One chip of the expense line, drawn from the server's reading.
class ExpenseChip {
  const ExpenseChip(this.kind, this.label, this.tone);

  /// amount, project, date, vendor, star, repeat or warning.
  final String kind;
  final String label;

  /// read, ask (the server could not use it as typed) or warn.
  final String tone;
}

const needsAmountText = 'Add an amount, like €12.';

String? _s(Json l, String k) => l[k] is String ? l[k] as String : null;

List<ExpenseChip> chipsOf(Json line) {
  final chips = <ExpenseChip>[];
  final amount = _s(line, 'amount');
  if (amount != null) {
    final money = formatMoney(amount, _s(line, 'currency') ?? 'EUR');
    final math = _s(line, 'amount_math');
    final shown = math != null ? '$money = $math' : money;
    chips.add(ExpenseChip(
        'amount', line['income'] == true ? 'Money in $shown' : shown, 'read'));
  } else if (_s(line, 'amount_words') != null) {
    chips.add(ExpenseChip('amount', _s(line, 'amount_words')!, 'ask'));
  }
  final project = line['project'];
  if (project is Map) {
    chips.add(ExpenseChip('project', '/${project['name']}', 'read'));
  } else if (_s(line, 'project_words') != null) {
    chips.add(ExpenseChip('project', _s(line, 'project_words')!, 'ask'));
  }
  if (_s(line, 'day_problem') != null) {
    chips.add(ExpenseChip(
        'date', _s(line, 'day_words') ?? _s(line, 'spent_text') ?? '', 'ask'));
  } else if (_s(line, 'day_words') != null) {
    chips.add(ExpenseChip('date', _s(line, 'spent_text') ?? '', 'read'));
  }
  if (_s(line, 'vendor') != null) {
    chips.add(ExpenseChip('vendor', 'at ${line['vendor']}', 'read'));
  }
  if (line['starred'] == true) chips.add(const ExpenseChip('star', 'Starred', 'read'));
  if (_s(line, 'cadence') != null) {
    chips.add(ExpenseChip('repeat', 'Repeats ${line['cadence']}', 'read'));
  } else if (_s(line, 'repeat_words') != null) {
    chips.add(ExpenseChip('repeat', _s(line, 'repeat_words')!, 'ask'));
  }
  for (final w in (line['warnings'] as List? ?? const [])) {
    chips.add(ExpenseChip('warning', '$w', 'warn'));
  }
  return chips;
}

/// Why a reading cannot be added yet, in the server's words.
String? blockerOf(Json line) {
  if (line['ready'] == true) return null;
  for (final k in const [
    'amount_problem',
    'project_question',
    'day_problem',
    'repeat_problem',
    'income_problem',
    'text_problem',
  ]) {
    final v = _s(line, k);
    if (v != null) return v;
  }
  return needsAmountText;
}

/// What a ready reading adds: exactly what the server read.
Json expenseBodyOf(Json line, {String? projectId}) {
  final project = line['project'];
  return {
    'amount': _s(line, 'amount') ?? '0',
    'currency': _s(line, 'currency'),
    if (project is Map)
      'project_id': project['id']
    else
      'project_id': ?projectId,
    if ((_s(line, 'note') ?? '').isNotEmpty) 'note': line['note'],
    'spent_at': _s(line, 'spent_at'),
    if (_s(line, 'vendor') != null) 'vendor': line['vendor'],
    if (line['starred'] == true) 'starred': true,
    if (line['income'] == true) 'income': true,
    if (_s(line, 'cadence') != null) 'cadence': line['cadence'],
  };
}
