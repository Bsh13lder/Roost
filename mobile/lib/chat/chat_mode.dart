import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../profile/bot_detail.dart';

/// How freely a bot clicks on its Linux computer: the chat's mode pill and
/// the profile's Browsing actions row show the same three.
enum ChatMode { askMe, justBrowse, fullAuto }

/// The approval topic that makes every browsing click ask.
const browsingTopic = 'browsing';

/// Each mode's label and its one-line explanation (the one place for them).
const chatModeWords = <ChatMode, (String, String)>{
  ChatMode.askMe: ('Ask me', 'Every click on its computer waits for your OK.'),
  ChatMode.justBrowse: (
    'Just browse',
    "Ordinary clicks just happen. Buttons it can't read still ask."
  ),
  ChatMode.fullAuto: (
    'Full auto',
    "A checker looks at buttons it can't read first. Paying, sending, "
        'deleting, typing and new sites still ask.'
  ),
};

String chatModeLabel(ChatMode m) => chatModeWords[m]!.$1;
String chatModeExplanation(ChatMode m) => chatModeWords[m]!.$2;

/// 'browsing' asked → Ask me; else auto_review → Full auto; else Just browse.
ChatMode chatModeOf(BotDetail bot) {
  if (bot.askTopics.contains(browsingTopic)) return ChatMode.askMe;
  return bot.autoReview ? ChatMode.fullAuto : ChatMode.justBrowse;
}

/// The body of `PUT /api/bots/{id}/approval` that a mode writes.
@immutable
class ApprovalWrite {
  const ApprovalWrite(this.mode, this.askTopics, this.autoReview);

  final String mode;
  final List<String> askTopics;
  final bool autoReview;

  Map<String, Object> toJson() =>
      {'mode': mode, 'ask_topics': askTopics, 'auto_review': autoReview};
}

/// The approval [mode] writes; the approval mode itself stays as it is.
ApprovalWrite approvalFor(BotDetail bot, ChatMode mode) {
  final others = [for (final t in bot.askTopics) if (t != browsingTopic) t];
  return switch (mode) {
    ChatMode.askMe => ApprovalWrite(bot.approvalMode, [...others, browsingTopic], false),
    ChatMode.justBrowse => ApprovalWrite(bot.approvalMode, others, false),
    ChatMode.fullAuto => ApprovalWrite(bot.approvalMode, others, true),
  };
}

/// One PUT; the bot the server returns replaces the local one.
Future<void> saveChatMode(WidgetRef ref, BotDetail bot, ChatMode mode) {
  final w = approvalFor(bot, mode);
  return saveApproval(ref, bot.id,
      mode: w.mode, topics: w.askTopics, autoReview: w.autoReview);
}
