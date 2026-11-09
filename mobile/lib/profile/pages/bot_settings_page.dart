import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../api/providers.dart';
import '../../theme/tokens.dart';
import '../../widgets/grouped_card.dart';
import '../../widgets/profile_kit.dart';
import '../approval_card.dart';
import '../bot_actions.dart';
import '../bot_detail.dart';
import '../folds/connectors_fold.dart';
import '../folds/decisions_fold.dart';
import '../folds/folders_fold.dart';
import '../folds/journal_fold.dart';
import '../folds/memory_fold.dart';
import '../folds/questions_fold.dart';
import '../folds/skills_fold.dart';
import '../folds/usage_fold.dart';
import '../instructions_screen.dart';
import '../model_picker.dart';
import '../../voice/voice_section.dart';

String _firstLine(String text) => text
    .split('\n')
    .map((l) => l.trim())
    .firstWhere((l) => l.isNotEmpty && !l.startsWith('#'), orElse: () => '');

/// A bot's Settings: everything that used to be on Info, in grouped cards,
/// with Retire this bot at the very end.
class BotSettingsPage extends ConsumerWidget {
  const BotSettingsPage({super.key, required this.botId});

  final String botId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final detail = ref.watch(botDetailProvider(botId));
    return Scaffold(
      appBar: AppBar(backgroundColor: Tokens.bg, title: const Text('Settings')),
      body: detail.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Quiet(describe(e), bad: true)),
        data: (bot) => ListView(children: [
          ..._top(context, bot),
          ..._folds(bot),
          _ComputerKind(bot: bot),
          _FullLimit(bot: bot),
          if (!bot.isPrimary)
            GroupedCard(children: [
              NavRow(
                key: const Key('retire-bot'),
                icon: Icons.delete_outline,
                label: 'Retire this bot',
                danger: true,
                onTap: () => retireBot(context, ref, bot.id, bot.name),
              ),
            ]),
          const SizedBox(height: Tokens.space8),
        ]),
      ),
    );
  }

  List<Widget> _top(BuildContext context, BotDetail bot) {
    final first = _firstLine(bot.instructions);
    return [
      GroupedCard(children: [
        InfoRow(
          label: 'Instructions',
          value: first.isEmpty ? 'Add instructions' : first,
          onTap: () => Navigator.of(context).push(MaterialPageRoute<void>(
              builder: (_) => InstructionsScreen(botId: bot.id))),
        ),
      ]),
      GroupedCard(label: 'Model & effort', children: [ModelRows(bot: bot)]),
      VoiceSection(bot: bot),
      GroupedCard(
          label: 'Approval mode',
          children: [CardBody(child: ApprovalCard(bot: bot))]),
    ];
  }

  List<Widget> _folds(BotDetail bot) => [
        Fold(title: 'What I remember', child: MemoryFold(botId: bot.id)),
        Fold(title: 'Skills', child: SkillsFold(botId: bot.id)),
        Fold(title: 'Decisions', child: DecisionsFold(botId: bot.id)),
        Fold(title: 'Question book', child: QuestionsFold(botId: bot.id)),
        Fold(title: 'Journal', child: JournalFold(botId: bot.id)),
        Fold(title: 'Usage', child: UsageFold(botId: bot.id)),
        Fold(title: 'Your Mac: folders', child: FoldersFold(botId: bot.id)),
        Fold(title: 'Connectors', child: ConnectorsFold(botId: bot.id)),
      ];
}

/// The "Linux computer | Mac Brave" switch (`PATCH /api/bots/{id}`).
class _ComputerKind extends ConsumerWidget {
  const _ComputerKind({required this.bot});

  final BotDetail bot;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return GroupedCard(label: 'Computer', children: [
      CardBody(
        child: SegmentedButton<String>(
          showSelectedIcon: false,
          segments: const [
            ButtonSegment(value: 'linux', label: Text('Linux computer')),
            ButtonSegment(value: 'mac_brave', label: Text('Mac Brave')),
          ],
          selected: {bot.computer == 'linux' ? 'linux' : 'mac_brave'},
          onSelectionChanged: (s) => attempt(context, () async {
            final saved = await ref.read(apiClientProvider).patch(
                '/api/bots/${Uri.encodeComponent(bot.id)}',
                {'computer': s.first});
            ref.read(botDetailProvider(bot.id).notifier).replace(saved);
          }),
        ),
      ),
    ]);
  }
}

/// Use the full limit until it resets (`PUT /api/bots/{id}/full-limit`).
/// The server refuses it while Roost can't read the usage limit.
class _FullLimit extends ConsumerWidget {
  const _FullLimit({required this.bot});

  final BotDetail bot;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return GroupedCard(children: [
      SwitchRow(
        label: 'Use the full limit until it resets',
        caption: 'Keeps a 10% reserve.',
        value: bot.fullLimitUntil != null,
        onChanged: (on) => attempt(context, () async {
          final saved = await ref.read(apiClientProvider).put(
              '/api/bots/${Uri.encodeComponent(bot.id)}/full-limit',
              {'on': on});
          ref.read(botDetailProvider(bot.id).notifier).replace(saved);
        }),
      ),
    ]);
  }
}
