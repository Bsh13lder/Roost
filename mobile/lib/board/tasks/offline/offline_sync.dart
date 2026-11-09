import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../api/api_error.dart';
import '../../../api/providers.dart';
import '../../../api/reachability.dart';
import '../task_models.dart';
import '../task_repo.dart';
import 'offline_queue.dart';
import 'offline_store.dart';

/// The open list the offline screen keeps (the Tasks tab's `sort=due`).
const keptListQuery = {'sort': 'due'};

/// The first server-error status: the Mac's gateway is down or restarting
/// (`tailscale serve` answers 502 then), never a refusal of the change.
const _serverErrorFrom = 500;

/// Answers that mean "not now", never "no": the change stays queued. Null
/// is no answer at all (a network miss); 401 is a session to sign in again;
/// a 5xx is the gateway down or restarting.
bool _keepForLater(int? status) =>
    status == null ||
    status == 401 ||
    status == 403 ||
    status == 429 ||
    status >= _serverErrorFrom;

/// What one change's send came to.
enum _Sent { synced, refused, stop }

/// Sends the offline changes to the gateway (O7): oldest first, one at a
/// time. A network miss or a server error stops the round and keeps the
/// rest; any other refusal (a 4xx) drops that one change with a "Couldn't
/// sync" note. A 404 on a
/// tick means it is already done or gone, so it counts as synced.
class OfflineSync {
  const OfflineSync(this._repo, this._tasks);

  final TaskRepo _repo;
  final OfflineTasksController _tasks;

  /// How many changes left the queue (synced or dropped).
  Future<int> run() async {
    var handled = 0;
    while (true) {
      final queue = (await _tasks.current()).queue;
      if (queue.isEmpty) return handled;
      final head = queue.first;
      final (sent, taskId) = await _send(head);
      switch (sent) {
        case _Sent.stop:
          return handled;
        case _Sent.synced:
          await _tasks.apply((t) => t.synced(head, taskId: taskId));
        case _Sent.refused:
          await _tasks.apply((t) => t.refused(head));
      }
      handled++;
    }
  }

  Future<(_Sent, String?)> _send(QueuedChange change) async {
    try {
      return switch (change) {
        QueuedAdd() => (
            _Sent.synced,
            (await _repo.createOffline(change.toBody())).id,
          ),
        QueuedDone() => await _complete(change),
      };
    } on ApiException catch (e) {
      if (_keepForLater(e.status)) return (_Sent.stop, null);
      debugPrint('offline sync: refused (${e.status}) ${e.message}');
      return (_Sent.refused, null);
    }
  }

  Future<(_Sent, String?)> _complete(QueuedDone done) async {
    try {
      await _repo.complete(done.taskId);
    } on ApiException catch (e) {
      if (e.status != 404) rethrow;
    }
    return (_Sent.synced, null);
  }
}

/// True while a sync round runs. It starts when Roost answers again after
/// being offline, and on pull to refresh; after a round that sent anything
/// the lists load again from the server (O8).
class OfflineSyncer extends Notifier<bool> {
  bool _gone = false;

  @override
  bool build() {
    _gone = false;
    ref.onDispose(() => _gone = true);
    ref.listen<bool>(offlineProvider, (was, now) {
      if (was == true && !now) unawaited(sync());
    });
    // A phone closed while offline sends what waits once it is open again.
    ref.listen(authProvider, (was, now) {
      if (now.signedIn && was?.signedIn != true) Future.microtask(sync);
    }, fireImmediately: true);
    return false;
  }

  Future<void> sync() async {
    if (_gone || state || !ref.read(authProvider).signedIn) return;
    state = true;
    try {
      final tasks = ref.read(offlineTasksProvider.notifier);
      final handled = await OfflineSync(ref.read(taskRepoProvider), tasks).run();
      if (handled > 0) await _reload(tasks);
    } on Object catch (e) {
      debugPrint('offline sync: stopped ($e)');
    } finally {
      if (!_gone) state = false;
    }
  }

  /// O8: the server's list replaces the kept copy, and every task screen
  /// loads again.
  Future<void> _reload(OfflineTasksController tasks) async {
    ref.invalidate(taskListProvider);
    ref.invalidate(taskCountsProvider);
    try {
      final open = await ref.read(taskRepoProvider).query(keptListQuery);
      await tasks.keep(open);
    } on ApiException catch (e) {
      debugPrint('offline sync: reload missed (${e.message})');
    }
  }
}

final offlineSyncProvider =
    NotifierProvider<OfflineSyncer, bool>(OfflineSyncer.new);

/// The kept list as the offline screen shows it: ticks waiting to sync show
/// as done.
List<TaskItem> keptWithTicks(OfflineTasks t) {
  final ticked = t.tickedIds;
  return [
    for (final task in t.kept)
      ticked.contains(task.id) ? task.withStatus('done') : task,
  ];
}
