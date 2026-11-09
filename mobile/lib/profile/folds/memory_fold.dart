import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../api/providers.dart';
import '../../widgets/profile_kit.dart';
import '../format.dart';

Future<List<Map<String, dynamic>>> loadMemories(
    WidgetRef ref, String botId, {String? kind}) async {
  final path = '/api/memories?bot_id=${Uri.encodeComponent(botId)}'
      '${kind == null ? '' : '&kind=$kind'}';
  final data = await ref.read(apiClientProvider).get(path) as List;
  return [for (final m in data) (m as Map).cast<String, dynamic>()];
}

Future<void> forgetMemory(WidgetRef ref, String id) =>
    ref.read(apiClientProvider).delete('/api/memories/${Uri.encodeComponent(id)}');

Future<void> editMemory(WidgetRef ref, String id, String text) => ref
    .read(apiClientProvider)
    .patch('/api/memories/${Uri.encodeComponent(id)}', {'text': text});

/// What I remember: About you and this bot's own, each with Edit and Forget.
class MemoryFold extends ConsumerWidget {
  const MemoryFold({super.key, required this.botId});

  final String botId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return LoadView<List<Map<String, dynamic>>>(
      load: () => loadMemories(ref, botId),
      builder: (context, all, reload) {
        final rows = [for (final m in all) if (m['kind'] != 'decision') m];
        if (rows.isEmpty) return const Quiet('Nothing remembered yet.');
        return Column(children: [
          for (final m in rows)
            ListTile(
              contentPadding: EdgeInsets.zero,
              title: Text(m['text'] as String? ?? ''),
              subtitle: Text(
                  '${m['bot_id'] == null ? 'About you' : 'This bot'} · ${appShort(m['updated_at'] as String? ?? '')}'),
              trailing: Row(mainAxisSize: MainAxisSize.min, children: [
                TextButton(
                  onPressed: () => _edit(context, ref, m, reload),
                  child: const Text('Edit'),
                ),
                TextButton(
                  onPressed: () async {
                    final ok = await attempt(
                        context, () => forgetMemory(ref, m['id'] as String));
                    if (ok) await reload();
                  },
                  child: const Text('Forget'),
                ),
              ]),
            ),
        ]);
      },
    );
  }

  Future<void> _edit(BuildContext context, WidgetRef ref,
      Map<String, dynamic> m, Future<void> Function() reload) async {
    final old = m['text'] as String? ?? '';
    final text = await showDialog<String>(
        context: context, builder: (_) => _EditMemoryDialog(text: old));
    if (text == null || text.isEmpty || text == old || !context.mounted) return;
    final ok = await attempt(
        context, () => editMemory(ref, m['id'] as String, text));
    if (ok) await reload();
  }
}

/// The Edit memory dialog; it owns its text field's controller.
class _EditMemoryDialog extends StatefulWidget {
  const _EditMemoryDialog({required this.text});
  final String text;

  @override
  State<_EditMemoryDialog> createState() => _EditMemoryDialogState();
}

class _EditMemoryDialogState extends State<_EditMemoryDialog> {
  late final _controller = TextEditingController(text: widget.text);

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: const Text('Edit memory'),
        content: TextField(controller: _controller, autofocus: true, maxLines: 4),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Cancel')),
          TextButton(
              onPressed: () => Navigator.pop(context, _controller.text.trim()),
              child: const Text('Save')),
        ],
      );
}
