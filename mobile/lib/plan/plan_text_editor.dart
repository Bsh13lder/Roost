import 'package:flutter/material.dart';

import '../api/api_error.dart';
import '../theme/tokens.dart';
import '../widgets/profile_kit.dart';
import 'plan_models.dart';

typedef PlanSave = Future<PlanData> Function(String content, int baseRevision);

/// Edit as text. A save carries the revision it read; a 409 offers
/// "Load the latest" or "Keep mine" (the server's current copy comes back).
class PlanTextEditor extends StatefulWidget {
  const PlanTextEditor(
      {super.key, required this.plan, required this.save, required this.onSaved});

  final PlanData plan;
  final PlanSave save;
  final ValueChanged<PlanData> onSaved;

  @override
  State<PlanTextEditor> createState() => _PlanTextEditorState();
}

class _PlanTextEditorState extends State<PlanTextEditor> {
  late final _text = TextEditingController(text: widget.plan.content);
  late int _revision = widget.plan.revision;
  bool _busy = false;
  PlanData? _conflict;

  @override
  void dispose() {
    _text.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    setState(() => _busy = true);
    try {
      widget.onSaved(await widget.save(_text.text, _revision));
    } on ApiException catch (e) {
      final current = e.current;
      if (e.isConflict && current != null) {
        setState(() => _conflict = PlanData.fromJson(current));
      } else {
        _say(e.message);
      }
    } catch (e) {
      _say(describe(e));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _say(String s) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(s)));
  }

  void _loadLatest() {
    final c = _conflict!;
    _text.text = c.content;
    setState(() {
      _revision = c.revision;
      _conflict = null;
    });
    widget.onSaved(c);
  }

  void _keepMine() => setState(() {
        _revision = _conflict!.revision;
        _conflict = null;
      });

  @override
  Widget build(BuildContext context) {
    return Column(children: [
      if (_conflict != null)
        MaterialBanner(
          key: const Key('plan-conflict'),
          backgroundColor: Tokens.raised,
          content: const Text('The Plan changed since you opened it.'),
          actions: [
            TextButton(
                onPressed: _loadLatest, child: const Text('Load the latest')),
            TextButton(onPressed: _keepMine, child: const Text('Keep mine')),
          ],
        ),
      Expanded(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: Tokens.space3),
          child: TextField(
            key: const Key('plan-text'),
            controller: _text,
            maxLines: null,
            expands: true,
            textAlignVertical: TextAlignVertical.top,
            style: const TextStyle(
                fontFamily: 'monospace', fontSize: Tokens.fsLabel),
          ),
        ),
      ),
      Padding(
        padding: const EdgeInsets.all(Tokens.space3),
        child: FilledButton(
          key: const Key('plan-save'),
          onPressed: _busy ? null : _save,
          child: const Text('Save'),
        ),
      ),
    ]);
  }
}
