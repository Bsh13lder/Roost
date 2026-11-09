import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../theme/accent.dart';
import '../../theme/tokens.dart';
import '../common/widgets.dart';
import 'expense_chips.dart';
import 'money_api.dart';

const _debounce = Duration(milliseconds: 300);
const _hint = 'Add an expense… try “€12 lunch /Trip yesterday”';

/// The expense quick line: as you type, the server's reading shows as chips,
/// and Add sends exactly that reading (or says what to fix). A chip's × leaves
/// its words in the note. [projectId] is a project page's own.
class ExpenseLine extends ConsumerStatefulWidget {
  const ExpenseLine({super.key, this.projectId, required this.onAdded});

  final String? projectId;
  final VoidCallback onAdded;

  @override
  ConsumerState<ExpenseLine> createState() => _ExpenseLineState();
}

class _ExpenseLineState extends ConsumerState<ExpenseLine> {
  final _text = TextEditingController();
  final List<String> _skip = [];
  Timer? _timer;
  int _seq = 0;
  Json? _line;
  String? _problem;
  bool _busy = false;

  @override
  void dispose() {
    _timer?.cancel();
    _text.dispose();
    super.dispose();
  }

  void _changed(String _) {
    _timer?.cancel();
    setState(() => _problem = null);
    if (_text.text.trim().isEmpty) {
      _skip.clear();
      setState(() => _line = null);
      return;
    }
    _timer = Timer(_debounce, _read);
  }

  Future<void> _read() async {
    final mine = ++_seq;
    try {
      final line = await ref.read(moneyApiProvider).parse(_text.text,
          projectId: widget.projectId, skip: List.of(_skip));
      if (mounted && mine == _seq) setState(() => _line = line);
    } catch (_) {
      // The chips are a hint; Add reads the line again and shows the error.
    }
  }

  void _dismiss(String kind) {
    _skip.add(kind);
    _read();
  }

  Future<void> _add() async {
    if (_text.text.trim().isEmpty || _busy) return;
    setState(() {
      _busy = true;
      _problem = null;
    });
    try {
      final api = ref.read(moneyApiProvider);
      final read = await api.parse(_text.text,
          projectId: widget.projectId, skip: List.of(_skip));
      final blocker = blockerOf(read);
      if (blocker != null) {
        if (mounted) setState(() => _problem = blocker);
        return;
      }
      await api.create(expenseBodyOf(read, projectId: widget.projectId));
      if (!mounted) return;
      _text.clear();
      _skip.clear();
      setState(() => _line = null);
      widget.onAdded();
    } catch (e) {
      if (mounted) setState(() => _problem = errorText(e));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final chips = _line == null ? const <ExpenseChip>[] : chipsOf(_line!);
    return Padding(
      padding: const EdgeInsets.all(Tokens.space4),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Expanded(
            child: TextField(
              controller: _text,
              onChanged: _changed,
              onSubmitted: (_) => _add(),
              textInputAction: TextInputAction.done,
              decoration: const InputDecoration(hintText: _hint),
            ),
          ),
          const SizedBox(width: Tokens.space2),
          FilledButton(
            onPressed: _busy ? null : _add,
            child: const Text('Add'),
          ),
        ]),
        if (chips.isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(top: Tokens.space2),
            child: Wrap(spacing: 6, runSpacing: 4, children: [
              for (final c in chips) _chip(c),
            ]),
          ),
        if (_problem != null)
          Padding(
            padding: const EdgeInsets.only(top: Tokens.space2),
            child: Text(_problem!,
                style: const TextStyle(
                    color: Tokens.dangerText, fontSize: Tokens.fsLabel)),
          ),
      ]),
    );
  }

  Widget _chip(ExpenseChip c) {
    final color = switch (c.tone) {
      'ask' => Tokens.warn,
      'warn' => Tokens.textSecondary,
      _ => AccentColors.of(context).soft,
    };
    final removable = c.kind != 'warning';
    return InputChip(
      key: ValueKey('chip-${c.kind}'),
      label: Text(c.label,
          style: TextStyle(color: color, fontSize: Tokens.fsLabel)),
      backgroundColor: AccentColors.of(context).tint,
      onDeleted: removable ? () => _dismiss(c.kind) : null,
      deleteIconColor: Tokens.textSecondary,
      visualDensity: VisualDensity.compact,
    );
  }
}
