import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../api/models.dart';
import '../api/providers.dart';
import '../live/live_connection.dart';
import '../theme/accent.dart';
import '../theme/tokens.dart';
import 'turn_actions.dart';

typedef Json = Map<String, dynamic>;

/// One thing waiting on you: it opens the bot's chat, or [to] when the card
/// shows elsewhere (a routine's card is in its run log). [kind] and [id]
/// say which card it is, so a long press can skip it ([cardKind] is an Ask
/// card's own kind: ask or plan).
class TurnRow {
  const TurnRow(this.key, this.botId, this.text,
      {this.urgent = false, String? to, this.kind = '', this.id = '', this.cardKind = ''})
      : to = to ?? '/chat/$botId';

  final String key, botId, text, to, kind, id, cardKind;
  final bool urgent;
}

class TurnData {
  const TurnData({this.rows = const [], this.problem});

  final List<TurnRow> rows;
  final String? problem;
}

List<Json> _list(Object? v) =>
    [for (final x in (v as List? ?? const [])) (x as Map).cast<String, dynamic>()];

/// Reads `GET /api/my-turn`: its `rows` in the server's order (the web's
/// words), keeping only bots still on the team. Stuck rows are urgent.
List<TurnRow> parseMyTurn(Object? data, Map<String, String> botNames) {
  if (data is! Map) return const [];
  return [
    for (final r in _list(data['rows']))
      if (botNames.containsKey(r['bot_id']))
        TurnRow('${r['kind']}-${r['id']}', r['bot_id'] as String,
            '${r['text'] ?? ''}',
            urgent: r['kind'] == 'stuck',
            kind: '${r['kind']}',
            id: '${r['id']}'),
  ];
}

/// Ask cards (`/api/approvals`) are not in My turn on the server, so the
/// app adds the open ones in front, as before.
List<TurnRow> approvalRows(List<Json> approvals, Map<String, String> botNames) => [
      for (final a in approvals)
        if (botNames[a['bot_id']] != null && a['state'] == 'open')
          TurnRow('approval-${a['id']}', a['bot_id'] as String,
              '${botNames[a['bot_id']]} · Asking you · ${_firstStep(a)}',
              urgent: true,
              to: _cardPlace(a),
              kind: 'approval',
              id: a['id'] as String,
              cardKind: '${a['kind'] ?? 'ask'}'),
    ];

/// A routine run's card shows in that routine's run log (owner, 2026-11-05:
/// the bot's chat had no card to tap).
String? _cardPlace(Json card) {
  final routine = card['routine_id'];
  return routine is String ? '/bots/${card['bot_id']}/routines/$routine/log' : null;
}

String _firstStep(Json card) {
  final steps = card['steps'] as List? ?? const [];
  if (steps.isEmpty) return 'Needs your OK';
  return (steps.first as Map)['title'] as String? ?? 'Needs your OK';
}

/// The frames that reload My turn: a card opened or closed, and a fresh
/// snapshot after the socket reconnects, so a card answered while the phone
/// slept never stays behind.
const _reloadOn = {'message', 'stuck_card', 'approval_card', 'bot_removed', 'snapshot'};

/// Loaded once and again when one of [_reloadOn] arrives. The two
/// sources load on their own: one that fails never hides the other.
final myTurnProvider = FutureProvider<TurnData>((ref) async {
  final sub = ref.read(frameBusProvider).stream
      .where((f) => _reloadOn.contains(f['type']))
      .listen((_) => ref.invalidateSelf());
  ref.onDispose(sub.cancel);
  final api = ref.watch(apiClientProvider);
  var failed = false;
  Future<Object?> get(String path) async {
    try {
      return await api.get(path);
    } catch (_) {
      failed = true;
      return null;
    }
  }

  final results =
      await Future.wait([get('/api/approvals'), get('/api/my-turn')]);
  final names = {
    for (final b in ref.read(liveProvider).bots.values) b.id: b.name,
  };
  return TurnData(
    rows: [
      ...approvalRows(_list(results[0]), names),
      ...parseMyTurn(results[1], names),
    ],
    problem: failed ? "Some of what's waiting on you didn't load." : null,
  );
});

/// The My turn block on Home: only shown while something waits on you.
class MyTurn extends ConsumerWidget {
  const MyTurn({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    // Rebuild when bots change so names resolve.
    ref.watch(liveProvider.select((s) => s.bots.length));
    final data = ref.watch(myTurnProvider).valueOrNull;
    if (data == null || (data.rows.isEmpty && data.problem == null)) {
      return const SizedBox.shrink();
    }
    return Container(
      key: const Key('my-turn'),
      margin: const EdgeInsets.fromLTRB(
          Tokens.space3, Tokens.space2, Tokens.space3, Tokens.space2),
      decoration: BoxDecoration(
        color: Tokens.panel,
        borderRadius: BorderRadius.circular(Tokens.radiusMd),
        border: Border.all(color: Tokens.border),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Padding(
          padding: EdgeInsets.fromLTRB(
              Tokens.space4, Tokens.space3, Tokens.space4, Tokens.space1),
          child: Text('My turn',
              style: TextStyle(fontWeight: FontWeight.w600)),
        ),
        if (data.problem != null)
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: Tokens.space4),
            child: Row(children: [
              Expanded(
                  child: Text(data.problem!,
                      style: const TextStyle(color: Tokens.dangerText))),
              TextButton(
                  onPressed: () => ref.invalidate(myTurnProvider),
                  child: const Text('Retry')),
            ]),
          ),
        for (final r in data.rows)
          ListTile(
            key: Key('turn-${r.key}'),
            dense: true,
            leading: Text(r.urgent ? '!' : '?',
                style: TextStyle(
                    color: r.urgent ? Tokens.dangerText : AccentColors.of(context).strong,
                    fontWeight: FontWeight.w700)),
            title: Text(r.text, maxLines: 2, overflow: TextOverflow.ellipsis),
            onTap: () => context.push(r.to),
            onLongPress: () => showTurnActions(context, ref, r),
          ),
      ]),
    );
  }
}

/// Names for tests and for Home.
Map<String, String> namesOf(Iterable<Bot> bots) =>
    {for (final b in bots) b.id: b.name};
