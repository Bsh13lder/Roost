import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../api/models.dart';
import '../../live/bot_frames.dart';
import '../../live/live_connection.dart';
import '../../util/app_time.dart';

/// Steps kept per run (the newest); [ComputerRun.count] still counts them all.
const maxStepsPerRun = 60;

/// Runs kept per chat; the oldest go first.
const maxRunsPerThread = 20;

/// One thing a bot did on its computer (`computer_step` on `/api/events`).
class ComputerStep {
  const ComputerStep({
    required this.step,
    required this.kind,
    required this.line,
    required this.at,
    this.host,
  });

  final int step;

  /// look, wait, scroll, click, type, key, open_page, open_app or tab.
  final String kind;
  final String line;
  final String? host;
  final String at;

  /// A frame or snapshot entry, or null when it is not a usable step.
  static ComputerStep? tryParse(Map<String, dynamic> j) {
    final step = j['step'], line = j['line'], at = j['at'];
    if (step is! int || line is! String || line.isEmpty || at is! String) {
      return null;
    }
    final host = j['host'];
    return ComputerStep(
      step: step,
      kind: j['kind'] is String ? j['kind'] as String : 'look',
      line: line,
      at: at,
      host: host is String && host.isNotEmpty ? host : null,
    );
  }
}

/// One run's steps on the bot's computer, in one chat.
class ComputerRun {
  const ComputerRun({
    required this.runId,
    required this.botId,
    required this.threadId,
    required this.steps,
    required this.count,
    this.done = false,
  });

  final String runId;
  final String botId;
  final String threadId;

  /// In step order, the newest [maxStepsPerRun] at most.
  final List<ComputerStep> steps;

  /// Every step this run took, kept or not.
  final int count;
  final bool done;

  ComputerStep get current => steps.last;
  String get startedAt => steps.first.at;

  /// The site of the latest step that named one.
  String? get host {
    for (final s in steps.reversed) {
      if (s.host != null) return s.host;
    }
    return null;
  }

  ComputerRun finished() => done
      ? this
      : ComputerRun(
          runId: runId,
          botId: botId,
          threadId: threadId,
          steps: steps,
          count: count,
          done: true,
        );

  ComputerRun withStep(ComputerStep next) {
    final known = steps.any((s) => s.step == next.step);
    final merged = [
      for (final s in steps)
        if (s.step != next.step) s,
      next,
    ]..sort((a, b) => a.step.compareTo(b.step));
    final kept = merged.length > maxStepsPerRun
        ? merged.sublist(merged.length - maxStepsPerRun)
        : merged;
    return ComputerRun(
      runId: runId,
      botId: botId,
      threadId: threadId,
      steps: List.unmodifiable(kept),
      count: known ? count : count + 1,
      done: done,
    );
  }
}

/// Every chat's computer runs, by thread id.
typedef ComputerRuns = Map<String, List<ComputerRun>>;

/// Pure reducer: the runs after one `/api/events` frame.
ComputerRuns applyComputerFrame(ComputerRuns runs, Frame frame) {
  switch (frame['type']) {
    case 'computer_step':
      return _addStep(runs, frame);
    case 'bot_status':
      final bot = frame['bot_id'];
      if (bot is! String || frame['status'] == 'on_it') return runs;
      return _mapBot(runs, bot, (r) => r.finished());
    case 'bot_removed':
      final bot = frame['bot_id'];
      if (bot is! String) return runs;
      return _mapBot(runs, bot, (_) => null);
    case 'snapshot':
      return _fromSnapshot(frame);
    default:
      return runs;
  }
}

ComputerRuns _addStep(ComputerRuns runs, Frame frame) {
  final bot = frame['bot_id'],
      thread = frame['thread_id'],
      id = frame['run_id'];
  final step = ComputerStep.tryParse(frame);
  if (bot is! String || thread is! String || id is! String || step == null) {
    return runs;
  }
  final ended = _mapBot(runs, bot, (r) => r.runId == id ? r : r.finished());
  final list = ended[thread] ?? const <ComputerRun>[];
  final i = list.indexWhere((r) => r.runId == id);
  final base = i == -1
      ? ComputerRun(
          runId: id,
          botId: bot,
          threadId: thread,
          steps: const [],
          count: 0,
        )
      : list[i];
  final next = base.withStep(step);
  final updated = i == -1
      ? [...list, next]
      : [for (final r in list) r.runId == id ? next : r];
  final kept = updated.length > maxRunsPerThread
      ? updated.sublist(updated.length - maxRunsPerThread)
      : updated;
  return {...ended, thread: List.unmodifiable(kept)};
}

