import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../theme/tokens.dart';
import '../common/format.dart';
import '../common/widgets.dart';
import 'project_edit.dart';
import 'projects_api.dart';

/// A project's top-ups: add one, Change an amount, Undo. The server writes
/// the difference of a change as a "Top-up changed" row.
class TopupsSheet extends ConsumerStatefulWidget {
  const TopupsSheet({super.key, required this.project});

  final Json project;

  @override
  ConsumerState<TopupsSheet> createState() => _TopupsSheetState();
}

class _TopupsSheetState extends ConsumerState<TopupsSheet> {
  late List<Json> _rows = _read(widget.project['topups']);
  final _amount = TextEditingController();
  final _source = TextEditingController();
  bool _busy = false;
  bool _changed = false;
  String? _error;

  static List<Json> _read(Object? v) =>
      [for (final r in (v as List? ?? const [])) Map<String, dynamic>.from(r as Map)];

  String get _id => '${widget.project['id']}';
  String get _currency => '${widget.project['currency']}';

  @override
  void dispose() {
    _amount.dispose();
    _source.dispose();
    super.dispose();
  }

  Future<void> _run(Future<void> Function(ProjectsApi api) call) async {
    setState(() {
      _busy = true;
      _error = null;
    });
    final api = ref.read(projectsApiProvider);
    try {
      await call(api);
      final fresh = await api.get(_id);
      if (mounted) {
        setState(() {
          _rows = _read(fresh['topups']);
          _changed = true;
        });
      }
    } catch (e) {
      if (mounted) setState(() => _error = errorText(e));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _add() async {
    final amount = readAmount(_amount.text);
    if (amount == null) return setState(() => _error = amountHint);
    final source = _source.text.trim();
    await _run((api) => api.addTopup(_id, amount, source.isEmpty ? null : source));
    if (_error == null) {
      _amount.clear();
      _source.clear();
    }
  }

  Future<void> _change(Json row) async {
    final c = TextEditingController(text: '${row['amount']}');
    final value = await showDialog<String>(
      context: context,
      builder: (d) => AlertDialog(
        title: const Text('Change this top-up'),
        content: TextField(
            controller: c,
            autofocus: true,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            decoration: const InputDecoration(labelText: 'New amount')),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(d), child: const Text('Cancel')),
          TextButton(
              onPressed: () => Navigator.pop(d, c.text),
              child: const Text('Change')),
        ],
      ),
    );
    c.dispose();
    if (value == null) return;
    final amount = readAmount(value);
    if (amount == null) return setState(() => _error = amountHint);
    await _run((api) => api.editTopup('${row['id']}', amount));
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) Navigator.pop(context, _changed);
      },
      child: Padding(
        padding: EdgeInsets.fromLTRB(Tokens.space4, 0, Tokens.space4,
            MediaQuery.of(context).viewInsets.bottom + Tokens.space4),
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const Text('Top-ups',
                  style: TextStyle(
                      fontSize: Tokens.fsHeading, fontWeight: FontWeight.w600)),
              const SizedBox(height: Tokens.space3),
              Row(children: [
                Expanded(
                  child: TextField(
                      key: const Key('topup-amount'),
                      controller: _amount,
                      keyboardType:
                          const TextInputType.numberWithOptions(decimal: true),
                      decoration: InputDecoration(labelText: 'Amount ($_currency)')),
                ),
                const SizedBox(width: Tokens.space2),
                Expanded(
                  child: TextField(
                      controller: _source,
                      decoration: const InputDecoration(labelText: 'From (optional)')),
                ),
              ]),
              const SizedBox(height: Tokens.space2),
              FilledButton(
                  key: const Key('topup-add'),
                  onPressed: _busy ? null : _add,
                  child: const Text('Add top-up')),
              if (_error != null)
                Padding(
                  padding: const EdgeInsets.only(top: Tokens.space2),
                  child: Text(_error!,
                      style: const TextStyle(color: Tokens.dangerText)),
                ),
              const SizedBox(height: Tokens.space3),
              if (_rows.isEmpty) const BoardNote('No top-ups yet.'),
              for (final r in _rows) _row(r),
            ],
          ),
        ),
      ),
    );
  }

  Widget _row(Json r) {
    final edit = r['kind'] == 'edit';
    final undone = r['undone'] == true;
    final source = r['source'];
    final label = edit
        ? 'Top-up changed'
        : (source == null ? 'Top-up' : 'Top-up from $source');
    return ListTile(
      dense: true,
      contentPadding: EdgeInsets.zero,
      title: Text(
          '${edit ? '' : '+'}${formatMoney('${r['amount']}', _currency)}  $label',
          style: TextStyle(
              decoration: undone ? TextDecoration.lineThrough : null,
              color: undone ? Tokens.textFaint : Tokens.text)),
      subtitle: Text('${r['created_at']}'.length >= 10
          ? dayLabel('${r['created_at']}'.substring(0, 10))
          : ''),
      trailing: r['can_change'] == true
          ? Row(mainAxisSize: MainAxisSize.min, children: [
              TextButton(
                  onPressed: _busy ? null : () => _change(r),
                  child: const Text('Change')),
              TextButton(
                  onPressed: _busy
                      ? null
                      : () => _run((api) => api.undoTopup('${r['id']}')),
                  child: const Text('Undo')),
            ])
          : null,
    );
  }
}
