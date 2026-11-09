import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/api/providers.dart';
import 'package:roost_mobile/api/reachability.dart';
import 'package:roost_mobile/api/session_store.dart';
import 'package:roost_mobile/live/live_connection.dart';

import 'fake_adapter.dart';

/// Waits (real time) until [check] holds, or fails after [limit].
Future<void> until(bool Function() check,
    {Duration limit = const Duration(seconds: 3)}) async {
  final end = DateTime.now().add(limit);
  while (!check()) {
    if (DateTime.now().isAfter(end)) fail('timed out');
    await Future<void>.delayed(const Duration(milliseconds: 20));
  }
}

ProviderContainer liveContainer(SwitchAdapter adapter, void Function() onOpen) {
  final container = ProviderContainer(overrides: [
    sessionStoreProvider.overrideWithValue(MemorySessionStore()
      ..url = 'http://127.0.0.1:18800'
      ..token = 'tok'),
    httpAdapterProvider.overrideWithValue(adapter),
    socketOpenerProvider.overrideWithValue((uri, headers) {
      onOpen();
      throw StateError('refused');
    }),
  ]);
  container.listen(liveProvider, (_, _) {});
  return container;
}

void main() {
  test('the events socket opens once the saved session has loaded', () async {
    var opens = 0;
    final c = liveContainer(
        SwitchAdapter((_) => FakeAdapter.json({})), () => opens++);
    addTearDown(c.dispose);
    await until(() => opens >= 1);
  });

  test(
      'a socket that keeps failing asks if Roost is there, and reconnects '
      'at once when it answers', () async {
    var opens = 0;
    final adapter = SwitchAdapter(
        (_) => FakeAdapter.json({'id': '1', 'username': 'me'}),
        down: true);
    final c = liveContainer(adapter, () => opens++);
    addTearDown(c.dispose);

    await until(() => opens == 1);
    expect(adapter.requests, isEmpty, reason: 'one miss is not offline yet');
    await until(() => opens == 2); // after the 1 s backoff
    await until(() => c.read(offlineProvider));
    // The socket's ask, then the second look after the grace pause.
    expect(adapter.requests.map((r) => r.uri.path).toSet(), {reachabilityProbePath});

    // Roost answers again: the socket tries now, not after its 2 s backoff.
    adapter.down = false;
    await c.read(offlineProvider.notifier).probe();
    expect(c.read(offlineProvider), isFalse);
    expect(opens, 3);
  });
}
