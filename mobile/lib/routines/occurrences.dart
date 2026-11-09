import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../live/live_connection.dart';
import '../theme/tokens.dart';
import 'routines_repo.dart';

/// One routine's runs on one account-zone day (board toggles, 2026-10-26): the
/// server reckons every time (`GET /api/routines/occurrences`); the phone
/// only groups them, so a routine that runs every 15 minutes is one line.
@immutable
class RoutineDayEntry {
  const RoutineDayEntry({
    required this.routineId,
    required this.routineName,
    required this.botId,
    required this.botName,
    required this.times,
  });

  final String routineId;
  final String routineName;
  final String botId;
  final String botName;

  /// account-zone "HH:MM", earliest first.
  final List<String> times;

  String get firstTime => times.isEmpty ? '' : times.first;

  /// "09:00", or "09:00 +3" when it runs four times that day.
  String get timeWords =>
      times.length > 1 ? '${times.first} +${times.length - 1}' : firstTime;

  RoutineDayEntry withTime(String time) => RoutineDayEntry(
        routineId: routineId,
        routineName: routineName,
        botId: botId,
        botName: botName,
        times: List.unmodifiable([...times, time]),
      );
}

typedef RoutineDays = Map<String, List<RoutineDayEntry>>;

/// Each day's routines ("2026-10-23" -> entries) from the server's rows,
/// ordered by their first time. Rows missing a field are skipped.
RoutineDays groupRoutineDays(List<Map<String, dynamic>> rows) {
  final sorted = [
    for (final r in rows)
      if (r['day'] is String && r['time'] is String && r['routine_id'] is String) r,
  ]..sort((a, b) => '${a['at']}'.compareTo('${b['at']}'));
  final out = <String, List<RoutineDayEntry>>{};
  for (final r in sorted) {
    final day = r['day'] as String;
    final list = out[day] ?? const <RoutineDayEntry>[];
    final at = list.indexWhere((e) => e.routineId == r['routine_id']);
    out[day] = List.unmodifiable(at >= 0
        ? [for (final (i, e) in list.indexed) i == at ? e.withTime(r['time'] as String) : e]
        : [
            ...list,
            RoutineDayEntry(
              routineId: r['routine_id'] as String,
              routineName: r['routine_name'] as String? ?? '',
              botId: r['bot_id'] as String? ?? '',
              botName: r['bot_name'] as String? ?? '',
              times: List.unmodifiable([r['time'] as String]),
            ),
          ]);
  }
  return Map.unmodifiable(out);
}

/// The span a calendar asks routines for: account-zone days, and one bot or all.
typedef RoutineSpan = ({String from, String to, String? botId});

/// The span's routine runs, grouped by day; asked again when a routine
/// changes anywhere. A failed load is no routine lines, never an error.
final routineDaysProvider =
    FutureProvider.autoDispose.family<RoutineDays, RoutineSpan>((ref, span) async {
  final sub = ref
      .read(frameBusProvider)
      .stream
      .where((f) => f['type'] == 'routines_changed')
      .listen((_) => ref.invalidateSelf());
  ref.onDispose(sub.cancel);
  try {
    final rows = await ref
        .watch(routinesRepoProvider)
        .occurrences(span.from, span.to, botId: span.botId);
    return groupRoutineDays(rows);
  } catch (e) {
    debugPrint('Routine times could not be read: $e');
    return const {};
  }
});

/// A routine's runs that day as a quiet line: a repeat mark, the time, the
/// name and (unless it is the bot's own Plan) the bot. A tap opens its run log.
class RoutineLine extends StatelessWidget {
  const RoutineLine({super.key, required this.entry, this.showBot = true, this.clockWidth});

  final RoutineDayEntry entry;
  final bool showBot;

  /// Given: the time sits in a column this wide, as the agenda's tasks do.
  final double? clockWidth;

  @override
  Widget build(BuildContext context) {
    const faint = TextStyle(color: Tokens.textFaint, fontSize: Tokens.fsCaption);
    final time = Text(entry.timeWords, style: faint);
    return InkWell(
      key: Key('routine-${entry.routineId}'),
      onTap: () => context.push('/bots/${entry.botId}/routines/${entry.routineId}/log'),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: Tokens.space4, vertical: Tokens.space2),
        child: Row(children: [
          if (clockWidth != null) SizedBox(width: clockWidth, child: time),
          const Icon(Icons.repeat, size: Tokens.metaIcon, color: Tokens.textFaint),
          const SizedBox(width: Tokens.space2),
          if (clockWidth == null) ...[time, const SizedBox(width: Tokens.space2)],
          Expanded(
            child: Text(entry.routineName,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(color: Tokens.textSecondary)),
          ),
          if (showBot && entry.botName.isNotEmpty) Text(entry.botName, style: faint),
        ]),
      ),
    );
  }
}
