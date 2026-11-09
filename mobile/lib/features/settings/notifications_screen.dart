import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../api/providers.dart';
import '../../theme/tokens.dart';
import '../../widgets/grouped_card.dart';
import '../../widgets/profile_kit.dart';
import 'stay_connected_section.dart';

/// One bot's notification switch (`bots.notify`).
@immutable
class NotifyRow {
  const NotifyRow({required this.id, required this.name, required this.on});

  factory NotifyRow.fromJson(Map<String, dynamic> j) => NotifyRow(
      id: '${j['id']}', name: '${j['name'] ?? ''}', on: j['notify'] == true);

  final String id, name;
  final bool on;
}

/// Every bot's switch, read from `GET /api/bots`.
final notifyRowsProvider =
    FutureProvider.autoDispose<List<NotifyRow>>((ref) async {
  final data = await ref.watch(apiClientProvider).get('/api/bots');
  return [
    if (data is List)
      for (final b in data)
        if (b is Map) NotifyRow.fromJson(b.cast<String, dynamic>()),
  ];
});

/// "1 of 2 bots" for the Settings row.
String notifySummary(List<NotifyRow> rows) =>
    rows.isEmpty ? '' : '${rows.where((r) => r.on).length} of ${rows.length} bots';

/// Notifications: Stay connected and what it tells you, then each bot's own
/// switch, the same one as on its profile.
class NotificationsScreen extends ConsumerWidget {
  const NotificationsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final rows = ref.watch(notifyRowsProvider);
    return Scaffold(
      appBar:
          AppBar(backgroundColor: Tokens.bg, title: const Text('Notifications')),
      body: ListView(children: [
        const StayConnectedSection(),
        rows.when(
          loading: () => const Padding(
            padding: EdgeInsets.all(Tokens.space6),
            child: Center(child: CircularProgressIndicator()),
          ),
          error: (e, _) => Center(
            child: TextButton(
              onPressed: () => ref.invalidate(notifyRowsProvider),
              child: Text('${describe(e)} Try again'),
            ),
          ),
          data: (list) => GroupedCard(
            label: 'Bots',
            caption: 'Get told when a bot finishes or is waiting for you.',
            children: [
              for (final r in list)
                SwitchRow(
                  switchKey: Key('notify-${r.id}'),
                  label: r.name,
                  value: r.on,
                  onChanged: (on) => _save(context, ref, r.id, on),
                ),
            ],
          ),
        ),
      ]),
    );
  }

  Future<void> _save(
      BuildContext context, WidgetRef ref, String botId, bool on) async {
    final ok = await attempt(
        context,
        () => ref.read(apiClientProvider).put(
            '/api/bots/${Uri.encodeComponent(botId)}/notify', {'notify': on}));
    if (ok) ref.invalidate(notifyRowsProvider);
  }
}
