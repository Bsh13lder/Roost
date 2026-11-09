import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../api/api_error.dart';
import '../../api/models.dart';
import '../../api/providers.dart';
import '../../features/home/home_data.dart';
import '../../live/live_connection.dart';
import '../../theme/tokens.dart';
import '../../widgets/lensbot.dart';
import 'card_base.dart';

/// The main bot's proposed teammate (`suggest_bot`, roost/talk/team_tools.py).
/// Nothing is created until Create this bot, which calls the normal
/// `POST /api/bots`; then, or when a bot of that name exists, it folds to one
/// line with Open.
class SuggestionCard extends ConsumerStatefulWidget {
  const SuggestionCard({super.key, required this.body, required this.tainted});
  final String body;
  final bool tainted;

  @override
  ConsumerState<SuggestionCard> createState() => _SuggestionCardState();
}

class _SuggestionCardState extends ConsumerState<SuggestionCard> {
  String? _createdId;
  bool _busy = false;
  String? _error;

  Future<void> _create(String name, String job, Avatar avatar) async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final bot = await ref.read(apiClientProvider).post('/api/bots', {
        'name': name,
        'job': job,
        'instructions': '',
        'avatar': avatar.toJson(),
      });
      final id = bot is Map ? bot['id'] : null;
      if (mounted) setState(() => _createdId = id is String ? id : '');
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
    if (d == null || d['name'] is! String || d['job'] is! String) {
      return const QuietLine('A suggested bot this app can’t read.');
    }
    final name = str(d['name']);
    final job = str(d['job']);
    final avatar = Avatar.fromJson(d['avatar']);
    final existing = ref.watch(liveProvider).bots.values
        .where((b) => b.name.toLowerCase() == name.toLowerCase());
    final openId = _createdId ?? (existing.isEmpty ? null : existing.first.id);
    if (openId != null) {
      return QuietLine('Created $name',
          trailing: openId.isEmpty
              ? null
              : TextButton(
                  onPressed: () => context.push('/chat/$openId'),
                  child: const Text('Open')));
    }
    return CardFrame(
      title: 'Suggested bot: $name',
      badges: [if (widget.tainted) 'This run read outside content.'],
      footer: [
        CardButton('Create this bot',
            primary: true,
            onPressed: _busy ? null : () => _create(name, job, avatar)),
      ],
      children: [
        Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          LensbotAvatar(avatar: avatar, size: 32),
          const SizedBox(width: Tokens.space3),
          Expanded(
              child: Text(job,
                  style: const TextStyle(color: Tokens.textSecondary))),
        ]),
        const Padding(
          padding: EdgeInsets.only(top: Tokens.space2),
          child: Text('Nothing is created until you tap.',
              style: TextStyle(
                  color: Tokens.textFaint, fontSize: Tokens.fsCaption)),
        ),
        if (_error != null) CardError(_error!),
      ],
    );
  }
}
