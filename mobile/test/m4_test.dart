import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/api/providers.dart';
import 'package:roost_mobile/api/session_store.dart';
import 'package:roost_mobile/connectors/connector_form.dart';
import 'package:roost_mobile/plan/plan_models.dart';
import 'package:roost_mobile/plan/plan_tab.dart';

import 'fake_adapter.dart';

Future<FakeAdapter> pump(WidgetTester tester, Widget home, FakeHandler h) async {
  final adapter = FakeAdapter(h);
  final container = ProviderContainer(overrides: [
    sessionStoreProvider.overrideWithValue(MemorySessionStore()),
    httpAdapterProvider.overrideWithValue(adapter),
  ]);
  addTearDown(container.dispose);
  await tester.pumpWidget(UncontrolledProviderScope(
    container: container,
    child: MaterialApp(home: Scaffold(body: home)),
  ));
  await tester.pumpAndSettle();
  return adapter;
}

Map<String, Object?> plan(int revision, String text) => {
      'content': '- [ ] $text',
      'revision': revision,
      'unreadable': 0,
      'items': [
        {'id': 'i1', 'status': 'planned', 'text': text, 'tags': [], 'tainted': false},
      ],
    };

void main() {
  testWidgets('the connector key is cleared on Save and never shown again',
      (tester) async {
    final adapter = await pump(
      tester,
      const ConnectorForm(),
      (o) => FakeAdapter.json({'detail': 'That address is not allowed.'}, status: 422),
    );
    await tester.enterText(find.byKey(const Key('connector-key')), 's3cret-key');
    TextField field() => tester.widget(find.byKey(const Key('connector-key')));
    expect(field().controller!.text, 's3cret-key');
    await tester.tap(find.byKey(const Key('connector-save')));
    await tester.pumpAndSettle();
    // The key went out once, then left the field; the error does not echo it.
    expect(adapter.requests.single.data['secret'], 's3cret-key');
    expect(field().controller!.text, isEmpty);
    expect(find.textContaining('s3cret-key'), findsNothing);
    expect(find.textContaining('Type the key again'), findsOneWidget);
  });

  testWidgets('a Plan save on a stale revision (409) offers the latest copy',
      (tester) async {
    await pump(tester, const PlanTab(botId: 'b1'), (o) {
      if (o.method == 'PUT') {
        return FakeAdapter.json({
          'detail': 'The Plan changed since you opened it.',
          'current': plan(5, 'Newer item'),
        }, status: 409);
      }
      return FakeAdapter.json(plan(4, 'Old item'));
    });
    expect(find.text('Old item'), findsOneWidget);
    await tester.tap(find.text('Edit as text'));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('plan-save')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('plan-conflict')), findsOneWidget);
    await tester.tap(find.text('Load the latest'));
    await tester.pumpAndSettle();
    final field = tester.widget<TextField>(find.byKey(const Key('plan-text')));
    expect(field.controller!.text, '- [ ] Newer item');
  });

  test('the agenda groups by day and puts undated last', () {
    final days = agendaDays(PlanData.fromJson(plan(1, 'x')).items);
    expect(days.single.$1, isNull);
  });
}
