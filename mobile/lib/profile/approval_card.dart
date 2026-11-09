import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../chat/chat_mode.dart';
import '../theme/tokens.dart';
import '../widgets/profile_kit.dart';
import 'bot_detail.dart';

const approvalModes = <(String, String, String)>[
  ('ask', 'Ask every time', 'Every change waits for your OK on a card.'),
  ('auto_edit', 'Auto-edit',
      'Ordinary changes go straight through, each with Undo. Risky ones still ask.'),
  ('plan', 'Review first', 'It shows you a proposal first. Accept runs it all.'),
];

const askTopicChoices = <(String, String)>[
  ('files', 'Files'), ('tasks', 'Tasks'), ('money', 'Money'),
  ('notes', 'Notes'), ('documents', 'Documents'), ('projects', 'Projects'),
  ('memory', 'Memory'), ('team', 'Team'), ('routines', 'Routines'),
];

/// Approval mode, "Always ask about" switches and (Linux computers) Browsing
/// actions. Every press saves at once.
class ApprovalCard extends ConsumerWidget {
  const ApprovalCard({super.key, required this.bot});

  final BotDetail bot;

  Future<void> _save(BuildContext context, WidgetRef ref, String mode,
      List<String> topics) {
    return attempt(
        context, () => saveApproval(ref, bot.id, mode: mode, topics: topics));
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final topics = bot.askTopics;
    final described =
        approvalModes.firstWhere((m) => m.$1 == bot.approvalMode, orElse: () => approvalModes[0]);
    List<String> toggled(String t, bool on) =>
        on ? [...topics, t] : [for (final x in topics) if (x != t) x];
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      SegmentedButton<String>(
        showSelectedIcon: false,
        segments: [
          for (final (id, label, _) in approvalModes)
            ButtonSegment(value: id, label: Text(label, textAlign: TextAlign.center)),
        ],
        selected: {bot.approvalMode},
        onSelectionChanged: (s) => _save(context, ref, s.first, topics),
      ),
      Quiet(described.$3),
      if (bot.computer == 'linux') BrowsingRow(bot: bot),
      const Text('Always ask about'),
      for (final (id, label) in askTopicChoices)
        SwitchListTile(
          dense: true,
          contentPadding: EdgeInsets.zero,
          title: Text(label),
          value: topics.contains(id),
          onChanged: (on) => _save(context, ref, bot.approvalMode, toggled(id, on)),
        ),
      SwitchListTile(
        dense: true,
        contentPadding: EdgeInsets.zero,
        title: const Text('Posting and sending'),
        subtitle: const Text('always asks'),
        value: true,
        onChanged: null,
      ),
    ]);
  }
}

/// Browsing actions: Ask me · Just browse · Full auto, the chosen one
/// explained (the same three as the chat's mode pill).
class BrowsingRow extends ConsumerWidget {
  const BrowsingRow({super.key, required this.bot});

  final BotDetail bot;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final current = chatModeOf(bot);
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const Text('Browsing actions'),
      const SizedBox(height: Tokens.space2),
      SegmentedButton<ChatMode>(
        showSelectedIcon: false,
        segments: [
          for (final m in ChatMode.values)
            ButtonSegment(
                value: m,
                label: Text(chatModeLabel(m), textAlign: TextAlign.center)),
        ],
        selected: {current},
        onSelectionChanged: (s) =>
            attempt(context, () => saveChatMode(ref, bot, s.first)),
      ),
      Quiet(chatModeExplanation(current)),
    ]);
  }
}
