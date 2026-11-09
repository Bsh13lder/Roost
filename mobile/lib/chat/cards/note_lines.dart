import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../api/api_error.dart';
import '../../api/models.dart';
import '../../api/providers.dart';
import '../../theme/tokens.dart';
import 'card_base.dart';

String _oneLine(String s) =>
    s.replaceAll(RegExp(r'[\u0000-\u001f\u007f]+'), ' ').trim();

/// "Remembered: …" with Undo, which forgets that memory.
class MemoryNoteLine extends ConsumerStatefulWidget {
  const MemoryNoteLine({super.key, required this.message});
  final Message message;

  @override
  ConsumerState<MemoryNoteLine> createState() => _MemoryNoteState();
}

class _MemoryNoteState extends ConsumerState<MemoryNoteLine> {
  String? _outcome;
  bool _busy = false;

  Future<void> _undo(String id, String text) async {
    setState(() => _busy = true);
    try {
      await ref.read(apiClientProvider).delete('/api/memories/$id');
      if (mounted) setState(() => _outcome = 'Forgot: $text');
    } on ApiException catch (e) {
      if (mounted) {
        setState(() =>
            _outcome = e.status == 404 ? 'Already forgotten.' : e.message);
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final d = decodeBody(widget.message.body);
    final id = str(d?['memory_id']);
    final text = str(d?['text']);
    if (id.isEmpty || text.isEmpty) return QuietLine(widget.message.body);
    if (_outcome != null) return QuietLine(_outcome!);
    return QuietLine('Remembered: $text',
        trailing: TextButton(
            onPressed: _busy ? null : () => _undo(id, text),
            child: const Text('Undo')));
  }
}

/// "Not remembered: …" with Remember it: a memory the bot couldn't save after reading a web page.
class MemoryOfferLine extends ConsumerStatefulWidget {
  const MemoryOfferLine({super.key, required this.message});
  final Message message;

  @override
  ConsumerState<MemoryOfferLine> createState() => _MemoryOfferState();
}

class _MemoryOfferState extends ConsumerState<MemoryOfferLine> {
  bool _saved = false;
  bool _busy = false;
  String? _error;

  Future<void> _remember() async {
    setState(() => _busy = true);
    final m = widget.message;
    try {
      await ref
          .read(apiClientProvider)
          .post('/api/threads/${m.threadId}/messages/${m.id}/remember', {});
      if (mounted) setState(() => _saved = true);
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final d = decodeBody(widget.message.body);
    final text = str(d?['text']);
    if (text.isEmpty) return const SizedBox.shrink();
    if (_saved || str(d?['memory_id']).isNotEmpty) {
      return QuietLine('Remembered: $text');
    }
    return QuietLine(_error ?? 'Not remembered: $text',
        trailing: TextButton(
            onPressed: _busy ? null : _remember,
            child: const Text('Remember it')));
  }
}

/// A Mac file change as one quiet line, with Undo while it can be undone.
class MacActivityLine extends ConsumerStatefulWidget {
  const MacActivityLine({super.key, required this.message});
  final Message message;

  @override
  ConsumerState<MacActivityLine> createState() => _MacActivityState();
}

class _MacActivityState extends ConsumerState<MacActivityLine> {
  bool _spent = false;
  bool _busy = false;
  String? _error;

  Future<void> _undo() async {
    setState(() => _busy = true);
    try {
      await ref
          .read(apiClientProvider)
          .post('/api/mac/activity/${widget.message.id}/undo', {});
    } on ApiException catch (e) {
      _error = e.message;
    }
    if (mounted) {
      setState(() {
        _spent = true;
        _busy = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final d = decodeBody(widget.message.body);
    final canUndo =
        d != null && d['undo'] is Map && d['op'] != 'undo' && !_spent;
    return Column(children: [
      QuietLine(macActivityLine(d),
          trailing: canUndo
              ? TextButton(
                  onPressed: _busy ? null : _undo, child: const Text('Undo'))
              : null),
      if (_error != null) CardError(_error!),
    ]);
  }
}

String _nameOf(String path) {
  final parts = path.replaceAll(RegExp(r'/+$'), '').split('/');
  return _oneLine(parts.isEmpty ? '' : parts.last);
}

/// The same words as roost/mac/activity.py.
String macActivityLine(Json? d) {
  if (d == null || d['op'] is! String || d['label'] is! String) {
    return 'Changed a file';
  }
  final name = _nameOf(str(d['path']));
  final label = _oneLine(str(d['label']));
  final mark = d['tainted_basis'] == true ? ' · Based on outside content' : '';
  return switch (d['op']) {
    'create' => 'Created $name · $label$mark',
    'edit' =>
      'Edited $name · $label (+${d['plus'] ?? 0} −${d['minus'] ?? 0})$mark',
    'rename' => 'Renamed $name → ${_nameOf(str(d['new_path']))} · $label$mark',
    'trash' => 'Moved $name to the trash · $label$mark',
    _ => d['undid'] == 'trash'
        ? 'Moved $name back from the trash · $label'
        : 'Undid ${const {
              'edit': 'the edit of',
              'create': 'the creation of',
              'rename': 'the rename of'
            }[d['undid']] ?? 'the change to'} $name · $label',
  };
}

/// "Ran: python3 a.py · exit 0", the output folded under it as plain text.
class ProgramActivityLine extends StatelessWidget {
  const ProgramActivityLine({super.key, required this.body});
  final String body;

  @override
  Widget build(BuildContext context) {
    final d = decodeBody(body);
    final op = d?['op'];
    if (d == null || (op != 'run' && op != 'write')) {
      return const QuietLine('Ran a program');
    }
    if (op == 'write') return QuietLine('Wrote ${_oneLine(str(d['path']))}');
    final timedOut = d['timed_out'] == true;
    final code = (d['exit_code'] as num?)?.toInt() ?? 0;
    final line =
        'Ran: ${_oneLine(str(d['command']))} · ${timedOut ? 'timed out' : 'exit $code'}';
    final output = str(d['output']);
    return Column(children: [
      Padding(
        padding: const EdgeInsets.symmetric(
            vertical: Tokens.space2, horizontal: Tokens.space6),
        child: Text(line,
            textAlign: TextAlign.center,
            style: TextStyle(
                color: timedOut || code != 0 ? Tokens.danger : Tokens.textFaint,
                fontSize: Tokens.fsLabel)),
      ),
      if (output.isNotEmpty)
        Theme(
          data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
          child: ExpansionTile(
            dense: true,
            title: Text('Output${d['cut'] == true ? ' (cut)' : ''}',
                style: const TextStyle(
                    color: Tokens.textFaint, fontSize: Tokens.fsCaption)),
            children: [
              Padding(
                padding: const EdgeInsets.all(Tokens.space3),
                child: SelectableText(output,
                    style: const TextStyle(
                        fontFamily: 'monospace', fontSize: Tokens.fsCaption)),
              ),
            ],
          ),
        ),
    ]);
  }
}
