import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../api/providers.dart';
import '../theme/tokens.dart';
import '../widgets/grouped_card.dart';
import '../widgets/lensbot.dart';
import '../widgets/profile_kit.dart';
import 'bot_detail.dart';
import 'bot_menu.dart';
import 'edit_bot_sheet.dart';
import 'pages/bot_settings_page.dart';
import 'pages/computer_page.dart';
import 'pages/library_page.dart';
import 'pages/plan_routines_page.dart';
import 'profile_values.dart';

/// A bot's Profile: a big Lensbot, its name and Edit, then one card of rows
/// (Plan & routines · Computer · Library · Settings), each its own page, and
/// the Notifications switch.
class ProfileScreen extends ConsumerWidget {
  const ProfileScreen({super.key, required this.botId});

  final String botId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final detail = ref.watch(botDetailProvider(botId));
    return Scaffold(
      appBar: AppBar(
        backgroundColor: Tokens.bg,
        actions: [
          if (detail.hasValue) BotMenu(bot: detail.requireValue),
        ],
      ),
      body: detail.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(
          child: TextButton(
            onPressed: () => ref.invalidate(botDetailProvider(botId)),
            child: Text('${describe(e)} Try again'),
          ),
        ),
        data: (bot) => ListView(children: [
          _Hero(bot: bot),
          _Rows(bot: bot),
          _NotifyCard(bot: bot),
          const SizedBox(height: Tokens.space8),
        ]),
      ),
    );
  }
}

class _Hero extends StatelessWidget {
  const _Hero({required this.bot});

  final BotDetail bot;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(
          Tokens.space4, 0, Tokens.space4, Tokens.space4),
      child: Column(children: [
        LensbotAvatar(
            avatar: bot.avatar,
            size: 140,
            star: bot.isPrimary,
            status: bot.status),
        const SizedBox(height: Tokens.space3),
        Text(bot.name,
            style: const TextStyle(
                fontSize: Tokens.fsDisplay, fontWeight: FontWeight.w600)),
        if (bot.job.isNotEmpty)
          Text(bot.job,
              textAlign: TextAlign.center,
              style: const TextStyle(color: Tokens.textSecondary)),
        const SizedBox(height: Tokens.space3),
        FilledButton.tonal(
          key: const Key('profile-edit'),
          style: FilledButton.styleFrom(
            backgroundColor: Tokens.raised,
            foregroundColor: Tokens.text,
            shape: const StadiumBorder(),
          ),
          onPressed: () => showEditBotSheet(context, bot),
          child: const Text('Edit'),
        ),
      ]),
    );
  }
}

class _Rows extends ConsumerWidget {
  const _Rows({required this.bot});

  final BotDetail bot;

  void _open(BuildContext context, Widget page) => Navigator.of(context)
      .push(MaterialPageRoute<void>(builder: (_) => page));

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final routines = ref.watch(botRoutinesProvider(bot.id)).valueOrNull;
    final desk = ref.watch(deskProvider(bot.id)).valueOrNull;
    return GroupedCard(children: [
      NavRow(
        key: const Key('row-plan'),
        icon: Icons.event_note_outlined,
        label: 'Plan & routines',
        value: routines == null ? '' : routinesOnLabel(routines),
        onTap: () => _open(context, PlanRoutinesPage(botId: bot.id)),
      ),
      NavRow(
        key: const Key('row-computer'),
        icon: Icons.desktop_windows_outlined,
        label: 'Computer',
        value: computerStatusWord(bot.status, desk),
        onTap: () => _open(context, ComputerPage(botId: bot.id)),
      ),
      NavRow(
        key: const Key('row-library'),
        icon: Icons.folder_outlined,
        label: 'Library',
        onTap: () => _open(context, LibraryPage(botId: bot.id)),
      ),
      NavRow(
        key: const Key('row-settings'),
        icon: Icons.tune,
        label: 'Settings',
        onTap: () => _open(context, BotSettingsPage(botId: bot.id)),
      ),
    ]);
  }
}

class _NotifyCard extends ConsumerWidget {
  const _NotifyCard({required this.bot});

  final BotDetail bot;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return GroupedCard(
      caption: notifyCaption,
      children: [
        SwitchRow(
          switchKey: const Key('profile-notify'),
          label: 'Notifications',
          value: bot.notify,
          onChanged: (on) => attempt(context, () async {
            final saved = await ref
                .read(apiClientProvider)
                .put('/api/bots/${bot.id}/notify', {'notify': on});
            ref.read(botDetailProvider(bot.id).notifier).replace(saved);
          }),
        ),
      ],
    );
  }
}

/// Used by the chat header's bot pill and its ⋯ menu.
void openProfile(BuildContext context, String botId) =>
    context.push('/profile/$botId');
