import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/api/providers.dart';
import 'package:roost_mobile/api/session_store.dart';
import 'package:roost_mobile/live/live_connection.dart';
import 'package:roost_mobile/profile/bot_detail.dart';

import '../fake_adapter.dart';

void main() {
  test('a bot_updated frame for this bot fetches its detail again; one for another bot does not', () async {
    var speed = 1.0;
    final adapter = FakeAdapter((o) {
      if (o.uri.path == '/api/bots/b1') {
        return FakeAdapter.json({
          'id': 'b1',
          'name': 'Gogi',
          'voice': {'speaker': 'aiden', 'tone': 'natural', 'speed': speed, 'read_aloud': false},
        });
      }
      return FakeAdapter.json({'detail': 'Not Found'}, status: 404);
    });
    final container = ProviderContainer(overrides: [
      sessionStoreProvider.overrideWithValue(MemorySessionStore()),
      httpAdapterProvider.overrideWithValue(adapter),
    ]);
    addTearDown(container.dispose);
    final sub = container.listen(botDetailProvider('b1'), (_, _) {});
    addTearDown(sub.close);
    final first = await container.read(botDetailProvider('b1').future);
    expect(first.voice.speed, 1.0);
    int gets() => adapter.requests.where((r) => r.uri.path == '/api/bots/b1').length;
    expect(gets(), 1);

    speed = 1.5;
    container.read(frameBusProvider).add({'type': 'bot_updated', 'bot': {'id': 'b1', 'name': 'Gogi'}});
    await pumpEventQueue();
    expect(gets(), 2);
    expect(container.read(botDetailProvider('b1')).valueOrNull?.voice.speed, 1.5);

    container.read(frameBusProvider).add({'type': 'bot_updated', 'bot': {'id': 'b2', 'name': 'Other'}});
    container.read(frameBusProvider).add({'type': 'bot_status', 'bot_id': 'b1', 'status': 'on_it'});
    await pumpEventQueue();
    expect(gets(), 2);
  });
}
