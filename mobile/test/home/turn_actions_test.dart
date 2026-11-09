import 'package:dio/dio.dart' show RequestOptions;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/api/providers.dart';
import 'package:roost_mobile/api/session_store.dart';
import 'package:roost_mobile/home/my_turn.dart';
import 'package:roost_mobile/home/turn_actions.dart';

import '../fake_adapter.dart';

TurnRow _row(String kind, {String cardKind = ''}) =>
    TurnRow('$kind-x1', 'g', 'Gela', kind: kind, id: 'x1', cardKind: cardKind);

void main() {
  test('Skip closes each kind of card through its own route', () {
    final paths = {
      for (final kind in ['approval', 'stuck', 'routine_proposal', 'skill_proposal', 'key_request', 'question'])
        kind: skipRequest(_row(kind, cardKind: 'ask'))?.path,
    };
    expect(paths, {
      'approval': '/api/approvals/x1/answer',
      'stuck': '/api/stuck/x1/give-up',
      'routine_proposal': '/api/routine-proposals/x1/decline',
      'skill_proposal': '/api/skill-proposals/x1/decline',
      'key_request': '/api/connector-requests/x1/decline',
      'question': '/api/questions/x1/dismiss',
    });
    expect(skipRequest(_row('approval', cardKind: 'ask'))?.body, {'answer': 'no'});
    expect(skipRequest(_row('approval', cardKind: 'plan'))?.body, {'answer': 'decline'});
    expect(skipRequest(_row('something_new')), isNull);
  });

  test('approval rows and My turn rows carry their kind and id', () {
    final rows = approvalRows([
      {'id': 'c1', 'bot_id': 'g', 'state': 'open', 'kind': 'plan', 'steps': []},
    ], {'g': 'Gela'});
    expect((rows.single.kind, rows.single.id, rows.single.cardKind), ('approval', 'c1', 'plan'));
    final mine = parseMyTurn({
      'rows': [
        {'kind': 'stuck', 'id': 's1', 'bot_id': 'g', 'text': 'Gela · Stuck'}
      ]
    }, {'g': 'Gela'});
    expect((mine.single.kind, mine.single.id), ('stuck', 's1'));
  });

  test('a new instruction skips the card, then goes to the bot as your message', () async {
    final adapter = FakeAdapter((RequestOptions o) => switch (o.uri.path) {
          '/api/bots/g/chat' => FakeAdapter.json({'id': 't1'}),
          '/api/threads/t1/messages' => FakeAdapter.json({'status': 'started', 'message_id': 'm1'}),
          _ => FakeAdapter.json({}),
        });
    final container = ProviderContainer(overrides: [
      sessionStoreProvider.overrideWithValue(MemorySessionStore()
        ..url = 'http://127.0.0.1:18800'
        ..token = 'tok'),
      httpAdapterProvider.overrideWithValue(adapter),
    ]);
    addTearDown(container.dispose);
    await giveNewInstruction(container.read(apiClientProvider), _row('stuck'), '  Check Ryanair instead ');
    expect(adapter.requests.map((r) => r.uri.path), [
      '/api/stuck/x1/give-up',
      '/api/bots/g/chat',
      '/api/threads/t1/messages',
    ]);
    expect(adapter.requests.last.data, {'text': 'Check Ryanair instead'});
  });
}
