import 'package:dio/dio.dart' show RequestOptions;
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/api/models.dart';
import 'package:roost_mobile/api/providers.dart';
import 'package:roost_mobile/api/session_store.dart';
import 'package:roost_mobile/profile/profile_screen.dart';
import 'package:roost_mobile/profile/profile_values.dart';

import '../fake_adapter.dart';

final _now = DateTime.now().toUtc();
String _ago(Duration d) => _now.subtract(d).toIso8601String();

Map<String, Object?> botJson({bool primary = false}) => {
      'id': 'b1',
      'name': 'Gogi',
      'job': 'Finds flights',
      'instructions': 'Be kind',
      'avatar': {'shape': 'mochi', 'color': '#8B5CF6'},
      'model': 'claude-sonnet-5-5',
      'model_label': 'Sonnet 5.5',
      'effort': null,
      'notify': true,
      'is_primary': primary,
      'group': '',
      'computer': 'linux',
      'status': 'resting',
      'full_limit_until': null,
      'approval': {'mode': 'ask', 'ask_topics': [], 'locked_topics': []},
    };

FakeReply profileAnswer(RequestOptions o) => switch (o.uri.path) {
      '/api/bots/b1' => FakeAdapter.json(botJson()),
      '/api/bots/b1/routines' => FakeAdapter.json({
          'routines': [
            {'id': 'r1', 'name': 'Morning prices', 'enabled': true, 'words': 'Every day at 09:00'},
            {'id': 'r2', 'name': 'Weekly wrap', 'enabled': false, 'words': 'Fridays'},
          ]
        }),
      '/api/bots/b1/desk' => FakeAdapter.json(
          {'state': 'running', 'computer': 'linux', 'browser': 'running', 'workspace': 'absent'}),
      '/api/bots/b1/made' => FakeAdapter.json({
          'tasks': [],
          'expenses': [],
          'notes': [],
          'documents': [
            {'id': 'd1', 'kind': 'doc', 'title': 'Flight notes', 'created_at': _ago(const Duration(minutes: 5))},
            {'id': 'd2', 'kind': 'pdf', 'title': 'Old receipt', 'created_at': _ago(const Duration(days: 30))},
          ],
        }),
      '/api/bots/b1/links' => FakeAdapter.json([
          {'url': 'https://example.com/a', 'host': 'example.com', 'created_at': _ago(const Duration(days: 3))},
        ]),
      '/api/bots/b1/notify' => FakeAdapter.json({...botJson(), 'notify': false}),
      '/api/plan' || '/api/bots/b1/plan' => FakeAdapter.json(
          {'text': '', 'items': [], 'revision': 1, 'unreadable': 0}),
      _ => FakeAdapter.json({}),
    };

Future<FakeAdapter> pumpProfile(WidgetTester tester) async {
  final adapter = FakeAdapter(profileAnswer);
  final container = ProviderContainer(overrides: [
    sessionStoreProvider.overrideWithValue(MemorySessionStore()),
    httpAdapterProvider.overrideWithValue(adapter),
  ]);
  addTearDown(container.dispose);
  tester.view.physicalSize = const Size(1080, 2400);
  tester.view.devicePixelRatio = 2.5;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(UncontrolledProviderScope(
    container: container,
    child: const MaterialApp(home: ProfileScreen(botId: 'b1')),
  ));
  await tester.pumpAndSettle();
  return adapter;
}

