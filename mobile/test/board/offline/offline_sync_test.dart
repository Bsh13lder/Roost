import 'dart:convert';

import 'package:dio/dio.dart' show RequestOptions;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/api/providers.dart';
import 'package:roost_mobile/api/session_store.dart';
import 'package:roost_mobile/board/tasks/offline/offline_queue.dart';
import 'package:roost_mobile/board/tasks/offline/offline_store.dart';
import 'package:roost_mobile/board/tasks/offline/offline_sync.dart';
import 'package:roost_mobile/board/tasks/task_models.dart';

import '../../fake_adapter.dart';

final _typed = DateTime.utc(2026, 11, 8, 14, 3, 5);

Map<String, Object?> _task(String id, String title) =>
    {'id': id, 'title': title, 'status': 'todo', 'priority': 'medium'};

/// Answers the sync's routes; [offline] picks the reply to each add by its
/// text, [complete] the status of each complete by task id.
FakeHandler syncAnswer({
  Map<String, int> offline = const {},
  Map<String, int> complete = const {},
  List<Map<String, Object?>> open = const [],
}) =>
    (RequestOptions o) {
      final path = o.uri.path;
      if (o.method == 'POST' && path == '/api/tasks/offline') {
        final body = (o.data as Map).cast<String, dynamic>();
        final text = body['text'] as String;
        final status = offline[text] ?? 201;
        if (status >= 400) return FakeAdapter.json({'detail': 'bad'}, status: status);
        return FakeAdapter.json(
            {..._task('real-${body['client_id']}', text), 'created': true},
            status: status);
      }
      final done = RegExp(r'^/api/tasks/([^/]+)/complete$').firstMatch(path);
      if (o.method == 'POST' && done != null) {
        final status = complete[done.group(1)] ?? 200;
        return FakeAdapter.json(status >= 400 ? {'detail': 'x'} : {},
            status: status);
      }
      if (o.method == 'GET' && path == '/api/tasks') return FakeAdapter.json(open);
      return FakeAdapter.json({});
    };

({ProviderContainer c, MemorySessionStore store}) _container(
    FakeAdapter adapter,
    {MemorySessionStore? store}) {
  final s = store ??
      (MemorySessionStore()
        ..url = 'http://127.0.0.1:18800'
        ..token = 'tok');
  var n = 0;
  final c = ProviderContainer(overrides: [
    sessionStoreProvider.overrideWithValue(s),
    httpAdapterProvider.overrideWithValue(adapter),
    offlineClockProvider.overrideWithValue(() => _typed),
    clientIdProvider.overrideWithValue(() => 'c${++n}'),
  ]);
  addTearDown(c.dispose);
  return (c: c, store: s);
}

Future<OfflineTasks> _state(ProviderContainer c) =>
    c.read(offlineTasksProvider.future);

OfflineTasksController _tasks(ProviderContainer c) =>
    c.read(offlineTasksProvider.notifier);

List<String> _posts(FakeAdapter a) => [
      for (final r in a.requests)
        if (r.method == 'POST') r.uri.path,
    ];

