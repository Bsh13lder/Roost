import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'bot_actions.dart';
import 'bot_detail.dart';

enum _Action { share, retire }

/// The profile's ⋯ menu: Share as Template, Retire this bot.
class BotMenu extends ConsumerWidget {
  const BotMenu({super.key, required this.bot});

  final BotDetail bot;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return PopupMenuButton<_Action>(
      tooltip: 'More',
      onSelected: (a) => switch (a) {
        _Action.share => shareTemplate(context, ref, bot.id, bot.name),
        _Action.retire => retireBot(context, ref, bot.id, bot.name),
      },
      itemBuilder: (_) => [
        const PopupMenuItem(
            value: _Action.share, child: Text('Share as Template')),
        if (!bot.isPrimary)
          const PopupMenuItem(
              value: _Action.retire, child: Text('Retire this bot')),
      ],
    );
  }
}
