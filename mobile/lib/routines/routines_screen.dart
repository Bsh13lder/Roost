import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../api/models.dart';
import '../live/live_connection.dart';
import '../profile/format.dart';
import '../theme/tokens.dart';
import '../widgets/profile_kit.dart';
import 'next_run.dart';
import 'watch_fields.dart';
import 'routine_editor.dart';
import 'routines_repo.dart';

typedef _Hub = ({List<Json> routines, List<Json> runs, List<Json> templates});

/// Every bot's routines in one place (the web's /routines).
class RoutinesScreen extends ConsumerStatefulWidget {
  const RoutinesScreen({super.key});

  @override
  ConsumerState<RoutinesScreen> createState() => _RoutinesScreenState();
}

class _RoutinesScreenState extends ConsumerState<RoutinesScreen> {
  late Future<_Hub> _future = _load();

  Future<_Hub> _load() async {
    final repo = ref.read(routinesRepoProvider);
    final routines = await repo.all();
    final runs = await repo.recentRuns();
    final templates = await repo.templates();
    return (routines: routines, runs: runs, templates: templates);
  }

  void _reload() => setState(() => _future = _load());

  Future<Bot?> _pickBot(String title) {
    final bots = ref.read(liveProvider).bots.values.toList();
    return showModalBottomSheet<Bot>(
      context: context,
      builder: (c) => SafeArea(
        child: ListView(shrinkWrap: true, children: [
          Padding(
              padding: const EdgeInsets.all(Tokens.space4),
              child: Text(title,
                  style: const TextStyle(fontSize: Tokens.fsLead))),
          for (final b in bots)
            ListTile(title: Text(b.name), onTap: () => Navigator.pop(c, b)),
        ]),
      ),
    );
  }

  Future<void> _new() async {
    final bot = await _pickBot('Which bot runs it?');
    if (bot == null || !mounted) return;
    if (await showRoutineEditor(context, botId: bot.id)) _reload();
  }

  Future<void> _addTemplate(Json t) async {
    final bot = await _pickBot('Add to which bot?');
    if (bot == null || !mounted) return;
    final ok = await attempt(
        context,
        () => ref
            .read(routinesRepoProvider)
            .addTemplate(bot.id, t['id'] as String));
    if (ok) _reload();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Routines'),
        actions: [
          IconButton(
              key: const Key('new-routine'),
              tooltip: 'New routine',
              icon: const Icon(Icons.add),
              onPressed: _new),
        ],
      ),
      body: FutureBuilder<_Hub>(
        future: _future,
        builder: (context, snap) {
          if (snap.hasError) {
            return Center(
                child: TextButton(
                    onPressed: _reload,
                    child: Text('${describe(snap.error!)} Try again')));
          }
          final hub = snap.data;
          if (hub == null) {
            return const Center(child: CircularProgressIndicator());
          }
          return ListView(children: [
            _heading('Routines'),
            if (hub.routines.isEmpty) const _Pad(Quiet('No routines yet.')),
            for (final r in hub.routines)
              _RoutineTile(routine: r, onChanged: _reload),
            _heading('Recent runs'),
            if (hub.runs.isEmpty) const _Pad(Quiet('No runs yet.')),
            for (final r in hub.runs) _RunTile(run: r),
            _heading('Templates'),
            for (final t in hub.templates)
              ListTile(
                title: Text(t['name'] as String? ?? ''),
                subtitle: Text(t['words'] as String? ?? ''),
                trailing: TextButton(
                    onPressed: () => _addTemplate(t),
                    child: const Text('Add to…')),
              ),
          ]);
        },
      ),
    );
  }

  Widget _heading(String text) => Padding(
        padding: const EdgeInsets.fromLTRB(
            Tokens.space4, Tokens.space4, Tokens.space4, Tokens.space1),
        child: Text(text.toUpperCase(),
            style: const TextStyle(
                color: Tokens.textFaint,
                fontSize: Tokens.fsCaption,
                letterSpacing: 0.8)),
      );
}

class _Pad extends StatelessWidget {
  const _Pad(this.child);
  final Widget child;
  @override
  Widget build(BuildContext context) => Padding(
      padding: const EdgeInsets.symmetric(horizontal: Tokens.space4),
      child: child);
}

class _RoutineTile extends ConsumerStatefulWidget {
  const _RoutineTile({required this.routine, required this.onChanged});

  final Json routine;
  final VoidCallback onChanged;

  @override
  ConsumerState<_RoutineTile> createState() => _RoutineTileState();
}

class _RoutineTileState extends ConsumerState<_RoutineTile> {
  late bool _on = widget.routine['enabled'] == true;

  @override
  Widget build(BuildContext context) {
    final r = widget.routine;
    final id = r['id'] as String;
    final botId = r['bot_id'] as String;
    final next = r['enabled'] == true
        ? nextRunWords(r['next_run_madrid'] as String?, DateTime.now())
        : '';
    final last = runStateWords(r['last_state'] as String?);
    final watching = watchLine(r, DateTime.now());
    return ListTile(
      title: Text('${r['name'] ?? ''}'),
      subtitle: Text([
        '${r['bot_name'] ?? ''} · ${watching.isNotEmpty ? watching : r['words'] ?? ''}',
        if (next.isNotEmpty) '${watching.isNotEmpty ? 'Next check' : 'Next run'}: $next',
        if (last.isNotEmpty) 'Last: $last${_note(r)}',
      ].join('\n')),
      isThreeLine: true,
      onTap: () async {
        if (await showRoutineEditor(context, botId: botId, routine: r)) {
          widget.onChanged();
        }
      },
      trailing: Row(mainAxisSize: MainAxisSize.min, children: [
        IconButton(
          tooltip: 'Run now',
          icon: const Icon(Icons.play_arrow_rounded),
          onPressed: () async {
            final ok = await attempt(
                context, () => ref.read(routinesRepoProvider).runNow(id));
            if (ok) widget.onChanged();
          },
        ),
        Switch(
          value: _on,
          onChanged: (on) async {
            final ok = await attempt(context,
                () => ref.read(routinesRepoProvider).setEnabled(id, on));
            if (ok && mounted) setState(() => _on = on);
          },
        ),
      ]),
      onLongPress: () => context.push('/bots/$botId/routines/$id/log'),
    );
  }

  String _note(Json r) {
    final n = r['last_note'] as String?;
    return n == null || n.isEmpty ? '' : ' · $n';
  }
}

class _RunTile extends StatelessWidget {
  const _RunTile({required this.run});
  final Json run;

  @override
  Widget build(BuildContext context) {
    final when = appShort(
        (run['finished_at'] ?? run['started_at'] ?? run['slot_at'] ?? '') as String);
    return ListTile(
      dense: true,
      title: Text('${run['routine_name'] ?? ''} · ${run['bot_name'] ?? ''}'),
      subtitle: Text('${runStateWords(run['state'] as String?)} · $when'),
      onTap: () => context.push(
          '/bots/${run['bot_id']}/routines/${run['routine_id']}/log'),
    );
  }
}