void main() {
  test('the typed time keeps its offset', () {
    expect(isoWithOffset(DateTime.utc(2026, 11, 8, 14, 3, 5)),
        '2026-11-08T14:03:05+00:00');
    final local = DateTime(2026, 7, 1, 9, 30);
    final iso = isoWithOffset(local);
    expect(DateTime.parse(iso).toUtc(), local.toUtc());
    expect(iso, matches(RegExp(r'[+-]\d\d:\d\d$')));
  });

  test('client ids are uuid v4 and differ', () {
    final a = newClientId();
    expect(a, matches(RegExp(
        r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$')));
    expect(newClientId(), isNot(a));
  });

  test('a queued add syncs with its typed time and client id', () async {
    final adapter = FakeAdapter(syncAnswer(open: [_task('real-c1', 'Milk')]));
    final (:c, :store) = _container(adapter);
    await _tasks(c).add('milk tomorrow');
    expect((await _state(c)).queue.single, isA<QueuedAdd>());

    await c.read(offlineSyncProvider.notifier).sync();

    final post = adapter.requests
        .firstWhere((r) => r.uri.path == '/api/tasks/offline');
    expect(post.data, {
      'client_id': 'c1',
      'text': 'milk tomorrow',
      'typed_at': '2026-11-08T14:03:05+00:00',
    });
    final after = await _state(c);
    expect(after.queue, isEmpty);
    expect(after.notes, isEmpty);
    // O8: the list is loaded again and kept.
    expect(after.kept.single.title, 'Milk');
    expect(jsonDecode(store.offlineTasks!)['queue'], isEmpty);
  });

  test('a network miss stops the round and keeps the queue', () async {
    final adapter = SwitchAdapter(syncAnswer(), down: true);
    final (:c, store: _) = _container(adapter);
    await _tasks(c).add('one');
    await _tasks(c).add('two');

    await c.read(offlineSyncProvider.notifier).sync();

    final after = await _state(c);
    expect([for (final q in after.queue) (q as QueuedAdd).text], ['one', 'two']);
    expect(after.notes, isEmpty);
    expect(_posts(adapter), ['/api/tasks/offline']);
  });

  test('a 4xx drops that one change, notes it and syncs the rest', () async {
    final adapter = FakeAdapter(syncAnswer(offline: {'bad line': 422}));
    final (:c, store: _) = _container(adapter);
    await _tasks(c).add('bad line');
    await _tasks(c).add('good line');

    await c.read(offlineSyncProvider.notifier).sync();

    final after = await _state(c);
    expect(after.queue, isEmpty);
    expect(after.notes, ["Couldn't sync: bad line"]);
    final texts = [
      for (final r in adapter.requests)
        if (r.uri.path == '/api/tasks/offline') (r.data as Map)['text'],
    ];
    expect(texts, ['bad line', 'good line']);
  });

  test('a 401 keeps the queue: nothing is lost to an expired session',
      () async {
    final adapter = FakeAdapter((_) => FakeAdapter.json({}, status: 401));
    final (:c, store: _) = _container(adapter);
    await _tasks(c).add('keep me');
    await c.read(offlineSyncProvider.notifier).sync();
    final after = await _state(c);
    expect(after.queue, hasLength(1));
    expect(after.notes, isEmpty);
  });

  test('a done on an offline add waits for it, then uses the real id',
      () async {
    final adapter = FakeAdapter(syncAnswer());
    final (:c, store: _) = _container(adapter);
    await _tasks(c).add('call mum');
    await _tasks(c).done('c1', title: 'call mum');

    await c.read(offlineSyncProvider.notifier).sync();

    expect(_posts(adapter),
        ['/api/tasks/offline', '/api/tasks/real-c1/complete']);
    expect((await _state(c)).queue, isEmpty);
  });

  test('a done on an add that could not sync is dropped with it', () async {
    final adapter = FakeAdapter(syncAnswer(offline: {'bad': 422}));
    final (:c, store: _) = _container(adapter);
    await _tasks(c).add('bad');
    await _tasks(c).done('c1', title: 'bad');
    await c.read(offlineSyncProvider.notifier).sync();
    expect(_posts(adapter), ['/api/tasks/offline']);
    final after = await _state(c);
    expect(after.queue, isEmpty);
    expect(after.notes, ["Couldn't sync: bad"]);
  });

  test('a 404 on complete counts as synced', () async {
    final adapter = FakeAdapter(syncAnswer(complete: {'t1': 404}));
    final (:c, store: _) = _container(adapter);
    await _tasks(c).done('t1', title: 'Old task');
    await c.read(offlineSyncProvider.notifier).sync();
    final after = await _state(c);
    expect(after.queue, isEmpty);
    expect(after.notes, isEmpty);
  });

  // Over Tailscale, `tailscale serve` answers 502 while the Mac's gateway is
  // down or restarting: a server error must never lose a change.
  for (final status in [500, 502, 503, 504]) {
    test('a $status keeps the queue for the next round', () async {
      final adapter = FakeAdapter((_) => FakeAdapter.json({}, status: status));
      final (:c, store: _) = _container(adapter);
      await _tasks(c).add('keep me');
      await _tasks(c).done('t1', title: 'Old task');
      await c.read(offlineSyncProvider.notifier).sync();
      final after = await _state(c);
      expect(after.queue, hasLength(2));
      expect(after.notes, isEmpty);
    });
  }

  test('the kept list and queue survive a restart', () async {
    final first = _container(FakeAdapter(syncAnswer()));
    await _tasks(first.c)
        .keep([TaskItem.fromJson(_task('t1', 'Pay rent'))]);
    await _tasks(first.c).add('later');

    final again = _container(FakeAdapter(syncAnswer()), store: first.store);
    final state = await _state(again.c);
    expect(state.kept.single.title, 'Pay rent');
    expect((state.queue.single as QueuedAdd).text, 'later');
  });

  test('a broken kept copy reads as empty, never a crash', () async {
    final store = MemorySessionStore()
      ..url = 'http://127.0.0.1:18800'
      ..token = 'tok'
      ..offlineTasks = '{not json';
    final (:c, store: _) = _container(FakeAdapter(syncAnswer()), store: store);
    final state = await _state(c);
    expect(state.kept, isEmpty);
    expect(state.queue, isEmpty);
  });

  test('sign out clears the kept list and the queue', () async {
    final (:c, :store) = _container(FakeAdapter(syncAnswer()));
    await _tasks(c).keep([TaskItem.fromJson(_task('t1', 'Pay rent'))]);
    await _tasks(c).add('later');
    expect(store.offlineTasks, isNotNull);

    await c.read(authProvider.notifier).signOut();
    await Future<void>.delayed(Duration.zero); // the controller reads again

    expect(store.offlineTasks, isNull);
    final state = await _state(c);
    expect(state.kept, isEmpty);
    expect(state.queue, isEmpty);
  });

  test('Dismiss clears the notes', () async {
    final adapter = FakeAdapter(syncAnswer(offline: {'bad': 422}));
    final (:c, store: _) = _container(adapter);
    await _tasks(c).add('bad');
    await c.read(offlineSyncProvider.notifier).sync();
    await _tasks(c).clearNotes();
    expect((await _state(c)).notes, isEmpty);
  });

  test('an empty queue sends nothing', () async {
    final adapter = FakeAdapter(syncAnswer());
    final (:c, store: _) = _container(adapter);
    await c.read(offlineSyncProvider.notifier).sync();
    expect(_posts(adapter), isEmpty);
  });
}
