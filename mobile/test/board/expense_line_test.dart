import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/api/providers.dart';
import 'package:roost_mobile/api/session_store.dart';
import 'package:roost_mobile/board/money/expense_line.dart';

import '../fake_adapter.dart';

const _reading = {
  'note': 'lunch',
  'amount': '62.00',
  'currency': 'EUR',
  'income': false,
  'amount_math': '2×31',
  'amount_words': '€2x31',
  'project': {
    'id': 'p1',
    'name': 'Trip',
    'currency': 'EUR',
    'color': '#3b82f6',
    'is_general': false,
  },
  'project_words': '/Trip',
  'spent_at': '2026-10-21',
  'day_words': 'yesterday',
  'spent_text': 'Wed 21 Oct',
  'vendor': 'Mercadona',
  'starred': false,
  'cadence': null,
  'ready': true,
  'warnings': <String>[],
};

void main() {
  testWidgets('shows the server reading as chips and adds exactly it',
      (tester) async {
    Object? created;
    final adapter = FakeAdapter((o) {
      if (o.path == '/api/money/parse') return FakeAdapter.json(_reading);
      if (o.path == '/api/money/expenses' && o.method == 'POST') {
        created = o.data;
        return FakeAdapter.json({'id': 'e1'}, status: 201);
      }
      fail('unexpected ${o.method} ${o.path}');
    });
    final container = ProviderContainer(overrides: [
      sessionStoreProvider.overrideWithValue(MemorySessionStore()),
      httpAdapterProvider.overrideWithValue(adapter),
    ]);
    addTearDown(container.dispose);
    var added = 0;
    await tester.pumpWidget(UncontrolledProviderScope(
      container: container,
      child: MaterialApp(
        home: Scaffold(body: ExpenseLine(onAdded: () => added++)),
      ),
    ));

    await tester.enterText(
        find.byType(TextField), '€2x31 lunch /Trip yesterday vendor:Mercadona');
    await tester.pump(const Duration(milliseconds: 400));
    await tester.pump();

    expect(find.text('€62.00 = 2×31'), findsOneWidget);
    expect(find.text('/Trip'), findsOneWidget);
    expect(find.text('Wed 21 Oct'), findsOneWidget);
    expect(find.text('at Mercadona'), findsOneWidget);

    await tester.tap(find.text('Add'));
    await tester.pumpAndSettle();

    expect(created, {
      'amount': '62.00',
      'currency': 'EUR',
      'project_id': 'p1',
      'note': 'lunch',
      'spent_at': '2026-10-21',
      'vendor': 'Mercadona',
    });
    expect(added, 1);
  });
}
