import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../api/api_error.dart';
import '../../api/models.dart';
import '../../api/providers.dart';
import '../../features/home/home_data.dart';
import '../../theme/tokens.dart';
import '../../widgets/lensbot.dart';
import '../../widgets/profile_kit.dart';
import 'card_base.dart';

/// The created card's mark when the chat had read web content (owner, 2026-10-29).
const createdCheckedText =
    'Auto-checked: this chat had read web content, so Fable checked this bot matches what you asked.';

/// "Created NAME" (S1.3, Ruling 29): what the main bot just made, in full,
/// with Open and Undo (which retires the new bot after the confirm).
class CreatedBotCard extends ConsumerStatefulWidget {
  const CreatedBotCard({super.key, required this.body});
  final String body;

  @override
  ConsumerState<CreatedBotCard> createState() => _CreatedBotCardState();
}

class _CreatedBotCardState extends ConsumerState<CreatedBotCard> {
  bool _undone = false;
  bool _busy = false;
  String? _error;

  Future<void> _undo(String id, String name) async {
    final ok = await confirm(context, 'Retire $name?', 'Retire this bot',
        body: 'This deletes the bot that was just created, with its chats.');
    if (!ok || !mounted) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await ref.read(apiClientProvider).delete('/api/bots/${Uri.encodeComponent(id)}');
      if (mounted) setState(() => _undone = true);
      ref.invalidate(botsLoadProvider);
      ref.invalidate(chatsProvider);
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final d = decodeBody(widget.body);
    final ok = d != null && ['bot_id', 'name', 'job', 'instructions'].every((k) => d[k] is String);
    if (!ok) return const QuietLine('A new bot this app can’t read.');
    final id = str(d['bot_id']);
    final name = str(d['name']);
    if (_undone) return QuietLine('Undone: $name was retired.');
    final instructions = str(d['instructions']);
    return CardFrame(
      title: 'Created $name',
      calm: true,
      badges: [if (d['checked'] == true) createdCheckedText],
      footer: [
        CardButton('Open', onPressed: () => context.push('/chat/$id')),
        CardButton('Undo', onPressed: _busy ? null : () => _undo(id, name)),
      ],
      children: [
        Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          LensbotAvatar(avatar: Avatar.fromJson(d['avatar']), size: 32),
          const SizedBox(width: Tokens.space3),
          Expanded(child: Text(str(d['job']), style: const TextStyle(color: Tokens.textSecondary))),
        ]),
        Padding(
          padding: const EdgeInsets.only(top: Tokens.space2),
          child: Text(instructions.isEmpty ? 'No instructions.' : instructions,
              style: const TextStyle(color: Tokens.textFaint, fontSize: Tokens.fsCaption)),
        ),
        if (_error != null) CardError(_error!),
      ],
    );
  }
}