void main() {
  group('values', () {
    test('the Computer row says On it, Idle or Asleep', () {
      const linux = {'computer': 'linux', 'state': 'running', 'browser': 'running'};
      expect(computerStatusWord(BotStatus.onIt, linux), 'On it');
      expect(computerStatusWord(BotStatus.resting, linux), 'Idle');
      for (final s in ['paused', 'stopped', 'absent']) {
        expect(computerStatusWord(BotStatus.resting, {...linux, 'state': s}), 'Asleep');
      }
      expect(
          computerStatusWord(BotStatus.resting,
              {'computer': 'mac_brave', 'state': null, 'browser': 'stopped'}),
          'Asleep');
      expect(
          computerStatusWord(BotStatus.resting,
              {'computer': 'mac_brave', 'state': null, 'browser': 'running'}),
          'Idle');
      expect(computerStatusWord(BotStatus.resting, null), '');
      expect(computerStatusWord(BotStatus.onIt, null), 'On it');
    });

    test('routines count the ones that are on', () {
      expect(routinesOnLabel(const []), '');
      expect(
          routinesOnLabel(const [
            {'enabled': true},
            {'enabled': true},
            {'enabled': false},
          ]),
          '2 on');
      expect(routinesOnLabel(const [{'enabled': false}]), '0 on');
    });

    test('the Library groups by Today, This week and Earlier (Madrid days)', () {
      final now = DateTime.utc(2026, 10, 23, 12);
      final items = [
        LibraryItem(kind: LibraryKind.document, title: 'a', detail: '', createdAt: '2026-10-23T09:00:00Z'),
        LibraryItem(kind: LibraryKind.link, title: 'b', detail: '', createdAt: '2026-10-20T09:00:00Z'),
        LibraryItem(kind: LibraryKind.document, title: 'c', detail: '', createdAt: '2026-09-01T09:00:00Z'),
        // 23:30 UTC on the 22nd is already the 23rd in Madrid.
        LibraryItem(kind: LibraryKind.link, title: 'd', detail: '', createdAt: '2026-10-22T23:30:00Z'),
      ];
      final groups = libraryGroups(items, now);
      expect([for (final g in groups) g.label], ['Today', 'This week', 'Earlier']);
      expect([for (final i in groups[0].items) i.title], ['a', 'd']);
      expect([for (final i in groups[1].items) i.title], ['b']);
      expect([for (final i in groups[2].items) i.title], ['c']);
    });
  });

  testWidgets('the profile is a header and one card of rows, no tabs',
      (tester) async {
    await pumpProfile(tester);
    expect(find.byType(TabBar), findsNothing);
    expect(find.text('Gogi'), findsOneWidget);
    expect(find.byKey(const Key('profile-edit')), findsOneWidget);
    expect(find.text('Plan & routines'), findsOneWidget);
    expect(find.text('1 on'), findsOneWidget);
    expect(find.text('Computer'), findsOneWidget);
    expect(find.text('Idle'), findsOneWidget);
    expect(find.text('Library'), findsOneWidget);
    expect(find.text('Settings'), findsOneWidget);
    expect(find.text('Notifications'), findsOneWidget);
    expect(find.text(notifyCaption), findsOneWidget);
  });

  testWidgets('the Notifications switch saves bots.notify', (tester) async {
    final adapter = await pumpProfile(tester);
    await tester.tap(find.byKey(const Key('profile-notify')));
    await tester.pumpAndSettle();
    final put = adapter.requests.where((r) => r.path == '/api/bots/b1/notify');
    expect(put.single.data, {'notify': false});
  });

  testWidgets('Library lists documents and links by when', (tester) async {
    await pumpProfile(tester);
    await tester.tap(find.text('Library'));
    await tester.pumpAndSettle();
    expect(find.text('Today'), findsOneWidget);
    expect(find.text('This week'), findsOneWidget);
    expect(find.text('Earlier'), findsOneWidget);
    expect(find.text('Flight notes'), findsOneWidget);
    expect(find.text('example.com'), findsOneWidget);
    expect(find.text('Old receipt'), findsOneWidget);
  });

  testWidgets('Settings holds the grouped cards and ends with Retire',
      (tester) async {
    await pumpProfile(tester);
    await tester.tap(find.text('Settings'));
    await tester.pumpAndSettle();
    for (final label in [
      'Model & effort',
      'Approval mode',
      'What I remember',
      'Skills',
      'Decisions',
      'Question book',
      'Journal',
      'Your Mac: folders',
    ]) {
      await tester.scrollUntilVisible(find.text(label), 200,
          scrollable: find.byType(Scrollable).last);
      // The lazy list re-estimates its length as tall cards leave it.
      await tester.pumpAndSettle();
      expect(find.text(label), findsWidgets);
    }
    await tester.scrollUntilVisible(find.byKey(const Key('retire-bot')), 200,
        scrollable: find.byType(Scrollable).last);
    expect(find.text('Retire this bot'), findsOneWidget);
    expect(find.text('Linux computer'), findsOneWidget);
    expect(find.text('Use the full limit until it resets'), findsOneWidget);
  });

  testWidgets('Plan & routines shows the Plan with the routines under it',
      (tester) async {
    await pumpProfile(tester);
    await tester.tap(find.text('Plan & routines'));
    await tester.pumpAndSettle();
    expect(find.text('Kanban'), findsOneWidget);
    expect(find.text('Morning prices'), findsOneWidget);
    expect(find.text('Weekly wrap'), findsOneWidget);
    expect(find.byKey(const Key('new-routine')), findsOneWidget);
  });

  testWidgets('Computer shows the status and Take control at the bottom',
      (tester) async {
    await pumpProfile(tester);
    await tester.tap(find.text('Computer'));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('take-control')), findsOneWidget);
    expect(find.byKey(const Key('open-live')), findsOneWidget);
  });
}
