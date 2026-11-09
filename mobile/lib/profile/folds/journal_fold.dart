import 'package:flutter/material.dart';
import 'package:flutter_markdown_plus/flutter_markdown_plus.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../api/providers.dart';
import '../../theme/tokens.dart';
import '../../widgets/profile_kit.dart';

/// Journal: one Obsidian daily note per account-zone day, read only.
class JournalFold extends ConsumerWidget {
  const JournalFold({super.key, required this.botId});

  final String botId;

  String get _path => '/api/bots/${Uri.encodeComponent(botId)}/journal';

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return LoadView<List<Map<String, dynamic>>>(
      load: () async {
        final data = await ref.read(apiClientProvider).get(_path) as Map;
        return [for (final d in data['days'] as List) (d as Map).cast<String, dynamic>()];
      },
      builder: (context, days, _) {
        if (days.isEmpty) return const Quiet('Nothing written yet.');
        return Column(children: [
          for (final d in days)
            ListTile(
              contentPadding: EdgeInsets.zero,
              title: Text(d['day'] as String? ?? ''),
              subtitle: Text('${d['entries']} entries'),
              trailing: const Icon(Icons.chevron_right, color: Tokens.textFaint),
              onTap: () => _open(context, ref, d['day'] as String),
            ),
        ]);
      },
    );
  }

  Future<void> _open(BuildContext context, WidgetRef ref, String day) async {
    String? content;
    final ok = await attempt(context, () async {
      final data = await ref
          .read(apiClientProvider)
          .get('$_path/${Uri.encodeComponent(day)}') as Map;
      content = data['content'] as String? ?? '';
    });
    if (!ok || !context.mounted) return;
    await Navigator.of(context).push(MaterialPageRoute<void>(
      builder: (_) => Scaffold(
        appBar: AppBar(title: Text(day), backgroundColor: Tokens.bg),
        body: Markdown(data: content ?? '', selectable: true),
      ),
    ));
  }
}
