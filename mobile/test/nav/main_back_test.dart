import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:roost_mobile/api/models.dart';
import 'package:roost_mobile/live/live_connection.dart';
import 'package:roost_mobile/nav/main_back.dart';

const _main = Bot(
    id: 'main',
    name: 'Chief',
    avatar: Avatar(),
    status: BotStatus.resting,
    isPrimary: true);
const _other =
    Bot(id: 'b2', name: 'Scout', avatar: Avatar(), status: BotStatus.resting);

/// Live bots without a socket.
class _Bots extends LiveController {
  _Bots(this.bots);

  final List<Bot> bots;

  @override
  LiveState build() => LiveState(bots: {for (final b in bots) b.id: b});
}

Widget _screen(String label) => Scaffold(
      appBar: AppBar(title: Text(label)),
      body: Builder(
        builder: (context) => TextButton(
          key: const Key('open-sheet'),
          onPressed: () => showModalBottomSheet<void>(
              context: context, builder: (_) => const Text('a sheet')),
          child: Text('screen $label'),
        ),
      ),
    );

GoRouter _router() => GoRouter(routes: [
      GoRoute(
          path: '/', builder: (_, _) => MainBackScope(child: _screen('home'))),
      GoRoute(
          path: '/board',
          builder: (_, _) => MainBackScope(child: _screen('board'))),
      GoRoute(
          path: '/settings',
          builder: (_, _) => MainBackScope(child: _screen('settings'))),
      GoRoute(
        path: '/chat/:botId',
        builder: (_, s) =>
            MainBackScope(child: _screen('chat ${s.pathParameters['botId']}')),
      ),
      GoRoute(
        path: '/profile/:botId',
        builder: (_, s) => MainBackScope(
            child: _screen('profile ${s.pathParameters['botId']}')),
      ),
    ]);

/// Counts the times the app leaves through SystemNavigator.pop.
class _Leaving {
  int count = 0;
}

_Leaving _watchLeaving(WidgetTester tester) {
  final leaving = _Leaving();
  final messenger = tester.binding.defaultBinaryMessenger;
  messenger.setMockMethodCallHandler(SystemChannels.platform, (call) async {
    if (call.method == 'SystemNavigator.pop') leaving.count++;
    return null;
  });
  addTearDown(
      () => messenger.setMockMethodCallHandler(SystemChannels.platform, null));
  return leaving;
}

Future<GoRouter> _pump(WidgetTester tester, List<Bot> bots) async {
  final router = _router();
  addTearDown(router.dispose);
  await tester.pumpWidget(ProviderScope(
    overrides: [liveProvider.overrideWith(() => _Bots(bots))],
    child: MaterialApp.router(routerConfig: router),
  ));
  await tester.pumpAndSettle();
  return router;
}

Future<void> _back(WidgetTester tester) async {
  await tester.binding.handlePopRoute();
  await tester.pumpAndSettle();
}

String _at(GoRouter r) =>
    r.routerDelegate.currentConfiguration.last.matchedLocation;

void main() {
  test('where Back goes', () {
    expect(backTarget('/chat/b2'), '/');
    expect(backTarget('/chat/main'), '/');
    expect(backTarget('/settings'), '/');
    expect(backTarget('/board'), '/');
    expect(backTarget('/profile/b2'), '/chat/b2');
    expect(backTarget('/computer/b2'), '/chat/b2');
    expect(backTarget('/bots/b2/routines/r1/log'), '/chat/b2');
    expect(backTarget('/board/projects/p1'), '/board');
    expect(backTarget('/'), isNull);
  });

  testWidgets("Back from a bot's chat opens Home, and Home leaves",
      (tester) async {
    final leaving = _watchLeaving(tester);
    final router = await _pump(tester, [_main, _other]);
    for (final bot in ['b2', 'main']) {
      router.go('/');
      router.push('/chat/$bot');
      await tester.pumpAndSettle();
      await _back(tester);
      expect(_at(router), '/', reason: bot);
      expect(find.text('screen home'), findsOneWidget);
      expect(router.canPop(), isFalse);
    }
    await _back(tester);
    expect(leaving.count, 1);
    expect(_at(router), '/');
  });

  testWidgets('Back never walks back through the pages you came by',
      (tester) async {
    final router = await _pump(tester, [_other, _main]);
    for (final page in ['/board', '/settings']) {
      router.go('/');
      router.push('/chat/b2');
      router.push(page);
      await tester.pumpAndSettle();
      await _back(tester);
      expect(_at(router), '/', reason: page);
    }
  });

  testWidgets("a bot's Profile goes back to its chat, then Home",
      (tester) async {
    final router = await _pump(tester, [_main, _other]);
    router.push('/chat/b2');
    router.push('/profile/b2');
    await tester.pumpAndSettle();
    await _back(tester);
    expect(_at(router), '/chat/b2');
    await _back(tester);
    expect(_at(router), '/');
  });

  testWidgets("the app bar's back arrow goes Home too", (tester) async {
    final router = await _pump(tester, [_main, _other]);
    router.push('/chat/b2');
    router.push('/settings');
    await tester.pumpAndSettle();
    await tester.tap(find.byType(BackButton));
    await tester.pumpAndSettle();
    expect(_at(router), '/');
  });

  testWidgets('Back with a sheet open closes only the sheet', (tester) async {
    final router = await _pump(tester, [_main, _other]);
    router.push('/chat/b2');
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('open-sheet')));
    await tester.pumpAndSettle();
    expect(find.text('a sheet'), findsOneWidget);
    await _back(tester);
    expect(find.text('a sheet'), findsNothing);
    expect(_at(router), '/chat/b2');
    await _back(tester);
    expect(_at(router), '/');
  });
}
