import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/api/providers.dart';
import 'package:roost_mobile/api/session_store.dart';
import 'package:roost_mobile/board/tasks/drawer_money_view.dart';
import 'package:roost_mobile/board/tasks/task_drawer.dart';

import '../fake_adapter.dart';

// The owner's request of 2026-10-26: on the phone, comments, budgets and
// expenses on a task and on each of its steps, on a 360 dp screen.

Map<String, Object?> detail() => {
      'id': 't1',
      'title': 'Fix the sink',
      'status': 'todo',
      'priority': 'medium',
      'project_id': null,
      'allocated_budget': '40.00',
      'pre_reminders': <String>[],
      'steps': [
        {'id': 's1', 'title': 'Buy a washer with a very long name for a phone', 'done': false},
      ],
      'tags': <String>[],
      'tainted': false,
      'created_at': '2026-10-23T10:00:00+00:00',
      'updated_at': '2026-10-23T10:00:00+00:00',
      'money': {
        'planned': '40.00', 'spent': '25.00', 'left': '15.00', 'currency': 'EUR',
        'used_percent': 62, 'tone': 'ok', 'steps': {'s1': '25.00'},
        'other_currencies': <String, Object?>{}, 'steps_other_currencies': <String, Object?>{},
        'steps_money': {
          's1': {'planned': '20.00', 'spent': '25.00', 'left': '-5.00', 'used_percent': 125, 'tone': 'over'},
        },
      },
      'expenses': [
        {'id': 'e1', 'amount': '25.00', 'currency': 'EUR', 'description': 'washers', 'step_id': 's1',
         'spent_at': '2026-10-25', 'status': 'posted', 'is_favorite': false, 'task_id': 't1'},
      ],
    };

void main() {
  late List<({String method, String path, Object? body})> writes;

  Future<void> pumpDrawer(WidgetTester tester) async {
    await tester.binding.setSurfaceSize(const Size(360, 2000));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    writes = [];
    final adapter = FakeAdapter((o) {
      if (o.method != 'GET') {
        writes.add((method: o.method, path: o.path, body: o.data));
        return FakeAdapter.json(o.path == '/api/tasks/t1' ? detail() : <String, Object?>{});
      }
      if (o.path == '/api/tasks/t1') return FakeAdapter.json(detail());
      return FakeAdapter.json([]);
    });
    final container = ProviderContainer(overrides: [
      sessionStoreProvider.overrideWithValue(MemorySessionStore()),
      httpAdapterProvider.overrideWithValue(adapter),
    ]);
    addTearDown(container.dispose);
    await tester.pumpWidget(UncontrolledProviderScope(
      container: container,
      child: const MaterialApp(home: TaskDrawer(taskId: 't1')),
    ));
    await tester.pumpAndSettle();
  }

  Future<void> stepMenu(WidgetTester tester, String item) async {
    await tester.tap(find.byKey(const Key('step-menu-s1')));
    await tester.pumpAndSettle();
    await tester.tap(find.text(item));
    await tester.pumpAndSettle();
  }

  testWidgets('a task in no project shows its money in General and its budget', (tester) async {
    await pumpDrawer(tester);
    expect(find.text('In no project, so its money counts in General, in EUR.'), findsOneWidget);
    expect(find.text('€40.00'), findsWidgets);
    expect(find.text('€25.00 of €20.00 · €5.00 over'), findsOneWidget);
  });

  testWidgets('the task budget is set from its row, at once', (tester) async {
    await pumpDrawer(tester);
    await tester.tap(find.byKey(const Key('drawer-budget')));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('budget-amount')), '55');
    await tester.tap(find.byKey(const Key('budget-save')));
    await tester.pumpAndSettle();
    expect(writes.single.path, '/api/tasks/t1');
    expect(writes.single.body, {'allocated_budget': '55'});
  });

  testWidgets('the task budget is cleared', (tester) async {
    await pumpDrawer(tester);
    await tester.tap(find.byKey(const Key('drawer-budget')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('budget-clear')));
    await tester.pumpAndSettle();
    expect(writes.single.body, {'allocated_budget': null});
  });

  testWidgets('a step gets its own budget from its menu', (tester) async {
    await pumpDrawer(tester);
    await stepMenu(tester, 'Budget…');
    await tester.enterText(find.byKey(const Key('budget-amount')), '30');
    await tester.tap(find.byKey(const Key('budget-save')));
    await tester.pumpAndSettle();
    expect(writes.single.method, 'PATCH');
    expect(writes.single.path, '/api/tasks/t1/steps/s1');
    expect(writes.single.body, {'budget': '30'});
  });

  testWidgets('an expense is added for one step, from the step menu', (tester) async {
    await pumpDrawer(tester);
    await stepMenu(tester, 'Add expense…');
    await tester.enterText(find.byKey(const Key('expense-amount')), '8,40');
    await tester.enterText(find.byKey(const Key('expense-note')), 'tape');
    await tester.tap(find.byKey(const Key('expense-save')));
    await tester.pumpAndSettle();
    expect(writes.single.path, '/api/money/expenses');
    expect(writes.single.body, {'amount': '8,40', 'task_id': 't1', 'step_id': 's1', 'note': 'tape'});
  });

  testWidgets('an expense is added for the whole task, with a day', (tester) async {
    await pumpDrawer(tester);
    await tester.tap(find.byKey(const Key('money-add')));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('expense-amount')), '12');
    await tester.enterText(find.byKey(const Key('expense-day')), 'yesterday');
    await tester.tap(find.byKey(const Key('expense-save')));
    await tester.pumpAndSettle();
    expect(writes.single.body, {'amount': '12', 'task_id': 't1', 'spent_at': 'yesterday'});
  });

  testWidgets('an expense is deleted from its sheet', (tester) async {
    await pumpDrawer(tester);
    await tester.tap(find.byKey(const ValueKey('expense-e1')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Delete'));
    await tester.pumpAndSettle();
    expect(writes.single.method, 'DELETE');
    expect(writes.single.path, '/api/money/expenses/e1');
  });

  testWidgets('a comment on a step, from its menu and from the thread', (tester) async {
    await pumpDrawer(tester);
    await stepMenu(tester, 'Comment…');
    await tester.enterText(find.byKey(const Key('step-comment')), 'Bought the wrong size');
    await tester.tap(find.byKey(const Key('step-comment-send')));
    await tester.pumpAndSettle();
    expect(writes.single.path, '/api/tasks/t1/comments');
    expect(writes.single.body, {'body': 'Bought the wrong size', 'step_id': 's1'});

    await tester.tap(find.byKey(const Key('comment-about-pick')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Buy a washer with a very long name for a phone').last);
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('comment-about')), findsOneWidget);
    await tester.enterText(find.byKey(const Key('comment-add')), 'Fits now');
    await tester.testTextInput.receiveAction(TextInputAction.done);
    await tester.pumpAndSettle();
    expect(writes.last.body, {'body': 'Fits now', 'step_id': 's1'});
    await tester.pumpWidget(const SizedBox());
    await tester.pump(const Duration(seconds: 5));
  });

  test('money words come from the server numbers', () {
    const line = MoneyLine(spent: '7.00');
    expect(line.words('EUR'), '€7.00 spent');
    expect(const MoneyLine(spent: '0.00').words('EUR'), isNull);
    expect(TaskMoneyView.fromDetail({'money': null}), isNull);
  });
}
