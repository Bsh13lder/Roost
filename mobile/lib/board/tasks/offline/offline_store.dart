import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../api/providers.dart';
import '../../../api/session_store.dart';
import '../task_models.dart';
import 'offline_queue.dart';

/// The clock an offline line is stamped with; fixed in tests.
final offlineClockProvider =
    Provider<DateTime Function()>((_) => DateTime.now);

/// Makes a client id for an offline line; fixed in tests.
final clientIdProvider = Provider<String Function()>((_) => newClientId);

/// Reads and writes [OfflineTasks] as one JSON text in the secure store.
class OfflineStore {
  const OfflineStore(this._store);

  final SessionStore _store;

  /// A kept copy that cannot be read is treated as empty: losing a cache
  /// beats a phone that cannot open its tasks.
  Future<OfflineTasks> load() async {
    final text = await _store.readOfflineTasks();
    if (text == null || text.isEmpty) return OfflineTasks.empty;
    try {
      return OfflineTasks.fromJson(
          (jsonDecode(text) as Map).cast<String, dynamic>());
    } on Object catch (e) {
      debugPrint('offline tasks: the kept copy was unreadable ($e)');
      return OfflineTasks.empty;
    }
  }

  Future<void> save(OfflineTasks tasks) =>
      _store.writeOfflineTasks(jsonEncode(tasks.toJson()));

  Future<void> clear() => _store.writeOfflineTasks(null);
}

/// The one owner of the offline tasks. Every change is applied in order
/// (one write at a time) and saved at once.
class OfflineTasksController extends AsyncNotifier<OfflineTasks> {
  Future<void> _last = Future.value();

  OfflineStore get _store => OfflineStore(ref.read(sessionStoreProvider));

  @override
  Future<OfflineTasks> build() {
    // Signing out clears the store (AuthController.signOut); read it again,
    // in turn with any change still being saved.
    ref.listen(authProvider, (was, now) {
      if (now.ready && !now.signedIn && was?.signedIn != false) {
        _last = _last.then((_) async => state = AsyncData(await _store.load()));
      }
    });
    return _store.load();
  }

  /// Applies [change] to the newest value, saves it and returns it.
  Future<OfflineTasks> apply(OfflineTasks Function(OfflineTasks) change) {
    final done = Completer<OfflineTasks>();
    _last = _last.then((_) async {
      try {
        final next = change(await future);
        state = AsyncData(next);
        await _store.save(next);
        done.complete(next);
      } on Object catch (e, st) {
        debugPrint('offline tasks: could not save ($e)');
        done.completeError(e, st);
      }
    });
    return done.future;
  }

  /// The newest value, once it has loaded.
  Future<OfflineTasks> current() => future;

  /// O2: the open list the Tasks tab just loaded.
  Future<void> keep(List<TaskItem> open) => apply((t) => t.withKept(open));

  /// O3: a quick line, stamped now with a new client id.
  Future<void> add(String text) {
    final line = text.trim();
    if (line.isEmpty) return Future.value();
    final change = QueuedAdd(
      clientId: ref.read(clientIdProvider)(),
      text: line,
      typedAt: isoWithOffset(ref.read(offlineClockProvider)()),
    );
    return apply((t) => t.withChange(change));
  }

  /// O6: a tick on [taskId] (a real id or a waiting add's client id).
  Future<void> done(String taskId, {String? title}) => apply((t) =>
      t.tickedIds.contains(taskId)
          ? t
          : t.withChange(QueuedDone(taskId: taskId, title: title)));

  Future<void> clearNotes() => apply((t) => t.withoutNotes());
}

final offlineTasksProvider =
    AsyncNotifierProvider<OfflineTasksController, OfflineTasks>(
        OfflineTasksController.new);
