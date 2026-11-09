import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../api/providers.dart';
import '../../widgets/profile_kit.dart';

/// Your Mac: folders a bot may use (every bot's when [botId] is null).
/// Revoke here; granting stays on the web.
class FoldersFold extends ConsumerWidget {
  const FoldersFold({super.key, required this.botId});

  final String? botId;

  String get _path => botId == null
      ? '/api/mac/grants'
      : '/api/mac/grants?bot_id=${Uri.encodeComponent(botId!)}';

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return LoadView<List<Map<String, dynamic>>>(
      load: () async {
        final data = await ref.read(apiClientProvider).get(_path) as List;
        return [for (final g in data) (g as Map).cast<String, dynamic>()];
      },
      builder: (context, grants, reload) {
        if (grants.isEmpty) {
          return const Quiet('No folders shared. Share one from the web.');
        }
        return Column(children: [
          for (final g in grants)
            ListTile(
              contentPadding: EdgeInsets.zero,
              title: Text(g['label'] as String? ?? ''),
              subtitle: Text(
                  '${g['path'] ?? ''}\n${g['access'] == 'read' ? 'Read only' : 'Read and write'}'),
              isThreeLine: true,
              trailing: TextButton(
                onPressed: () async {
                  if (!await confirm(context, 'Stop sharing this folder?', 'Revoke')) return;
                  if (!context.mounted) return;
                  final ok = await attempt(
                      context,
                      () => ref.read(apiClientProvider).delete(
                          '/api/mac/grants/${Uri.encodeComponent(g['id'] as String)}'));
                  if (ok) await reload();
                },
                child: const Text('Revoke'),
              ),
            ),
        ]);
      },
    );
  }
}
