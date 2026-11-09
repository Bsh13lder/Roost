import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../theme/tokens.dart';
import '../common/format.dart';
import '../common/widgets.dart';
import 'projects_api.dart';

final _amountPattern = RegExp(r'^\d{1,9}(\.\d{1,2})?$');

/// An amount typed as "12,50" or "12.5", as the server wants it ("12.50"), or
/// null when it is not an amount more than 0.
String? readAmount(String raw) {
  final text = raw.trim().replaceAll(',', '.');
  if (!_amountPattern.hasMatch(text)) return null;
  final n = double.parse(text);
  if (n <= 0) return null;
  return n.toStringAsFixed(2);
}

const amountHint = 'Use a number like 12.50.';

/// Edit a project: name, total budget, monthly limit, start and due days, and
/// archive. Pops true when something was saved.
class ProjectEditSheet extends ConsumerStatefulWidget {
  const ProjectEditSheet({super.key, required this.project});

  final Json project;

  @override
  ConsumerState<ProjectEditSheet> createState() => _ProjectEditSheetState();
}

class _ProjectEditSheetState extends ConsumerState<ProjectEditSheet> {
  late final _name = TextEditingController(text: '${widget.project['name']}');
  late final _total = TextEditingController(text: _line('total'));
  late final _monthly = TextEditingController(text: _line('month'));
  late String? _start = widget.project['start_date'] as String?;
  late String? _due = widget.project['due_date'] as String?;
  late bool _archived = widget.project['status'] == 'archived';
  bool _busy = false;
  String? _error;

  String _line(String key) {
    final b = (widget.project[key] as Map?)?['budget'];
    return b == null ? '' : '$b';
  }

  @override
  void dispose() {
    _name.dispose();
    _total.dispose();
    _monthly.dispose();
    super.dispose();
  }

  /// Blank clears; anything else must read as an amount.
  (bool, String?) _amount(TextEditingController c) {
    if (c.text.trim().isEmpty) return (true, null);
    final a = readAmount(c.text);
    return (a != null, a);
  }

  Future<void> _pickDay(bool start) async {
    final now = DateTime.tryParse(appTodayIso()) ?? DateTime.now();
    final picked = await showDatePicker(
      context: context,
      initialDate: DateTime.tryParse((start ? _start : _due) ?? '') ?? now,
      firstDate: DateTime(2020),
      lastDate: DateTime(2100),
    );
    if (picked == null) return;
    final text = picked.toIso8601String().substring(0, 10);
    setState(() => start ? _start = text : _due = text);
  }

  Future<void> _save() async {
    final name = _name.text.trim();
    final (totalOk, total) = _amount(_total);
    final (monthOk, monthly) = _amount(_monthly);
    if (name.isEmpty) return setState(() => _error = 'Give the project a name.');
    if (!totalOk || !monthOk) return setState(() => _error = amountHint);
    setState(() {
      _busy = true;
      _error = null;
    });
    final api = ref.read(projectsApiProvider);
    final id = '${widget.project['id']}';
    try {
      await api.update(id, {
        'name': name,
        'start_date': _start,
        'due_date': _due,
        'monthly_budget': monthly,
        'status': _archived ? 'archived' : 'active',
      });
      final before =
          double.tryParse('${(widget.project['total'] as Map?)?['budget'] ?? ''}');
      final after = total == null ? null : double.parse(total);
      if (before != after) await api.setBudget(id, total);
      if (mounted) Navigator.pop(context, true);
    } catch (e) {
      if (mounted) setState(() => _error = errorText(e));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final currency = '${widget.project['currency']}';
    return Padding(
      padding: EdgeInsets.fromLTRB(Tokens.space4, 0, Tokens.space4,
          MediaQuery.of(context).viewInsets.bottom + Tokens.space4),
      child: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Text('Edit project',
                style: TextStyle(
                    fontSize: Tokens.fsHeading, fontWeight: FontWeight.w600)),
            const SizedBox(height: Tokens.space3),
            TextField(
                key: const Key('project-name'),
                controller: _name,
                decoration: const InputDecoration(labelText: 'Name')),
            const SizedBox(height: Tokens.space3),
            TextField(
                key: const Key('project-total'),
                controller: _total,
                keyboardType: const TextInputType.numberWithOptions(decimal: true),
                decoration: InputDecoration(
                    labelText: 'Total budget ($currency)',
                    helperText: 'Leave empty for none. Top-ups raise it.')),
            const SizedBox(height: Tokens.space3),
            TextField(
                key: const Key('project-monthly'),
                controller: _monthly,
                keyboardType: const TextInputType.numberWithOptions(decimal: true),
                decoration: InputDecoration(
                    labelText: 'Monthly limit ($currency)',
                    helperText: 'Leave empty for none.')),
            const SizedBox(height: Tokens.space2),
            _dayRow('Start', _start, true),
            _dayRow('Due', _due, false),
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text('Archived'),
              value: _archived,
              onChanged: (v) => setState(() => _archived = v),
            ),
            if (_error != null)
              Padding(
                padding: const EdgeInsets.only(bottom: Tokens.space2),
                child: Text(_error!,
                    style: const TextStyle(color: Tokens.dangerText)),
              ),
            FilledButton(
              key: const Key('project-save'),
              onPressed: _busy ? null : _save,
              child: Text(_busy ? 'Saving…' : 'Save changes'),
            ),
          ],
        ),
      ),
    );
  }

  Widget _dayRow(String label, String? day, bool start) => Row(children: [
        Expanded(child: Text('$label: ${day == null ? 'none' : dayLabel(day)}')),
        TextButton(
            onPressed: () => _pickDay(start), child: const Text('Pick a day')),
        if (day != null)
          TextButton(
              onPressed: () => setState(() => start ? _start = null : _due = null),
              child: const Text('Clear')),
      ]);
}
