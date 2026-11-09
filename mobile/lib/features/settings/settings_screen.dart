import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../api/account_zone.dart';
import '../../api/providers.dart';
import '../../theme/tokens.dart';
import '../../update/update_row.dart';
import '../../util/app_time.dart';
import '../../widgets/grouped_card.dart';
import '../home/home_data.dart';
import 'accent_swatches.dart';
import 'gateway_field.dart';
import 'notifications_screen.dart';
import 'usage_line.dart';

/// How many Mac folders are shared, over every bot; null when unknown.
final macFolderCountProvider = FutureProvider.autoDispose<int?>((ref) async {
  final data = await ref.watch(apiClientProvider).get('/api/mac/grants');
  return data is List ? data.length : null;
});

String _folders(int? n) => switch (n) {
      null => '',
      1 => '1 folder',
      _ => '$n folders',
    };

/// Settings as grouped cards: Account, Time zone (read only), Connections, your bots' Routines and
/// Skills, Appearance, Notifications, Gateway, Version (with Check for
/// updates) and Sign out.
class SettingsScreen extends ConsumerWidget {
  const SettingsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Scaffold(
      appBar: AppBar(backgroundColor: Tokens.bg, title: const Text('Settings')),
      body: ListView(
        children: [
          const _Account(),
          const _TimeZone(),
          const UsageLine(),
          ..._connections(context, ref),
          const GroupedCard(label: 'Appearance', children: [
            CardBody(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Accent colour',
                      style: TextStyle(fontSize: Tokens.fsLead)),
                  SizedBox(height: Tokens.space3),
                  AccentSwatches(),
                ],
              ),
            ),
          ]),
          _notifications(context, ref),
          const GroupedCard(
              label: 'Gateway', children: [CardBody(child: GatewayField())]),
          const UpdateCard(),
          GroupedCard(children: [
            NavRow(
              key: const Key('settings-sign-out'),
              icon: Icons.logout,
              label: 'Sign out',
              danger: true,
              onTap: () => ref.read(authProvider.notifier).signOut(),
            ),
          ]),
          const SizedBox(height: Tokens.space8),
        ],
      ),
    );
  }

  List<Widget> _connections(BuildContext context, WidgetRef ref) {
    final folders = ref.watch(macFolderCountProvider).valueOrNull;
    return [
      GroupedCard(label: 'Connections', children: [
        NavRow(
          icon: Icons.link,
          label: 'Connectors',
          onTap: () => context.push('/connectors'),
        ),
        NavRow(
          icon: Icons.folder_outlined,
          label: 'Your Mac: folders',
          value: _folders(folders),
          onTap: () => context.push('/mac-folders'),
        ),
        NavRow(
          icon: Icons.credit_card,
          label: 'Vault: cards',
          onTap: () => context.push('/payment-cards'),
        ),
        NavRow(
          key: const Key('settings-vault-passwords'),
          icon: Icons.key_outlined,
          label: 'Vault: passwords',
          onTap: () => context.push('/vault-passwords'),
        ),
      ]),
      GroupedCard(label: 'Your bots', children: [
        NavRow(
          icon: Icons.schedule,
          label: 'Routines',
          onTap: () => context.push('/routines'),
        ),
        NavRow(
          icon: Icons.menu_book_outlined,
          label: 'Skills',
          onTap: () => context.push('/skills'),
        ),
      ]),
    ];
  }

  Widget _notifications(BuildContext context, WidgetRef ref) {
    final rows = ref.watch(notifyRowsProvider).valueOrNull ?? const [];
    return GroupedCard(children: [
      NavRow(
        icon: Icons.notifications_none,
        label: 'Notifications',
        value: notifySummary(rows),
        onTap: () => context.push('/notifications'),
      ),
    ]);
  }
}

class _Account extends ConsumerWidget {
  const _Account();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final name = ref.watch(usernameProvider).valueOrNull ?? '';
    final base = ref.watch(authProvider).baseUrl;
    return GroupedCard(label: 'Account', children: [
      Padding(
        padding: const EdgeInsets.all(Tokens.space4),
        child: Row(children: [
          CircleAvatar(
            radius: 24,
            backgroundColor: Tokens.raised,
            child: Text(initialsOf(name),
                style: const TextStyle(
                    color: Tokens.text, fontSize: Tokens.fsLead)),
          ),
          const SizedBox(width: Tokens.space4),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(name,
                    style: const TextStyle(
                        fontSize: Tokens.fsHeading,
                        fontWeight: FontWeight.w600)),
                Text(base,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(color: Tokens.textSecondary)),
              ],
            ),
          ),
        ]),
      ),
    ]);
  }
}

/// The account's time zone, read only: the web on your computer sets it.
class _TimeZone extends ConsumerWidget {
  const _TimeZone();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    // Rebuilds once /api/auth/me has named the zone.
    ref.watch(accountZoneProvider);
    return GroupedCard(
      caption: 'Change it in Roost on your computer.',
      children: [
        NavRow(
          key: const Key('settings-time-zone'),
          icon: Icons.public,
          label: 'Time zone',
          value: zoneCity(),
        ),
      ],
    );
  }
}
