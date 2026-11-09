import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/api/providers.dart';
import 'package:roost_mobile/api/session_store.dart';
import 'package:roost_mobile/api/usage.dart';
import 'package:roost_mobile/features/settings/usage_line.dart';
import 'package:roost_mobile/profile/folds/usage_fold.dart';
import 'package:roost_mobile/theme/app_theme.dart';
import 'package:roost_mobile/theme/accent.dart';

import 'fake_adapter.dart';

Map<String, dynamic> counts(int input, int output) => {
      'input': input,
      'output': output,
      'cache_read': 0,
      'cache_write': 0,
      'calls': 1,
      'tokens_in': input,
      'tokens_out': output,
      'tokens': input + output,
    };

List<Map<String, dynamic>> week(int perDayIn) => [
      for (var i = 1; i <= 7; i++)
        {'day': '2026-11-0$i', ...counts(i == 7 ? perDayIn : 0, 0)},
    ];

Future<FakeAdapter> pump(
    WidgetTester tester, Widget child, FakeHandler handler) async {
  final adapter = FakeAdapter(handler);
  final store = MemorySessionStore()
    ..url = 'http://127.0.0.1:18800'
    ..token = 'tok';
  final container = ProviderContainer(overrides: [
    sessionStoreProvider.overrideWithValue(store),
    httpAdapterProvider.overrideWithValue(adapter),
  ]);
  addTearDown(container.dispose);
  await tester.pumpWidget(UncontrolledProviderScope(
    container: container,
    child: Consumer(
      builder: (_, ref, _) => MaterialApp(
        theme: buildTheme(ref.watch(accentProvider)),
        home: Scaffold(body: child),
      ),
    ),
  ));
  await tester.pumpAndSettle();
  return adapter;
}

void main() {
  group('compactTokens', () {
    test('small numbers stay whole', () {
      expect(compactTokens(0), '0');
      expect(compactTokens(999), '999');
    });
    test('thousands and millions get one decimal', () {
      expect(compactTokens(1000), '1k');
      expect(compactTokens(12345), '12.3k');
      expect(compactTokens(1234567), '1.2M');
      expect(compactTokens(5000000), '5M');
    });
  });

  group('parsing', () {
    test('missing fields read as zero or empty', () {
      final c = UsageCounts.fromJson(null);
      expect(c.tokens, 0);
      expect(c.tokensIn, 0);
      final s = UsageSummary.fromJson({});
      expect(s.perDay, isEmpty);
      expect(s.busiest, isNull);
      expect(s.total.tokens, 0);
      final b = BotUsage.fromJson({'per_day': 'nope'});
      expect(b.perDay, isEmpty);
    });

    test('reads the totals, days and busiest bot', () {
      final s = UsageSummary.fromJson({
        'days': 7,
        'today': '2026-11-07',
        'total': counts(1000, 200),
        'today_total': counts(300, 20),
        'per_day': week(300),
        'busiest': {'bot_id': 'b1', 'name': 'Scout', 'tokens': 1200},
      });
      expect(s.total.tokens, 1200);
      expect(s.todayTotal.tokensOut, 20);
      expect(s.perDay, hasLength(7));
      expect(s.perDay.last.day, '2026-11-07');
      expect(s.busiest!.name, 'Scout');
    });

    test('a usage line names the busiest bot only when there is one', () {
      final s = UsageSummary.fromJson({
        'total': counts(12000, 345),
        'today_total': counts(1000, 0),
        'busiest': {'bot_id': 'b1', 'name': 'Scout', 'tokens': 1},
      });
      expect(usageLine(s),
          'Tokens today: 1k · this week: 12.3k · busiest: Scout');
      expect(usageLine(UsageSummary.fromJson({})),
          'Tokens today: 0 · this week: 0');
    });
  });

  testWidgets('the Usage fold shows today, the week and a bar per day',
      (tester) async {
    final adapter = await pump(
        tester,
        const UsageFold(botId: 'b1'),
        (o) => FakeAdapter.json({
              'bot_id': 'b1',
              'days': 7,
              'today': '2026-11-07',
              'total': counts(12000, 345),
              'today_total': counts(1500, 45),
              'per_day': week(1500),
            }));
    expect(adapter.requests.single.uri.path, '/api/bots/b1/usage');
    expect(adapter.requests.single.uri.queryParameters['days'], '7');
    expect(find.text('Today: 1.5k tokens'), findsOneWidget);
    expect(find.text('Last 7 days: 12.3k tokens'), findsOneWidget);
    expect(find.text('in 12k · out 345'), findsOneWidget);
    expect(find.byKey(const Key('usage-bar')), findsNWidgets(7));
    expect(find.bySemanticsLabel('2026-11-07: 1.5k tokens'), findsOneWidget);
  });

  testWidgets('a bot with no usage says so', (tester) async {
    await pump(tester, const UsageFold(botId: 'b1'),
        (o) => FakeAdapter.json({'total': counts(0, 0), 'per_day': week(0)}));
    expect(find.text('No tokens used yet.'), findsOneWidget);
    expect(find.byKey(const Key('usage-bar')), findsNothing);
  });

  testWidgets('Settings shows one usage line', (tester) async {
    await pump(
        tester,
        const UsageLine(),
        (o) => FakeAdapter.json({
              'total': counts(12000, 345),
              'today_total': counts(1000, 0),
              'busiest': {'bot_id': 'b1', 'name': 'Scout', 'tokens': 1},
            }));
    expect(find.text('Tokens today: 1k · this week: 12.3k · busiest: Scout'),
        findsOneWidget);
  });

  testWidgets('the Settings line hides when the fetch fails', (tester) async {
    await pump(tester, const UsageLine(),
        (o) => FakeAdapter.json({'detail': 'boom'}, status: 500));
    expect(find.textContaining('Tokens today'), findsNothing);
  });
}
