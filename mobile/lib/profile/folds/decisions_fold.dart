import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../widgets/profile_kit.dart';
import '../format.dart';
import 'memory_fold.dart';

/// Decisions: the options you picked for this bot; Forget lets it ask again.
class DecisionsFold extends ConsumerWidget {
  const DecisionsFold({super.key, required this.botId});

  final String botId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return LoadView<List<Map<String, dynamic>>>(
      load: () => loadMemories(ref, botId, kind: 'decision'),
      builder: (context, rows, reload) {
        final items = [
          for (final m in rows)
            if (parseDecision(m['text'] as String? ?? '') case final d?) (m, d),
        ];
        if (items.isEmpty) return const Quiet('No decisions yet.');
        return Column(children: [
          for (final (m, d) in items)
            ListTile(
              contentPadding: EdgeInsets.zero,
              title: Text(d.question),
              subtitle: Text(
                  '${d.answer}\n${appShort(m['updated_at'] as String? ?? '')}'),
              isThreeLine: true,
              trailing: TextButton(
                onPressed: () async {
                  final ok = await attempt(
                      context, () => forgetMemory(ref, m['id'] as String));
                  if (ok) await reload();
                },
                child: const Text('Forget'),
              ),
            ),
        ]);
      },
    );
  }
}