/// Each of [bot]'s runs through [change]; null drops the run.
ComputerRuns _mapBot(
  ComputerRuns runs,
  String bot,
  ComputerRun? Function(ComputerRun) change,
) {
  if (!runs.values.any((list) => list.any((r) => r.botId == bot))) return runs;
  return {
    for (final e in runs.entries)
      e.key: List.unmodifiable([
        for (final r in e.value)
          if (r.botId != bot) r else ?change(r),
      ]),
  };
}

/// The snapshot's runs, read leniently: each bot's kept runs (its newest
/// finished run per chat, `computer_kept`), always finished, then its running
/// steps (`computer_steps`, a map by bot id; an older per-bot list is read
/// too). A bot with neither has none.
ComputerRuns _fromSnapshot(Frame frame) {
  ComputerRuns runs = const {};
  final bots = frame['bots'];
  if (bots is! List) return runs;
  final kept = frame['computer_kept'];
  final running = frame['computer_steps'];
  for (final b in bots.whereType<Map>()) {
    final bot = b['id'];
    if (bot is! String) continue;
    final runsKept = kept is Map ? kept[bot] : null;
    for (final run in runsKept is List ? runsKept : const []) {
      runs = _addSteps(runs, bot, run);
    }
    runs = _mapBot(runs, bot, (r) => r.finished());
    runs = _addSteps(runs, bot, running is Map ? running[bot] : b['computer_steps']);
    if (b['status'] != 'on_it') {
      runs = _mapBot(runs, bot, (r) => r.finished());
    }
  }
  return runs;
}

/// [steps] (a list of step maps, else nothing) added for [bot].
ComputerRuns _addSteps(ComputerRuns runs, String bot, Object? steps) {
  if (steps is! List) return runs;
  for (final s in steps.whereType<Map>()) {
    runs = _addStep(runs, {...s.cast<String, dynamic>(), 'bot_id': bot});
  }
  return runs;
}

/// The chat's messages with its runs set in: each run right after your
/// message that started it (the last one of yours before its first step).
List<Object> withComputerRuns(List<Message> messages, List<ComputerRun> runs) {
  if (runs.isEmpty) return messages;
  final items = <Object>[...messages];
  for (final run in runs) {
    final start = _time(run.startedAt);
    var at = 0;
    for (var i = 0; i < items.length; i++) {
      final m = items[i];
      if (m is Message && m.fromUser && !_time(m.createdAt).isAfter(start)) {
        at = i + 1;
      }
    }
    items.insert(at, run);
  }
  return items;
}

DateTime _time(String iso) {
  try {
    return parseServerTime(iso);
  } on FormatException {
    return DateTime.fromMillisecondsSinceEpoch(0, isUtc: true);
  }
}

/// "upwork.com" for "www.upwork.com".
String shortHost(String host) =>
    host.startsWith('www.') ? host.substring(4) : host;

/// "Used its computer · upwork.com · 6 steps".
String doneLine(ComputerRun run) {
  final host = run.host;
  final steps = run.count == 1 ? '1 step' : '${run.count} steps';
  return [
    'Used its computer',
    if (host != null) shortHost(host),
    steps,
  ].join(' · ');
}

/// Follows every frame on the events socket and keeps each chat's runs.
class ComputerRunsController extends Notifier<ComputerRuns> {
  StreamSubscription<Frame>? _sub;

  @override
  ComputerRuns build() {
    _sub?.cancel();
    _sub = ref.watch(frameBusProvider).stream.listen((frame) {
      final next = applyComputerFrame(state, frame);
      if (!identical(next, state)) state = next;
    });
    ref.onDispose(() => _sub?.cancel());
    return const {};
  }
}

final computerRunsProvider =
    NotifierProvider<ComputerRunsController, ComputerRuns>(
      ComputerRunsController.new,
    );
