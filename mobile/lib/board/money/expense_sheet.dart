import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../theme/tokens.dart';
import '../common/widgets.dart';
import 'money_api.dart';

/// Opens the edit sheet for one expense. [onChanged] runs after any change.
Future<void> showExpenseSheet(
  BuildContext context,
  Json expense,
  VoidCallback onChanged,
) {
  return showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    backgroundColor: Tokens.overlay,
    builder: (_) => _ExpenseSheet(
      expense: expense,
      onChanged: onChanged,
      messenger: ScaffoldMessenger.maybeOf(context),
    ),
  );
}

class _ExpenseSheet extends ConsumerStatefulWidget {
  const _ExpenseSheet(
      {required this.expense, required this.onChanged, this.messenger});

  final Json expense;
  final VoidCallback onChanged;
  final ScaffoldMessengerState? messenger;

  @override
  ConsumerState<_ExpenseSheet> createState() => _ExpenseSheetState();
}

class _ExpenseSheetState extends ConsumerState<_ExpenseSheet> {
  late final _amount = TextEditingController(text: '${widget.expense['amount']}');
  late final _note =
      TextEditingController(text: widget.expense['description'] as String? ?? '');
  late final _vendor =
      TextEditingController(text: widget.expense['vendor'] as String? ?? '');
  late final _day = TextEditingController(text: '${widget.expense['spent_at']}');
  String? _problem;
  bool _busy = false;

  Json get _e => widget.expense;
  String get _id => _e['id'] as String;

  @override
  void dispose() {
    for (final c in [_amount, _note, _vendor, _day]) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> _run(Future<void> Function() job, {String? done}) async {
    setState(() {
      _busy = true;
      _problem = null;
    });
    try {
      await job();
      widget.onChanged();
      if (mounted) Navigator.of(context).pop();
      if (done != null) widget.messenger?.showSnackBar(SnackBar(content: Text(done)));
    } catch (e) {
      if (mounted) setState(() => _problem = errorText(e));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Json _patch() => {
        if (_amount.text.trim() != '${_e['amount']}') 'amount': _amount.text.trim(),
        if (_note.text.trim() != (_e['description'] ?? '')) 'note': _note.text.trim(),
        if (_vendor.text.trim() != (_e['vendor'] ?? '')) 'vendor': _vendor.text.trim(),
        if (_day.text.trim() != '${_e['spent_at']}') 'spent_at': _day.text.trim(),
      };

  Future<void> _save() async {
    final patch = _patch();
    if (patch.isEmpty) return Navigator.of(context).pop();
    await _run(() => ref.read(moneyApiProvider).patch(_id, patch));
  }

  Future<void> _delete() async {
    final api = ref.read(moneyApiProvider);
    final onChanged = widget.onChanged;
    final messenger = widget.messenger;
    await _run(() => api.delete(_id));
    messenger?.hideCurrentSnackBar();
    messenger?.showSnackBar(SnackBar(
      content: const Text('Expense deleted'),
      persist: false,
      action: SnackBarAction(
        label: 'Undo',
        onPressed: () async {
          try {
            await api.restore(_id);
            onChanged();
          } catch (e) {
            messenger.showSnackBar(SnackBar(content: Text(errorText(e))));
          }
        },
      ),
    ));
  }

  @override
  Widget build(BuildContext context) {
    final starred = _e['is_favorite'] == true;
    final isVoid = _e['status'] == 'void';
    return Padding(
      padding: EdgeInsets.fromLTRB(Tokens.space4, Tokens.space4, Tokens.space4,
          MediaQuery.of(context).viewInsets.bottom + Tokens.space4),
      child: SingleChildScrollView(
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          TextField(
              controller: _amount,
              keyboardType: const TextInputType.numberWithOptions(decimal: true),
              decoration: const InputDecoration(labelText: 'Amount')),
          TextField(controller: _note, decoration: const InputDecoration(labelText: 'Note')),
          TextField(controller: _vendor, decoration: const InputDecoration(labelText: 'Vendor')),
          TextField(
              controller: _day,
              decoration: const InputDecoration(labelText: 'Day (YYYY-MM-DD)')),
          if (_problem != null)
            Padding(
              padding: const EdgeInsets.only(top: Tokens.space2),
              child: Text(_problem!, style: const TextStyle(color: Tokens.dangerText)),
            ),
          const SizedBox(height: Tokens.space3),
          Wrap(spacing: Tokens.space2, children: [
            FilledButton(onPressed: _busy ? null : _save, child: const Text('Save')),
            OutlinedButton(
              onPressed: _busy
                  ? null
                  : () => _run(() => ref.read(moneyApiProvider).star(_id, !starred)),
              child: Text(starred ? 'Unstar' : 'Star'),
            ),
            OutlinedButton(
              onPressed: _busy
                  ? null
                  : () => _run(() => ref.read(moneyApiProvider).voidIt(_id, !isVoid)),
              child: Text(isVoid ? 'Restore' : 'Void'),
            ),
            TextButton(
              onPressed: _busy ? null : _delete,
              child: const Text('Delete', style: TextStyle(color: Tokens.danger)),
            ),
          ]),
        ]),
      ),
    );
  }
}
