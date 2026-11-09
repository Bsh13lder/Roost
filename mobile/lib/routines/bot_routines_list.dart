import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../profile/profile_values.dart';
import '../theme/tokens.dart';
import '../widgets/grouped_card.dart';
import '../widgets/profile_kit.dart';
import 'next_run.dart';
import 'routine_editor.dart';
import 'routines_repo.dart';
import 'watch_fields.dart';

/// One bot's routines under its Plan: a switch each, a tap edits it, Run now,
/// and + New routine.
class BotRoutinesList extends ConsumerWidget {
  const BotRoutinesList({super.key, required this.botId});

  final String botId;

  void _reload(WidgetRef ref) => ref.invalidate(botRoutinesProvider(botId));

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final routines = ref.watch(botRoutinesProvider(botId));
    return ListView(children: [
      Padding(
        padding: const EdgeInsets.fromLTRB(
            Tokens.space4, Tokens.space2, Tokens.space2, 0),
        child: Row(children: [
          const Expanded(
            child: Text('Routines',
                style: TextStyle(
                    fontSize: Tokens.fsLead, fontWeight: FontWeight.w600)),
          ),
          TextButton.icon(
            key: const Key('new-routine'),
            icon: const Icon(Icons.add, size: 18),
            label: const Text('New routine'),
            onPressed: () async {
              if (await showRoutineEditor(context, botId: botId)) _reload(ref);
            },
          ),
        ]),
      ),
      routines.when(
        loading: () => const Padding(
          padding: EdgeInsets.all(Tokens.space4),
          child: Center(child: CircularProgressIndicator()),
        ),
        error: (e, _) => Padding(
          padding: const EdgeInsets.symmetric(horizontal: Tokens.space4),
          child: Row(children: [
            Expanded(child: Quiet(describe(e), bad: true)),
            TextButton(
                onPressed: () => _reload(ref), child: const Text('Try again')),
          ]),
        ),
        data: (list) => list.isEmpty
            ? const Padding(
                padding: EdgeInsets.symmetric(horizontal: Tokens.space4),
                child: Quiet('No routines yet.'),
              )
            : GroupedCard(children: [
                for (final r in list)
                  _RoutineRow(
                      botId: botId, routine: r, onChanged: () => _reload(ref)),
              ]),
      ),
    ]);
  }
}

class _RoutineRow extends ConsumerWidget {
  const _RoutineRow(
      {required this.botId, required this.routine, required this.onChanged});

  final String botId;
  final Map<String, dynamic> routine;
  final VoidCallback onChanged;

  String get _id => routine['id'] as String? ?? '';

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final repo = ref.read(routinesRepoProvider);
    final now = DateTime.now();
    final watching = watchLine(routine, now);
    final words = watching.isNotEmpty ? watching : routine['words'] as String? ?? '';
    final next = routine['enabled'] == true
        ? nextRunWords(routine['next_run_at'] as String?, now)
        : '';
    final nextLabel = watching.isNotEmpty ? 'Next check' : 'Next run';
    final lines = [if (words.isNotEmpty) words, if (next.isNotEmpty) '$nextLabel: $next'];
    return ListTile(
      key: Key('routine-$_id'),
      title: Text(routine['name'] as String? ?? ''),
      subtitle: lines.isEmpty
          ? null
          : Text(lines.join('\n'), style: const TextStyle(color: Tokens.textSecondary)),
      onTap: () async {
        final saved =
            await showRoutineEditor(context, botId: botId, routine: routine);
        if (saved) onChanged();
      },
      trailing: Row(mainAxisSize: MainAxisSize.min, children: [
        IconButton(
          tooltip: 'Run now',
          icon: const Icon(Icons.play_arrow_rounded),
          onPressed: () async {
            final ok = await attempt(context, () => repo.runNow(_id));
            if (ok && context.mounted) {
              ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(content: Text('Started. Its Report comes to the chat.')));
            }
          },
        ),
        Switch(
          key: Key('routine-switch-$_id'),
          value: routine['enabled'] == true,
          onChanged: (on) async {
            final ok = await attempt(context, () => repo.setEnabled(_id, on));
            if (ok) onChanged();
          },
        ),
      ]),
    );
  }
}
