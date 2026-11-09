import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../live/bot_frames.dart';
import '../../live/live_connection.dart';
import '../../util/app_time.dart';

/// Steps kept per run (the newest); [ActivityRun.count] still counts them all.
const maxRunStepsPerRun = 80;

/// Runs kept per chat; the oldest go first.
const maxActivityRunsPerThread = 30;

/// A note: the bot's own words between steps (owner, 2026-11-04), shown in
/// the pill and the steps sheet, never as a chat bubble and never a step.
const noteKind = 'note';

/// The kinds a step can be (`run_step.kind`); anything else reads as other.
const runStepKinds = {
  'think', 'search', 'read', 'computer', 'program', 'file', 'tasks', 'notes', //
  'money', 'calendar', 'bots', 'memory', 'message', 'other', noteKind,
};

/// One thing a bot did in a run, in plain words (`run_step` on `/api/events`).
class RunStep {
  const RunStep({
    required this.step,
    required this.kind,
    required this.line,
    required this.at,
    this.state = 'start',
    this.host,
    this.tainted = false,
  });

  final int step;
  final String kind;

  /// A note only: the run had read outside content when the bot wrote it.
  final bool tainted;

  bool get isNote => kind == noteKind;

  /// Plain words, never code: "Browsing web.whatsapp.com".
  final String line;
  final String at;

  /// start, done or failed.
  final String state;
  final String? host;

  bool get failed => state == 'failed';

  static RunStep? tryParse(Map<String, dynamic> j) {
    final step = j['step'], line = j['line'], at = j['at'];
    if (step is! int || line is! String || line.trim().isEmpty || at is! String) {
      return null;
    }
    final kind = j['kind'], state = j['state'], host = j['host'];
    return RunStep(
      step: step,
      kind: kind is String && runStepKinds.contains(kind) ? kind : 'other',
      line: line.trim(),
      at: at,
      state: state == 'done' || state == 'failed' ? state as String : 'start',
      host: host is String && host.isNotEmpty ? host : null,
      tainted: j['tainted'] == true,
    );
  }
}

/// One run of a bot in one chat: its steps, and whether it has ended.
class ActivityRun {
  const ActivityRun({
    required this.runId,
    required this.botId,
    required this.threadId,
    required this.steps,
    required this.count,
    this.done = false,
    this.endedAt,
  });

  const ActivityRun.empty({
    required this.runId,
    required this.botId,
    required this.threadId,
  })  : steps = const [],
        count = 0,
        done = false,
        endedAt = null;

  final String runId;
  final String botId;
  final String threadId;

  /// In step order, the newest [maxRunStepsPerRun] at most.
  final List<RunStep> steps;
  final int count;
  final bool done;
  final String? endedAt;

  RunStep get current => steps.last;
  String get startedAt => steps.first.at;
  bool get onlyThinking => steps.every((s) => s.kind == 'think' || s.isNote);

  /// The newest step that is not a note.
  RunStep? get _work {
    for (final s in steps.reversed) {
      if (!s.isNote) return s;
    }
    return null;
  }

  /// What the live pill says: the reply being written, else the bot's newest
  /// note (its own words, like Grok's thinking line), else the newest step.
  String get pillLine {
    final work = _work;
    if (work != null && work.kind == 'message' && work.state == 'start') return work.line;
    for (final s in steps.reversed) {
      if (s.isNote) return s.line;
    }
    return work?.line ?? 'Thinking';
  }

  /// What the robot acts out: the newest real step (a note is thinking).
  String get pillKind => _work?.kind ?? 'think';

  /// Whether the pill shimmers: a step is still running.
  bool get pillWorking => _work == null || _work!.state == 'start';

  String? get host {
    for (final s in steps.reversed) {
      if (s.host != null) return s.host;
    }
    return null;
  }

  /// From the first step to the end (or the last step while it runs).
  Duration get took {
    if (steps.isEmpty) return Duration.zero;
    final end = _time(endedAt ?? steps.last.at);
    final d = end.difference(_time(startedAt));
    return d.isNegative ? Duration.zero : d;
  }

  ActivityRun finished([String? at]) => done
      ? this
      : ActivityRun(
          runId: runId,
          botId: botId,
          threadId: threadId,
          steps: steps,
          count: count,
          done: true,
          endedAt: at ?? (steps.isEmpty ? null : steps.last.at),
        );

  ActivityRun withStep(RunStep next) {
    final known = steps.any((s) => s.step == next.step);
    final merged = [
      for (final s in steps)
        if (s.step != next.step) s,
      next,
    ]..sort((a, b) => a.step.compareTo(b.step));
    final kept = merged.length > maxRunStepsPerRun
        ? merged.sublist(merged.length - maxRunStepsPerRun)
        : merged;
    return ActivityRun(
      runId: runId,
      botId: botId,
      threadId: threadId,
      steps: List.unmodifiable(kept),
      count: known ? count : count + 1,
      done: done,
      endedAt: endedAt,
    );
  }
}

