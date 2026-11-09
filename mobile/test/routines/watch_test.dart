import 'dart:convert';

import 'package:dio/dio.dart' show RequestOptions;
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/api/providers.dart';
import 'package:roost_mobile/api/session_store.dart';
import 'package:roost_mobile/routines/routine_editor.dart';
import 'package:roost_mobile/routines/watch_fields.dart';

import '../fake_adapter.dart';

const _watch = {
  'url': 'https://web.whatsapp.com/',
  'part': 'the physio chat',
  'every_min': 5,
  'host': 'web.whatsapp.com',
  'last_checked_at': '2026-11-04T13:55:00Z',
  'last_changed_at': '2026-11-04T13:50:00Z',
};

Future<FakeAdapter> _pumpEditor(WidgetTester tester, {Map<String, dynamic>? routine}) async {
  final adapter = FakeAdapter((RequestOptions o) => FakeAdapter.json({'id': 'r1'}));
  final container = ProviderContainer(overrides: [
    sessionStoreProvider.overrideWithValue(MemorySessionStore()),
    httpAdapterProvider.overrideWithValue(adapter),
  ]);
  addTearDown(container.dispose);
  tester.view.physicalSize = const Size(1080, 3000);
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
  test('the row line says what it watches, how often and when it last changed', () {
    final now = DateTime.utc(2026, 11, 4, 15);
    expect(watchLine({'watch': _watch}, now),
        'Watching web.whatsapp.com · every 5 min · last change 14:50');
    expect(watchLine({'watch': {..._watch, 'last_changed_at': '2026-11-02T13:50:00Z'}}, now),
        'Watching web.whatsapp.com · every 5 min · last change Mon 2 Nov 14:50');
    expect(watchLine({'watch': {..._watch, 'last_changed_at': null}}, now),
        'Watching web.whatsapp.com · every 5 min');
    expect(watchLine({'watch': null}, now), '');
  });

  test('the body is null when off, and the minutes default when unreadable', () {
    expect(watchBody(on: false, url: 'x', part: '', every: '5'), isNull);
    expect(watchBody(on: true, url: ' https://x.com ', part: ' price ', every: 'ten'),
        {'url': 'https://x.com', 'part': 'price', 'every_min': 5});
  });

  testWidgets('switching the watch on replaces the schedule and sends it', (tester) async {
    final adapter = await _pumpEditor(tester);
    expect(find.text('Days and times'), findsOneWidget);
    await tester.enterText(find.byKey(const Key('routine-name')), 'Physio');
    await tester.enterText(find.byKey(const Key('routine-instructions')), 'Tell me what Ana wrote');
    await tester.tap(find.byKey(const Key('routine-watch')));
    await tester.pumpAndSettle();
    expect(find.text('Days and times'), findsNothing);
    await tester.enterText(find.byKey(const Key('routine-watch-url')), 'https://web.whatsapp.com');
    await tester.enterText(find.byKey(const Key('routine-watch-part')), 'the physio chat');
    await tester.enterText(find.byKey(const Key('routine-watch-every')), '10');
    await tester.tap(find.byKey(const Key('routine-save')));
    await tester.pumpAndSettle();
    expect(_sent(adapter)['watch'],
        {'url': 'https://web.whatsapp.com', 'part': 'the physio chat', 'every_min': 10});
  });

  testWidgets('switching an existing watch off sends null', (tester) async {
    final adapter = await _pumpEditor(tester, routine: {
      'id': 'r1',
      'name': 'Physio',
      'instructions': 'Read',
      'schedule': {'kind': 'times', 'days': [1], 'times': ['09:00']},
      'watch': _watch,
    });
    expect(find.text('https://web.whatsapp.com/'), findsOneWidget);
    await tester.tap(find.byKey(const Key('routine-watch')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('routine-save')));
    await tester.pumpAndSettle();
    final sent = _sent(adapter);
    expect(sent.containsKey('watch'), isTrue);
    expect(sent['watch'], isNull);
  });
}
