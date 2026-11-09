import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../profile/bot_detail.dart';
import '../theme/accent.dart';
import '../theme/tokens.dart';
import '../widgets/profile_kit.dart' show attempt;
import 'chat_mode.dart';

/// The small pill beside a bot's composer: the chat mode, one tap to change
/// it. Shown only for a bot on its Linux computer.
class ChatModePill extends ConsumerWidget {
  const ChatModePill(
      {super.key, required this.botId, this.padding = EdgeInsets.zero});

  final String botId;

  /// Space around the pill, kept only while the pill shows.
  final EdgeInsets padding;

  Future<void> _pick(BuildContext context, WidgetRef ref, BotDetail bot) async {
    final current = chatModeOf(bot);
    final picked = await showModalBottomSheet<ChatMode>(
      context: context,
      backgroundColor: Tokens.panel,
      builder: (_) => ChatModeSheet(current: current),
    );
    if (picked == null || picked == current || !context.mounted) return;
    await attempt(context, () => saveChatMode(ref, bot, picked));
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final bot = ref.watch(botDetailProvider(botId)).valueOrNull;
    if (bot == null || bot.computer != 'linux') return const SizedBox.shrink();
    return Padding(padding: padding, child: _pill(context, ref, bot));
  }

  Widget _pill(BuildContext context, WidgetRef ref, BotDetail bot) {
    return Material(
      key: const Key('chat-mode-pill'),
      color: Tokens.raised,
      shape: const StadiumBorder(side: BorderSide(color: Tokens.border)),
      child: InkWell(
        customBorder: const StadiumBorder(),
        onTap: () => _pick(context, ref, bot),
        child: Container(
          height: Tokens.chipHeight,
          padding: const EdgeInsets.symmetric(horizontal: Tokens.space3),
          alignment: Alignment.center,
          child: Text(chatModeLabel(chatModeOf(bot)),
              style: const TextStyle(
                  fontSize: Tokens.fsLabel, color: Tokens.textSecondary)),
        ),
      ),
    );
  }
}

/// The three modes with their explanations; the current one is checked.
class ChatModeSheet extends StatelessWidget {
  const ChatModeSheet({super.key, required this.current, this.title});

  final ChatMode current;

  /// A heading over the choices, e.g. "How Gigs uses its computer".
  final String? title;

  @override
  Widget build(BuildContext context) => SafeArea(
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          if (title != null)
            Padding(
              padding: const EdgeInsets.fromLTRB(
                  Tokens.space4, Tokens.space4, Tokens.space4, Tokens.space1),
              child: Align(
                alignment: Alignment.centerLeft,
                child: Text(title!,
                    style: const TextStyle(
                        fontSize: Tokens.fsLead, fontWeight: FontWeight.w600)),
              ),
            ),
          for (final m in ChatMode.values)
            ListTile(
              key: Key('chat-mode-${m.name}'),
              title: Text(chatModeLabel(m)),
              subtitle: Text(chatModeExplanation(m),
                  style: const TextStyle(color: Tokens.textSecondary)),
              trailing: m == current
                  ? Icon(Icons.check, color: AccentColors.of(context).strong)
                  : null,
              onTap: () => Navigator.of(context).pop(m),
            ),
        ]),
      );
}
