import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/board/tasks/task_repo.dart';
import 'package:roost_mobile/features/home/chat_search.dart';
import 'package:roost_mobile/home/my_turn.dart';

import 'fake_adapter.dart';
import 'package:roost_mobile/api/api_client.dart';

void main() {
  test('My turn rows come from GET /api/my-turn, off-team bots left out', () {
    final rows = parseMyTurn({
      'count': 2,
      'rows': [
        {'kind': 'stuck', 'id': 's1', 'bot_id': 'b1', 'text': 'Scout · Stuck'},
        {'kind': 'question', 'id': 'q1', 'bot_id': 'b1', 'text': 'Scout · Which?'},
        {'kind': 'question', 'id': 'q2', 'bot_id': 'gone', 'text': 'x'},
      ],
    }, {'b1': 'Scout'});
    expect(rows.map((r) => r.key), ['stuck-s1', 'question-q1']);
    expect(rows.first.urgent, isTrue);
    expect(rows.last.urgent, isFalse);
    expect(rows.first.text, 'Scout · Stuck');
    expect(parseMyTurn(null, {}), isEmpty);
  });

  test('chat search hits are read from results', () {
    final hits = parseChatHits({
      'results': [
        {
          'chat_kind': 'bot', 'chat_id': 'b1', 'name': 'Scout',
          'message_id': 'm1', 'snippet': 'pay <b>rent</b>',
          'created_at': '2026-10-22T10:00:00Z', 'from_you': true,
        }
      ]
    });
    expect(hits.single.chatId, 'b1');
    expect(hits.single.snippet, 'pay <b>rent</b>');
    expect(hits.single.isBot, isTrue);
  });

  test('task Undo posts /restore instead of re-adding', () async {
    final calls = <String>[];
    final api = ApiClient(
      connection: () => const Connection(baseUrl: 'http://127.0.0.1:18800'),
      onUnauthorized: () {},
      adapter: FakeAdapter((o) {
        calls.add('${o.method} ${o.path}');
        return FakeAdapter.json({});
      }),
    );
    await TaskRepo(api).restore('t1');
    expect(calls, ['POST /api/tasks/t1/restore']);
  });
}
