import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/models.dart';
import '../features/chat/message_view.dart';
import '../profile/format.dart';
import '../theme/tokens.dart';
import '../widgets/profile_kit.dart';
import 'routines_repo.dart';

typedef _Log = ({Json routine, List<Json> runs, List<Message> messages});

/// One routine's run log: its recent runs, then the log thread (read-only).
class RunLogScreen extends ConsumerWidget {
  const RunLogScreen({super.key, required this.botId, required this.routineId});

  final String botId, routineId;

  Future<_Log> _load(RoutinesRepo repo) async {
    final routines = await repo.forBot(botId);
    final routine = routines.firstWhere((r) => r['id'] == routineId,
        orElse: () => <String, dynamic>{});
    final runs = await repo.runs(routineId);
    final thread = routine['thread_id'] as String?;
    final messages = thread == null
        ? <Json>[]
        : await repo.logMessages(thread);
    return (
      routine: routine,
      runs: runs,
      messages: [for (final m in messages) Message.fromJson(m)],
    );
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final repo = ref.watch(routinesRepoProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Run log')),
      body: LoadView<_Log>(
        load: () => _load(repo),
        builder: (context, log, reload) => RefreshIndicator(
          onRefresh: reload,
          child: ListView(children: [
            Padding(
              padding: const EdgeInsets.all(Tokens.space4),
              child: Text('${log.routine['name'] ?? 'Routine'}',
                  style: const TextStyle(fontSize: Tokens.fsLead)),
            ),
            if (finishedLine(log.routine) case final done?) _Pad(Quiet(done)),
            if (lastErrorLine(log.routine) case final problem?)
              _Pad(Quiet(problem, bad: true)),
            if (log.runs.isEmpty) const _Pad(Quiet('No runs yet.')),
            for (final r in log.runs)
              ListTile(
                dense: true,
                title: Text(
                    '${runStateWords(r['state'] as String?)} · ${appShort('${r['slot_at'] ?? ''}')}'),
                subtitle: (r['note'] as String?) == null
                    ? null
                    : Text(r['note'] as String),
              ),
            const Divider(),
            for (final m in log.messages)
              MessageView(message: m, text: m.body),
          ]),
        ),
      ),
    );
  }
}

class _Pad extends StatelessWidget {
  const _Pad(this.child);
  final Widget child;
  @override
  Widget build(BuildContext context) => Padding(
      padding: const EdgeInsets.symmetric(horizontal: Tokens.space4),
      child: child);
}
