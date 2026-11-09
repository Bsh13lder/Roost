import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../theme/tokens.dart';
import '../bot_detail.dart';
import '../profile_values.dart';

/// The bot's computer: its status, a large way into the live screen, Teach,
/// and Take control at the bottom. Mac Brave has its own window on the Mac.
class ComputerPage extends ConsumerWidget {
  const ComputerPage({super.key, required this.botId});

  final String botId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final bot = ref.watch(botDetailProvider(botId)).valueOrNull;
    final desk = ref.watch(deskProvider(botId)).valueOrNull;
    final word =
        bot == null ? '' : computerStatusWord(bot.status, desk);
    return Scaffold(
      appBar: AppBar(backgroundColor: Tokens.bg, title: const Text('Computer')),
      body: bot == null
          ? const Center(child: CircularProgressIndicator())
          : bot.computer == 'linux'
              ? _Linux(botId: botId, name: bot.name, word: word)
              : _MacBrave(name: bot.name),
    );
  }
}

class _Linux extends StatelessWidget {
  const _Linux({required this.botId, required this.name, required this.word});

  final String botId, name, word;

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.all(Tokens.space4),
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          if (word.isNotEmpty)
            Text(word,
                key: const Key('computer-word'),
                style: const TextStyle(color: Tokens.textSecondary)),
          const SizedBox(height: Tokens.space3),
          Expanded(child: _ScreenTile(botId: botId, name: name)),
          const SizedBox(height: Tokens.space4),
          OutlinedButton(
            key: const Key('teach'),
            onPressed: () => context.push('/computer/$botId?go=teach'),
            child: const Text('Teach'),
          ),
          const SizedBox(height: Tokens.space2),
          FilledButton(
            key: const Key('take-control'),
            onPressed: () => context.push('/computer/$botId?go=control'),
            child: const Text('Take control'),
          ),
        ]),
      ),
    );
  }
}

class _ScreenTile extends StatelessWidget {
  const _ScreenTile({required this.botId, required this.name});

  final String botId, name;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Tokens.panel,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(Tokens.radiusLg),
        side: const BorderSide(color: Tokens.border),
      ),
      child: InkWell(
        key: const Key('open-live'),
        customBorder: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(Tokens.radiusLg)),
        onTap: () => context.push('/computer/$botId'),
        child: Center(
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            const Icon(Icons.desktop_windows_outlined,
                size: 48, color: Tokens.textSecondary),
            const SizedBox(height: Tokens.space3),
            Text("Watch $name's computer live",
                style: const TextStyle(fontSize: Tokens.fsLead)),
          ]),
        ),
      ),
    );
  }
}

class _MacBrave extends StatelessWidget {
  const _MacBrave({required this.name});

  final String name;

  @override
  Widget build(BuildContext context) => Center(
        child: Padding(
          padding: const EdgeInsets.all(Tokens.space6),
          child: Text(
              '$name uses Mac Brave, which has its own window on your Mac. Switch to a Linux computer in Settings to watch and take control from here.',
              textAlign: TextAlign.center,
              style: const TextStyle(color: Tokens.textSecondary)),
        ),
      );
}
