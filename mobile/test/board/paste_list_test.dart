import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/api/api_client.dart';
import 'package:roost_mobile/board/tasks/paste_list.dart';
import 'package:roost_mobile/board/tasks/task_repo.dart';

import '../fake_adapter.dart';
import '../workspace/workspace_fakes.dart' show wtask;

Map<String, Object?> pasted({bool ready = true, String? problem}) => {
      'count': 2,
      'ready': ready,
      'problem': problem,
      'tasks': [
        {'title': 'Buy milk', 'ready': true, 'priority': 'high', 'steps': <String>[]},
        {'title': 'Pack', 'ready': true, 'steps': ['Socks', 'Shoes']},
      ],
    };

Map<String, Object?> task(String title) => {...wtask('n', title), 'due_date': null};

TaskRepo repoWith(FakeAdapter adapter) => TaskRepo(ApiClient(
      connection: () => const Connection(baseUrl: 'http://127.0.0.1:18800'),
      onUnauthorized: () {},
      adapter: adapter,
    ));

void main() {
  test('two or more non-empty lines are a list; one line is not', () {
    expect(isPastedList('Buy milk\nCall Ana'), isTrue);
    expect(isPastedList('Buy milk\r\n\r\n  Call Ana  '), isTrue);
    expect(isPastedList('Buy milk\n\n'), isFalse);
    expect(isPastedList('Buy milk'), isFalse);
    expect(isPastedList(''), isFalse);
  });

  test('the server\'s reading of a pasted list is read leniently', () {
    final list = PastedList.fromJson(pasted());
    expect(list.count, 2);
    expect(list.ready, isTrue);
    expect(list.tasks.map((t) => t.reading.title), ['Buy milk', 'Pack']);
    expect(list.tasks.last.steps, ['Socks', 'Shoes']);
    expect(list.tasks.last.createBody(), {
      'title': 'Pack',
      'steps': ['Socks', 'Shoes'],
    });
    expect(list.tasks.first.createBody(), {'title': 'Buy milk', 'priority': 'high'});
    final bad = PastedList.fromJson({'tasks': 'x', 'problem': 'Line 2: nope'});
    expect(bad.count, 0);
    expect(bad.ready, isFalse);
    expect(bad.problem, 'Line 2: nope');
  });

  test('"Add 1 task" and "Add 3 tasks"', () {
    expect(addTasksLabel(1), 'Add 1 task');
    expect(addTasksLabel(3), 'Add 3 tasks');
  });

  test('parse-many sends the text; adding creates each task in order', () async {
    final adapter = FakeAdapter((o) {
      if (o.uri.path == '/api/tasks/parse-many') return FakeAdapter.json(pasted());
      return FakeAdapter.json(task((o.data as Map)['title'] as String));
    });
    final repo = repoWith(adapter);
    final list = await repo.parseMany('Buy milk !high\nPack\n  Socks\n  Shoes');
    expect(adapter.requests.first.data, {'text': 'Buy milk !high\nPack\n  Socks\n  Shoes'});
    final added = await addPastedTasks(repo, list.tasks);
    expect(added.map((t) => t.title), ['Buy milk', 'Pack']);
    final titles = [
      for (final r in adapter.requests)
        if (r.uri.path == '/api/tasks') (r.data as Map)['title'],
    ];
    expect(titles, ['Buy milk', 'Pack']);
  });

  test('a failed add keeps the tasks still to add and names the problem', () async {
    var calls = 0;
    final adapter = FakeAdapter((o) {
      calls++;
      return calls == 1
          ? FakeAdapter.json(task('Buy milk'))
          : FakeAdapter.json({'detail': 'No room.'}, status: 422);
    });
    final repo = repoWith(adapter);
    final list = PastedList.fromJson(pasted());
    await expectLater(
      addPastedTasks(repo, list.tasks),
      throwsA(isA<PasteAddProblem>()
          .having((p) => p.left.map((t) => t.reading.title), 'left', ['Pack'])
          .having((p) => p.message, 'message', 'No room.')),
    );
  });
}
