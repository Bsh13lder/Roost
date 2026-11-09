import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/providers.dart';
import '../theme/tokens.dart';
import '../widgets/profile_kit.dart';
import 'connector_form.dart';

/// Connectors with Add connector and tap-to-edit. With a [botId] only the
/// connectors that bot may use are listed (the Profile's fold); without one,
/// all of them (the settings sheet's screen).
class ConnectorsList extends ConsumerWidget {
  const ConnectorsList({super.key, this.botId});

  final String? botId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return LoadView<List<Json>>(
      load: () async {
        final data = await ref.read(apiClientProvider).get('/api/connectors') as List;
        return [for (final c in data) (c as Map).cast<String, dynamic>()];
      },
      builder: (context, rows, reload) {
        final shown = [
          for (final c in rows)
            if (botId == null ||
                c['bot_ids'] == null ||
                (c['bot_ids'] as List).contains(botId))
              c,
        ];
        return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          if (shown.isEmpty)
            const Quiet(
                "No connectors yet. Add one to let your bots use a service's API with your key."),
          for (final c in shown)
            ListTile(
              contentPadding: EdgeInsets.zero,
              title: Text('${c['name'] ?? ''}'),
              subtitle: Text('${c['host'] ?? ''} · ${c['key_hint'] ?? ''}'),
              trailing: const Icon(Icons.chevron_right, color: Tokens.textFaint),
              onTap: () async {
                if (await showConnectorForm(context, botId: botId, connector: c)) {
                  await reload();
                }
              },
            ),
          TextButton.icon(
            key: const Key('add-connector'),
            icon: const Icon(Icons.add),
            label: const Text('Add connector'),
            onPressed: () async {
              if (await showConnectorForm(context, botId: botId)) await reload();
            },
          ),
        ]);
      },
    );
  }
}
