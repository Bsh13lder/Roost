import 'dart:convert';

import 'package:dio/dio.dart' show RequestOptions;
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/api/providers.dart';
import 'package:roost_mobile/api/session_store.dart';
import 'package:roost_mobile/routines/routine_editor.dart';

import '../fake_adapter.dart';

const _models = {
  'choices': [
    {'id': 'claude-sonnet-5-5', 'label': 'Sonnet 5.5', 'line': 'sonnet', 'new': false},
    {'id': 'claude-haiku-5-5', 'label': 'Haiku 5.5', 'line': 'haiku', 'new': false},
  ],
  'efforts': ['low'],
  'default_effort': {},
};

Future<FakeAdapter> _pump(WidgetTester tester, {Map<String, dynamic>? routine}) async {
  final adapter = FakeAdapter((RequestOptions o) =>
      FakeAdapter.json(o.path.endsWith('/api/models') ? _models : {'id': 'r1'}));
  final container = ProviderContainer(overrides: [
    sessionStoreProvider.overrideWithValue(MemorySessionStore()),
    httpAdapterProvider.overrideWithValue(adapter),
  ]);
  addTearDown(container.dispose);
  tester.view.physicalSize = const Size(1080, 3200);
  tester.view.devicePixelRatio = 2.5;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(UncontrolledProviderScope(
    container: container,
    child: MaterialApp(home: Scaffold(body: RoutineEditor(botId: 'b1', routine: routine))),
  ));
  await tester.pumpAndSettle();
  return adapter;
}

Map<String, dynamic> _sent(FakeAdapter adapter) {
  final write = adapter.requests.lastWhere((r) => r.method == 'POST' || r.method == 'PATCH');
  final data = write.data;
  return (data is String ? jsonDecode(data) : data as Map).cast<String, dynamic>();
}

void main() {
  testWidgets('a new routine is Same as the bot and sends null', (tester) async {
    final adapter = await _pump(tester);
    expect(find.text('Same as the bot'), findsOneWidget);
    await tester.enterText(find.byKey(const Key('routine-name')), 'Prices');
    await tester.enterText(find.byKey(const Key('routine-instructions')), 'Check.');
    await tester.tap(find.byKey(const Key('routine-save')));
    await tester.pumpAndSettle();
    expect(_sent(adapter).containsKey('model'), isTrue);
    expect(_sent(adapter)['model'], isNull);
  });

  testWidgets('picking Haiku sends its id', (tester) async {
    final adapter = await _pump(tester, routine: {
      'id': 'r1', 'name': 'Prices', 'instructions': 'Check.',
      'schedule': {'kind': 'times', 'days': [1], 'times': ['09:00']}, 'model': null,
    });
    await tester.tap(find.byKey(const Key('routine-model')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Haiku 5.5').last);
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('routine-save')));
    await tester.pumpAndSettle();
    expect(_sent(adapter)['model'], 'claude-haiku-5-5');
  });
}