/// "42 s", "2 min 5 s", "3 min".
String durationWords(Duration d) {
  final s = d.inSeconds < 1 ? 1 : d.inSeconds;
  if (s < 60) return '$s s';
  final min = s ~/ 60, rest = s % 60;
  return rest == 0 ? '$min min' : '$min min $rest s';
}

/// "Worked for 42 s · 6 steps", or "Thought for 4 s" when it only thought.
String doneWords(ActivityRun run, {int extra = 0}) {
  final took = durationWords(run.took);
  if (run.onlyThinking && extra == 0) return 'Thought for $took';
  final n = run.steps.where((s) => s.kind != 'think' && !s.isNote).length + extra;
  return 'Worked for $took · ${n == 1 ? '1 step' : '$n steps'}';
}

/// Every chat's runs, by thread id.
typedef ActivityRuns = Map<String, List<ActivityRun>>;

/// Pure reducer: the runs after one `/api/events` frame.
ActivityRuns applyRunFrame(ActivityRuns runs, Frame frame) {
  switch (frame['type']) {
    case 'run_step':
      return _addStep(runs, frame);
    case 'bot_status':
      final bot = frame['bot_id'];
      if (bot is! String || frame['status'] == 'on_it') return runs;
      final at = frame['at'];
      return _mapBot(runs, bot, (r) => r.finished(at is String ? at : null));
    case 'bot_removed':
      final bot = frame['bot_id'];
      return bot is String ? _mapBot(runs, bot, (_) => null) : runs;
    case 'snapshot':
      return _fromSnapshot(frame);
    default:
      return runs;
  }
}

ActivityRuns _addStep(ActivityRuns runs, Frame frame) {
  final bot = frame['bot_id'], thread = frame['thread_id'], id = frame['run_id'];
  final step = RunStep.tryParse(frame);
  if (bot is! String || thread is! String || id is! String || step == null) {
    return runs;
  }
  final ended = _mapBot(runs, bot, (r) => r.runId == id ? r : r.finished());
  final list = ended[thread] ?? const <ActivityRun>[];
  final i = list.indexWhere((r) => r.runId == id);
  final base = i == -1
      ? ActivityRun.empty(runId: id, botId: bot, threadId: thread)
      : list[i];
  final next = base.withStep(step);
  final updated =
      i == -1 ? [...list, next] : [for (final r in list) r.runId == id ? next : r];
  final kept = updated.length > maxActivityRunsPerThread
      ? updated.sublist(updated.length - maxActivityRunsPerThread)
      : updated;
  return {...ended, thread: List.unmodifiable(kept)};
}

ActivityRuns _mapBot(
    ActivityRuns runs, String bot, ActivityRun? Function(ActivityRun) change) {
  if (!runs.values.any((list) => list.any((r) => r.botId == bot))) return runs;
  return {
    for (final e in runs.entries)
      e.key: List.unmodifiable([
        for (final r in e.value)
          if (r.botId != bot) r else ?change(r),
      ]),
  };
}

/// The snapshot's running steps (`run_steps`, a map by bot id; an older
/// per-bot list is read too), read leniently.
ActivityRuns _fromSnapshot(Frame frame) {
  ActivityRuns runs = const {};
  final bots = frame['bots'];
  if (bots is! List) return runs;
  final byBot = frame['run_steps'];
  for (final b in bots.whereType<Map>()) {
    final steps = byBot is Map ? byBot[b['id']] : b['run_steps'];
    if (steps is! List) continue;
    for (final s in steps.whereType<Map>()) {
      runs = _addStep(runs, {'bot_id': b['id'], ...s.cast<String, dynamic>()});
    }
    if (b['status'] != 'on_it' && b['id'] is String) {
      runs = _mapBot(runs, b['id'] as String, (r) => r.finished());
    }
  }
  return runs;
}

DateTime _time(String iso) {
  try {
    return parseServerTime(iso);
  } on FormatException {
    return DateTime.fromMillisecondsSinceEpoch(0, isUtc: true);
  }
}

/// Follows every frame on the events socket and keeps each chat's runs.
class ActivityRunsController extends Notifier<ActivityRuns> {
  StreamSubscription<Frame>? _sub;

  @override
  ActivityRuns build() {
    _sub?.cancel();
    _sub = ref.watch(frameBusProvider).stream.listen((frame) {
      final next = applyRunFrame(state, frame);
      if (!identical(next, state)) state = next;
    });
    ref.onDispose(() => _sub?.cancel());
    return const {};
  }
}

final activityRunsProvider =
    NotifierProvider<ActivityRunsController, ActivityRuns>(
        ActivityRunsController.new);
