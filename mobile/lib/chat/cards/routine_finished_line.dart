import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../api/api_error.dart';
import '../../api/models.dart';
import '../../api/providers.dart';
import '../web_mark.dart';
import 'card_base.dart';

/// "Finished routine · Watch physio: booked. I'll delete it in 7 days." with
/// Resume and Delete now (owner, 2026-11-11; `routine_finished`, schema v48).
/// A line from a tainted run (a page-watch change) wears the web mark.
class RoutineFinishedLine extends ConsumerStatefulWidget {
  const RoutineFinishedLine({super.key, required this.message});
  final Message message;

  @override
  ConsumerState<RoutineFinishedLine> createState() => _RoutineFinishedState();
}

class _RoutineFinishedState extends ConsumerState<RoutineFinishedLine> {
  String? _outcome;
  String? _error;
  bool _busy = false;

  Future<void> _act(String id, String name, {required bool resume}) async {
    setState(() {
      _busy = true;
      _error = null;
    });
    final api = ref.read(apiClientProvider);
    final path = '/api/routines/$id';
    try {
      if (resume) {
        await api.post('$path/resume', {});
      } else {
        await api.delete(path);
      }
      if (mounted) {
        setState(() =>
            _outcome = '${resume ? 'Resumed' : 'Deleted'} routine · $name');
      }
    } on ApiException catch (e) {
      if (mounted) {
        setState(() {
          if (e.status == 404) {
            _outcome = 'That routine is already gone.';
          } else {
            _error = e.message;
          }
        });
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final d = decodeBody(widget.message.body);
    final id = str(d?['routine_id']);
    final text = str(d?['text']);
    if (id.isEmpty || text.isEmpty) return QuietLine(widget.message.body);
    if (_outcome != null) return QuietLine(_outcome!);
    final name = str(d?['name']);
    return Column(children: [
      QuietLine(text,
          trailing: Row(mainAxisSize: MainAxisSize.min, children: [
            if (widget.message.tainted) const WebMark(),
            TextButton(
                onPressed:
                    _busy ? null : () => _act(id, name, resume: true),
                child: const Text('Resume')),
            TextButton(
                onPressed:
                    _busy ? null : () => _act(id, name, resume: false),
                child: const Text('Delete now')),
          ])),
      if (_error != null) CardError(_error!),
    ]);
  }
}
