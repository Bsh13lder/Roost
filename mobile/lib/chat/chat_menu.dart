import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api_error.dart';
import '../api/models.dart';
import '../api/providers.dart';
import '../home/earlier_conversations.dart';
import '../profile/bot_actions.dart';
import '../profile/profile_screen.dart' show openProfile;
import '../theme/tokens.dart';

enum _Pick { profile, find, earlier, fresh, share, retire }

/// The chat's ⋯ menu: View profile, Find in chat, Earlier conversations,
/// Fresh start, Share as Template and (not for the main bot) Retire this bot.
class ChatMenu extends ConsumerWidget {
  const ChatMenu({
    super.key,
    required this.botId,
    required this.bot,
    required this.threadId,
    required this.messages,
  });

  final String botId;
  final Bot? bot;
  final String? threadId;
  final List<Message> messages;

  void _pick(BuildContext context, WidgetRef ref, _Pick pick) {
    final name = bot?.name ?? 'this bot';
    switch (pick) {
      case _Pick.profile:
        openProfile(context, botId);
      case _Pick.find:
        showFindInChat(context, messages);
      case _Pick.earlier:
        Navigator.of(context).push(MaterialPageRoute<void>(
            builder: (_) =>
                EarlierConversations(botId: botId, mainThreadId: threadId)));
      case _Pick.fresh:
        _freshStart(context, ref);
      case _Pick.share:
        shareTemplate(context, ref, botId, name);
      case _Pick.retire:
        retireBot(context, ref, botId, name);
    }
  }

  /// Fresh start: hides earlier web content from the bot's next runs; the line arrives by the live socket.
  Future<void> _freshStart(BuildContext context, WidgetRef ref) async {
    final id = threadId;
    if (id == null) return;
    try {
      await ref
          .read(apiClientProvider)
          .post('/api/threads/${Uri.encodeComponent(id)}/fresh-start', {});
    } on ApiException catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.maybeOf(context)
            ?.showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return PopupMenuButton<_Pick>(
      key: const Key('chat-menu'),
      tooltip: 'More',
      icon: const Icon(Icons.more_horiz),
      onSelected: (p) => _pick(context, ref, p),
      itemBuilder: (_) => [
        _item(_Pick.profile, Icons.account_circle_outlined, 'View profile'),
        _item(_Pick.find, Icons.search, 'Find in chat'),
        _item(_Pick.earlier, Icons.history, 'Earlier conversations'),
        if (threadId != null)
          _item(_Pick.fresh, Icons.restart_alt, 'Fresh start'),
        _item(_Pick.share, Icons.ios_share, 'Share as Template'),
        if (bot != null && !bot!.isPrimary)
          _item(_Pick.retire, Icons.delete_outline, 'Retire this bot',
              danger: true),
      ],
    );
  }

  PopupMenuItem<_Pick> _item(_Pick value, IconData icon, String label,
      {bool danger = false}) {
    final color = danger ? Tokens.dangerText : Tokens.text;
    return PopupMenuItem(
      value: value,
      child: Row(children: [
        Icon(icon, size: 20, color: color),
        const SizedBox(width: Tokens.space3),
        Flexible(
          child: Text(label,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(color: color)),
        ),
      ]),
    );
  }
}
