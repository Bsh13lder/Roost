import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../api/providers.dart';
import '../../widgets/profile_kit.dart';

/// The question book: questions the bot carried on without. Your answer comes
/// back as your own message.
class QuestionsFold extends ConsumerWidget {
  const QuestionsFold({super.key, required this.botId});

  final String botId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final id = Uri.encodeComponent(botId);
    return LoadView<List<Map<String, dynamic>>>(
      load: () async {
        final q = await ref
            .read(apiClientProvider)
            .get('/api/questions?state=open&bot_id=$id') as Map;
        return [
          for (final x in q['questions'] as List)
            (x as Map).cast<String, dynamic>()
        ];
      },
      builder: (context, questions, reload) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (questions.isEmpty) const Quiet('No open questions.'),
          for (final q in questions)
            ListTile(
              contentPadding: EdgeInsets.zero,
              title: Text(q['question'] as String? ?? ''),
              subtitle: Text('Carried on with: ${q['default_choice'] ?? ''}'),
              onTap: () => _answer(context, ref, q, reload),
            ),
        ],
      ),
    );
  }

  Future<void> _answer(BuildContext context, WidgetRef ref,
      Map<String, dynamic> q, Future<void> Function() reload) async {
    final controller = TextEditingController();
    final text = await showDialog<String>(
      context: context,
      builder: (c) => AlertDialog(
        title: Text(q['question'] as String? ?? ''),
        content: TextField(controller: controller, autofocus: true, maxLines: 3),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(c), child: const Text('Cancel')),
          TextButton(
              onPressed: () => Navigator.pop(c, controller.text.trim()),
              child: const Text('Answer')),
        ],
      ),
    );
    controller.dispose();
    if (text == null || text.isEmpty || !context.mounted) return;
    final ok = await attempt(
        context,
        () => ref.read(apiClientProvider).post(
            '/api/questions/${Uri.encodeComponent(q['id'] as String)}/answer',
            {'answer': text}));
    if (ok) await reload();
  }
}
