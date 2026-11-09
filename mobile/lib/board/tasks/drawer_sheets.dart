import 'package:flutter/material.dart';

import '../../theme/tokens.dart';
import 'task_models.dart';

/// What a budget sheet answered: a typed amount, or null to clear it.
typedef BudgetPick = ({String? amount});

/// A new expense from the drawer: the amount as typed, and where it goes.
typedef ExpensePick = ({String amount, String? note, String? day, String? stepId});

const _wholeTask = '';

Future<T?> _sheet<T>(BuildContext context, WidgetBuilder builder) =>
    showModalBottomSheet<T>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Tokens.overlay,
      builder: (c) => Padding(
        padding: EdgeInsets.fromLTRB(Tokens.space4, Tokens.space4, Tokens.space4,
            MediaQuery.of(c).viewInsets.bottom + Tokens.space4),
        child: SingleChildScrollView(child: builder(c)),
      ),
    );

Widget _title(String text) => Padding(
      padding: const EdgeInsets.only(bottom: Tokens.space2),
      child: Text(text,
          style: const TextStyle(
              fontSize: Tokens.fsLead, fontWeight: FontWeight.w600)),
    );

/// A budget for the task or a step, in [currency]. Null: cancelled.
Future<BudgetPick?> showBudgetSheet(BuildContext context,
        {required String title, required String currency, String? current}) =>
    _sheet<BudgetPick>(
        context, (_) => _BudgetForm(title: title, currency: currency, current: current));

class _BudgetForm extends StatefulWidget {
  const _BudgetForm({required this.title, required this.currency, this.current});

  final String title;
  final String currency;
  final String? current;

  @override
  State<_BudgetForm> createState() => _BudgetFormState();
}

class _BudgetFormState extends State<_BudgetForm> {
  late final _amount = TextEditingController(text: widget.current ?? '');

  @override
  void dispose() {
    _amount.dispose();
    super.dispose();
  }

  void _done(String? amount) => Navigator.pop<BudgetPick>(context, (amount: amount));

  void _save() => _done(_amount.text.trim().isEmpty ? null : _amount.text.trim());

  @override
  Widget build(BuildContext context) => Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _title(widget.title),
          TextField(
            key: const Key('budget-amount'),
            controller: _amount,
            autofocus: true,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            decoration: InputDecoration(
                labelText: 'Budget in ${widget.currency}', hintText: '20'),
            onSubmitted: (_) => _save(),
          ),
          const SizedBox(height: Tokens.space3),
          Wrap(spacing: Tokens.space2, runSpacing: Tokens.space2, children: [
            FilledButton(
                key: const Key('budget-save'), onPressed: _save, child: const Text('Save')),
            if (widget.current != null)
              OutlinedButton(
                key: const Key('budget-clear'),
                onPressed: () => _done(null),
                child: const Text('Clear budget'),
              ),
            TextButton(
                onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
          ]),
        ],
      );
}

/// A new expense for the task or one of its [steps]. Null: cancelled.
Future<ExpensePick?> showAddExpenseSheet(BuildContext context,
    {required List<TaskStep> steps, required String currency, String? stepId}) {
  return _sheet<ExpensePick>(
    context,
    (c) => _ExpenseForm(steps: steps, currency: currency, stepId: stepId),
  );
}

class _ExpenseForm extends StatefulWidget {
  const _ExpenseForm({required this.steps, required this.currency, this.stepId});

  final List<TaskStep> steps;
  final String currency;
  final String? stepId;

  @override
  State<_ExpenseForm> createState() => _ExpenseFormState();
}

class _ExpenseFormState extends State<_ExpenseForm> {
  final _amount = TextEditingController();
  final _note = TextEditingController();
  final _day = TextEditingController();
  late String _for = widget.stepId ?? _wholeTask;

  @override
  void dispose() {
    for (final c in [_amount, _note, _day]) {
      c.dispose();
    }
    super.dispose();
  }

  String? _text(TextEditingController c) =>
      c.text.trim().isEmpty ? null : c.text.trim();

  void _save() {
    final amount = _text(_amount);
    if (amount == null) return;
    Navigator.pop<ExpensePick>(context, (
      amount: amount,
      note: _text(_note),
      day: _text(_day),
      stepId: _for == _wholeTask ? null : _for,
    ));
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _title('Add an expense'),
        TextField(
          key: const Key('expense-amount'),
          controller: _amount,
          autofocus: true,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          decoration: InputDecoration(labelText: 'Amount in ${widget.currency}'),
        ),
        TextField(
          key: const Key('expense-note'),
          controller: _note,
          decoration: const InputDecoration(labelText: 'What it was'),
        ),
        TextField(
          key: const Key('expense-day'),
          controller: _day,
          decoration: const InputDecoration(
              labelText: 'Day', hintText: 'Today, or yesterday, 2026-10-12'),
        ),
        if (widget.steps.isNotEmpty) ...[
          const SizedBox(height: Tokens.space3),
          const Text('For', style: TextStyle(color: Tokens.textSecondary)),
          const SizedBox(height: Tokens.space1),
          Wrap(spacing: Tokens.space2, runSpacing: Tokens.space2, children: [
            _choice(_wholeTask, 'The whole task'),
            for (final s in widget.steps) _choice(s.id, s.title),
          ]),
        ],
        const SizedBox(height: Tokens.space3),
        Wrap(spacing: Tokens.space2, children: [
          FilledButton(
              key: const Key('expense-save'),
              onPressed: _save,
              child: const Text('Add expense')),
          TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Cancel')),
        ]),
      ],
    );
  }

  Widget _choice(String id, String label) => ChoiceChip(
        key: Key('expense-for-${id.isEmpty ? 'task' : id}'),
        label: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 240),
          child: Text(label, overflow: TextOverflow.ellipsis),
        ),
        selected: _for == id,
        onSelected: (_) => setState(() => _for = id),
      );
}

/// A comment on one step ([title] names it). Null: cancelled.
Future<String?> showCommentSheet(BuildContext context, {required String title}) =>
    _sheet<String>(context,
        (_) => _CommentForm(heading: 'Comment on “$title”', send: 'Comment'));

/// Your own comment, to edit. Null: cancelled.
Future<String?> showEditCommentSheet(BuildContext context, {required String body}) =>
    _sheet<String>(context,
        (_) => _CommentForm(heading: 'Edit comment', send: 'Save', initial: body));

class _CommentForm extends StatefulWidget {
  const _CommentForm({required this.heading, required this.send, this.initial = ''});

  final String heading;
  final String send;
  final String initial;

  @override
  State<_CommentForm> createState() => _CommentFormState();
}

class _CommentFormState extends State<_CommentForm> {
  late final _body = TextEditingController(text: widget.initial);

  @override
  void dispose() {
    _body.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _title(widget.heading),
          TextField(
            key: const Key('step-comment'),
            controller: _body,
            autofocus: true,
            minLines: 2,
            maxLines: 6,
            decoration: const InputDecoration(hintText: 'Write a comment'),
          ),
          const SizedBox(height: Tokens.space3),
          Wrap(spacing: Tokens.space2, children: [
            FilledButton(
              key: const Key('step-comment-send'),
              onPressed: () => Navigator.pop(context, _body.text.trim()),
              child: Text(widget.send),
            ),
            TextButton(
                onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
          ]),
        ],
      );
}
