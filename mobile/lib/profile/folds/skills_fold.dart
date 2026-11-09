import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:go_router/go_router.dart';

import '../../api/providers.dart';
import '../../widgets/profile_kit.dart';

/// Skills: every saved how-to, with "On for this bot".
class SkillsFold extends ConsumerWidget {
  const SkillsFold({super.key, required this.botId});

  final String botId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return LoadView<List<Map<String, dynamic>>>(
      load: () async {
        final data = await ref
            .read(apiClientProvider)
            .get('/api/skills?bot_id=${Uri.encodeComponent(botId)}') as List;
        return [for (final s in data) (s as Map).cast<String, dynamic>()];
      },
      builder: (context, skills, reload) {
        final manage = TextButton(
          onPressed: () => context.push('/skills'),
          child: const Text('Manage skills'),
        );
        if (skills.isEmpty) {
          return Column(children: [const Quiet('No skills yet.'), manage]);
        }
        return Column(children: [
          manage,
          for (final s in skills)
            _SkillTile(botId: botId, skill: s),
        ]);
      },
    );
  }
}

class _SkillTile extends ConsumerStatefulWidget {
  const _SkillTile({required this.botId, required this.skill});

  final String botId;
  final Map<String, dynamic> skill;

  @override
  ConsumerState<_SkillTile> createState() => _SkillTileState();
}

class _SkillTileState extends ConsumerState<_SkillTile> {
  late bool _on = widget.skill['on'] == true;

  @override
  Widget build(BuildContext context) {
    final s = widget.skill;
    return SwitchListTile(
      contentPadding: EdgeInsets.zero,
      title: Text(s['name'] as String? ?? ''),
      subtitle: Text(s['use_when'] as String? ?? ''),
      secondary: null,
      value: _on,
      onChanged: (on) async {
        final ok = await attempt(
          context,
          () => ref.read(apiClientProvider).put(
              '/api/bots/${widget.botId}/skills/${Uri.encodeComponent(s['id'] as String)}',
              {'on': on}),
        );
        if (ok && mounted) setState(() => _on = on);
      },
    );
  }
}
