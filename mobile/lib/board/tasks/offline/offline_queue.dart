import 'dart:math';

import 'package:flutter/foundation.dart';

import '../task_models.dart';

// The offline tasks' shapes (docs/plans/2026-11-08-roost-offline-tasks.md):
// the kept open list, the changes made with no connection, and the lines
// that could not sync. All immutable; every change returns a new value.

/// How a change that the server refused is listed (O7).
const couldNotSyncPrefix = "Couldn't sync: ";

/// The most "Couldn't sync" lines kept; older ones fall off.
const offlineNotesMax = 20;

/// The title a tick shows in a note when it has none of its own.
const _untitledTick = 'a ticked task';

/// One change made while Roost could not be reached.
@immutable
sealed class QueuedChange {
  const QueuedChange();

  Map<String, dynamic> toJson();

  /// The words a "Couldn't sync" note shows for it.
  String get line;

  /// Null for a shape this phone does not know (kept data from elsewhere).
  static QueuedChange? fromJson(Map<String, dynamic> j) => switch (j['kind']) {
        'add' => QueuedAdd(
            clientId: '${j['client_id']}',
            text: '${j['text']}',
            typedAt: '${j['typed_at']}',
          ),
        'done' => QueuedDone(
            taskId: '${j['task_id']}', title: j['title'] as String?),
        _ => null,
      };
}

/// A quick line typed offline: sent as is, read by the server with
/// `now = typedAt` (O3, O4).
final class QueuedAdd extends QueuedChange {
  const QueuedAdd(
      {required this.clientId, required this.text, required this.typedAt});

  final String clientId;
  final String text;

  /// ISO 8601 with the phone's offset ("2026-11-08T14:03:05+01:00").
  final String typedAt;

  @override
  String get line => text;

  @override
  Map<String, dynamic> toJson() =>
      {'kind': 'add', 'client_id': clientId, 'text': text, 'typed_at': typedAt};

  /// The body for `POST /api/tasks/offline`.
  Map<String, dynamic> toBody() =>
      {'client_id': clientId, 'text': text, 'typed_at': typedAt};
}

/// A tick offline (O6). [taskId] is a real task id, or the client id of a
/// [QueuedAdd] still waiting, swapped for the real id once that add syncs.
final class QueuedDone extends QueuedChange {
  const QueuedDone({required this.taskId, this.title});

  final String taskId;
  final String? title;

  @override
  String get line => title ?? _untitledTick;

  @override
  Map<String, dynamic> toJson() =>
      {'kind': 'done', 'task_id': taskId, 'title': title};

  QueuedDone withTask(String id) => QueuedDone(taskId: id, title: title);
}

/// Everything the phone keeps for offline tasks (O2).
@immutable
class OfflineTasks {
  const OfflineTasks(
      {this.kept = const [], this.queue = const [], this.notes = const []});

  static const empty = OfflineTasks();

  /// The last open-task list the Tasks tab saw (`sort=due`).
  final List<TaskItem> kept;

  /// Oldest first.
  final List<QueuedChange> queue;

  /// "Couldn't sync: …" lines, newest last.
  final List<String> notes;

  factory OfflineTasks.fromJson(Map<String, dynamic> j) => OfflineTasks(
        kept: List.unmodifiable([
          for (final t in (j['kept'] as List? ?? const []))
            TaskItem.fromJson((t as Map).cast<String, dynamic>()),
        ]),
        queue: List.unmodifiable([
          for (final q in (j['queue'] as List? ?? const []))
            ?QueuedChange.fromJson((q as Map).cast<String, dynamic>()),
        ]),
        notes: List.unmodifiable(
            [for (final n in (j['notes'] as List? ?? const [])) '$n']),
      );

  Map<String, dynamic> toJson() => {
        'kept': [for (final t in kept) t.toJson()],
        'queue': [for (final q in queue) q.toJson()],
        'notes': notes,
      };

  OfflineTasks _with(
          {List<TaskItem>? kept,
          List<QueuedChange>? queue,
          List<String>? notes}) =>
      OfflineTasks(
        kept: kept ?? this.kept,
        queue: queue == null ? this.queue : List.unmodifiable(queue),
        notes: notes == null ? this.notes : List.unmodifiable(notes),
      );

  OfflineTasks withKept(List<TaskItem> list) =>
      _with(kept: List.unmodifiable(list));

  OfflineTasks withChange(QueuedChange change) =>
      _with(queue: [...queue, change]);

  OfflineTasks withoutNotes() => _with(notes: const []);

  /// [head] synced: it leaves the queue. An add's ticks now point at the
  /// task the server made ([taskId]).
  OfflineTasks synced(QueuedChange head, {String? taskId}) {
    final rest = [for (final q in queue) if (!identical(q, head)) q];
    if (head is! QueuedAdd || taskId == null) return _with(queue: rest);
    return _with(queue: [
      for (final q in rest)
        q is QueuedDone && q.taskId == head.clientId ? q.withTask(taskId) : q,
    ]);
  }

  /// The server refused [head]: it leaves the queue with a note, and so do
  /// the ticks on an add that will never exist.
  OfflineTasks refused(QueuedChange head) {
    bool tiedTo(QueuedChange q) =>
        head is QueuedAdd && q is QueuedDone && q.taskId == head.clientId;
    final kept = [
      for (final q in queue)
        if (!identical(q, head) && !tiedTo(q)) q,
    ];
    final added = [...notes, '$couldNotSyncPrefix${head.line}'];
    final from = max(0, added.length - offlineNotesMax);
    return _with(queue: kept, notes: added.sublist(from));
  }

  /// The ids (real or client) ticked offline and not yet synced.
  Set<String> get tickedIds =>
      {for (final q in queue) if (q is QueuedDone) q.taskId};

  List<QueuedAdd> get waitingAdds =>
      [for (final q in queue) if (q is QueuedAdd) q];
}

/// [t] as ISO 8601 with its own offset, so the server reads the moment as
/// the phone meant it ("tomorrow" is the day after you typed it).
String isoWithOffset(DateTime t) {
  String two(int n) => n.toString().padLeft(2, '0');
  final offset = t.timeZoneOffset;
  final sign = offset.isNegative ? '-' : '+';
  final mins = offset.inMinutes.abs();
  final wall = '${t.year.toString().padLeft(4, '0')}-${two(t.month)}-'
      '${two(t.day)}T${two(t.hour)}:${two(t.minute)}:${two(t.second)}';
  return '$wall$sign${two(mins ~/ 60)}:${two(mins % 60)}';
}

/// A random version 4 UUID, from the platform's secure random source.
String newClientId() {
  final r = Random.secure();
  final b = [for (var i = 0; i < 16; i++) r.nextInt(256)];
  b[6] = (b[6] & 0x0f) | 0x40;
  b[8] = (b[8] & 0x3f) | 0x80;
  final hex = [for (final x in b) x.toRadixString(16).padLeft(2, '0')].join();
  return '${hex.substring(0, 8)}-${hex.substring(8, 12)}-'
      '${hex.substring(12, 16)}-${hex.substring(16, 20)}-${hex.substring(20)}';
}
