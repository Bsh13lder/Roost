import 'package:dio/dio.dart' show RequestOptions;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/api/models.dart';
import 'package:roost_mobile/api/providers.dart';
import 'package:roost_mobile/api/session_store.dart';
import 'package:roost_mobile/home/my_turn.dart';
import 'package:roost_mobile/live/live_connection.dart';

import '../fake_adapter.dart';

/// Gela, with no events socket.
class _Bots extends LiveController {
  @override
  LiveState build() => const LiveState(bots: {
        'g': Bot(id: 'g', name: 'Gela', avatar: Avatar(), status: BotStatus.resting),
      });
}

const _card = {
  'id': 'c1',
  'bot_id': 'g',
  'state': 'open',
  'steps': [
    {'title': 'Open www.wizzair.com'}
  ],
};

void main() {
  for (final type in ['approval_card', 'snapshot']) {
    test('a closed card leaves My turn after a $type frame', () async {
      var open = true;
      FakeReply answer(RequestOptions o) => switch (o.uri.path) {
            '/api/approvals' => FakeAdapter.json(open ? [_card] : []),
            '/api/my-turn' => FakeAdapter.json({'rows': []}),
            _ => FakeAdapter.json([]),
          };
      final container = ProviderContainer(overrides: [
        sessionStoreProvider.overrideWithValue(MemorySessionStore()
          ..url = 'http://127.0.0.1:18800'
          ..token = 'tok'),
        httpAdapterProvider.overrideWithValue(FakeAdapter(answer)),
        liveProvider.overrideWith(_Bots.new),
      ]);
      addTearDown(container.dispose);
      final sub = container.listen(myTurnProvider, (_, _) {});
      addTearDown(sub.close);
      expect((await container.read(myTurnProvider.future)).rows, hasLength(1));

      open = false; // answered somewhere else while the phone slept
      container.read(frameBusProvider).add({'type': type});
      await Future<void>.delayed(Duration.zero);
      expect((await container.read(myTurnProvider.future)).rows, isEmpty);
    });
  }

  test("a routine's card opens its run log, a chat's card the chat", () {
    final rows = approvalRows([
      {..._card, 'routine_id': 'r9'},
      {..._card, 'id': 'c2'},
    ], {'g': 'Gela'});
    expect(rows.map((r) => r.to), ['/bots/g/routines/r9/log', '/chat/g']);
  });
}
