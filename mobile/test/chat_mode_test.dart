import 'package:dio/dio.dart' show RequestOptions;
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/api/providers.dart';
import 'package:roost_mobile/api/session_store.dart';
import 'package:roost_mobile/chat/chat_mode.dart';
import 'package:roost_mobile/chat/chat_mode_pill.dart';
import 'package:roost_mobile/profile/approval_card.dart';
import 'package:roost_mobile/profile/bot_detail.dart';

import 'fake_adapter.dart';

Map<String, Object?> botJson({
  List<String> topics = const ['files'],
  bool? autoReview,
  String computer = 'linux',
  String mode = 'auto_edit',
}) =>
    {
      'id': 'b1',
      'name': 'Gogi',
      'avatar': {'shape': 'mochi', 'color': '#8B5CF6'},
      'computer': computer,
      'status': 'resting',
      'approval': {
        'mode': mode,
        'ask_topics': topics,
        'locked_topics': <String>[],
        'auto_review': ?autoReview,
      },
    };

BotDetail bot({List<String> topics = const ['files'], bool? autoReview}) =>
    BotDetail.fromJson(botJson(topics: topics, autoReview: autoReview));

/// Serves [start] for GET and echoes each approval PUT back as the bot,
/// unless [failPut] is set.
class FakeBotServer {
  FakeBotServer(this.start, {this.failPut = false});

  Map<String, Object?> start;
  final bool failPut;
  late final adapter = FakeAdapter(_answer);

  FakeReply _answer(RequestOptions o) {
    if (o.path == '/api/bots/b1/approval' && o.method == 'PUT') {
      if (failPut) return FakeAdapter.json({'detail': 'nope'}, status: 500);
      final body = (o.data as Map).cast<String, Object?>();
      final old = (start['approval'] as Map).cast<String, Object?>();
      start = {
        ...start,
        'approval': {
          ...old,
          'mode': body['mode'],
          'ask_topics': body['ask_topics'],
          if (body.containsKey('auto_review')) 'auto_review': body['auto_review'],
        },
      };
      return FakeAdapter.json(start);
    }
    if (o.path == '/api/bots/b1') return FakeAdapter.json(start);
    return FakeAdapter.json({});
  }

  Iterable<RequestOptions> get puts =>
      adapter.requests.where((r) => r.method == 'PUT');
}

Future<void> pumpWith(WidgetTester tester, FakeBotServer server, Widget child) async {
  final container = ProviderContainer(overrides: [
    sessionStoreProvider.overrideWithValue(MemorySessionStore()),
    httpAdapterProvider.overrideWithValue(server.adapter),
  ]);
  addTearDown(container.dispose);
  await tester.pumpWidget(UncontrolledProviderScope(
    container: container,
    child: MaterialApp(home: Scaffold(body: child)),
  ));
  await tester.pumpAndSettle();
}

/// The profile's card, fed from the live bot detail like the Settings page.
class _CardHost extends ConsumerWidget {
  const _CardHost();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final detail = ref.watch(botDetailProvider('b1')).valueOrNull;
    if (detail == null) return const SizedBox();
    return SingleChildScrollView(child: ApprovalCard(bot: detail));
  }
}

void main() {
  group('chatModeOf', () {
    test('browsing in the topics is Ask me, whatever auto_review says', () {
      expect(chatModeOf(bot(topics: ['browsing'], autoReview: true)), ChatMode.askMe);
    });
    test('auto_review without browsing is Full auto', () {
      expect(chatModeOf(bot(autoReview: true)), ChatMode.fullAuto);
    });
    test('neither is Just browse; a missing auto_review is false', () {
      expect(chatModeOf(bot()), ChatMode.justBrowse);
      expect(bot().autoReview, isFalse);
    });
  });

  group('approvalFor', () {
    test('Ask me adds browsing once and turns auto_review off', () {
      final w = approvalFor(bot(autoReview: true), ChatMode.askMe);
      expect(w.toJson(), {
        'mode': 'auto_edit',
        'ask_topics': ['files', 'browsing'],
        'auto_review': false,
      });
      final again = approvalFor(bot(topics: ['browsing']), ChatMode.askMe);
      expect(again.askTopics, ['browsing']);
    });
    test('Just browse drops browsing, auto_review off', () {
      final w = approvalFor(bot(topics: ['files', 'browsing']), ChatMode.justBrowse);
      expect(w.toJson(),
          {'mode': 'auto_edit', 'ask_topics': ['files'], 'auto_review': false});
    });
    test('Full auto drops browsing, auto_review on', () {
      final w = approvalFor(bot(topics: ['browsing']), ChatMode.fullAuto);
      expect(w.toJson(),
          {'mode': 'auto_edit', 'ask_topics': <String>[], 'auto_review': true});
    });
    test('every mode has a label and one explanation line', () {
      expect([for (final m in ChatMode.values) chatModeLabel(m)],
          ['Ask me', 'Just browse', 'Full auto']);
      expect(chatModeExplanation(ChatMode.askMe),
          'Every click on its computer waits for your OK.');
      expect(chatModeExplanation(ChatMode.justBrowse),
          "Ordinary clicks just happen. Buttons it can't read still ask.");
      expect(
          chatModeExplanation(ChatMode.fullAuto),
          "A checker looks at buttons it can't read first. Paying, sending, "
          'deleting, typing and new sites still ask.');
    });
  });

  group('the pill', () {
    testWidgets('shows the mode; the sheet picks Full auto with one PUT',
        (tester) async {
      final server = FakeBotServer(botJson());
      await pumpWith(tester, server, const ChatModePill(botId: 'b1'));
      expect(find.text('Just browse'), findsOneWidget);

      await tester.tap(find.byKey(const Key('chat-mode-pill')));
      await tester.pumpAndSettle();
      expect(find.text(chatModeExplanation(ChatMode.askMe)), findsOneWidget);
      expect(find.text(chatModeExplanation(ChatMode.fullAuto)), findsOneWidget);
      expect(
          find.descendant(
              of: find.byKey(const Key('chat-mode-justBrowse')),
              matching: find.byIcon(Icons.check)),
          findsOneWidget);

      await tester.tap(find.byKey(const Key('chat-mode-fullAuto')));
      await tester.pumpAndSettle();
      expect(server.puts.single.data,
          {'mode': 'auto_edit', 'ask_topics': ['files'], 'auto_review': true});
      expect(find.text('Full auto'), findsOneWidget);
    });

    testWidgets('a failed save says so and keeps the old mode', (tester) async {
      final server = FakeBotServer(botJson(topics: ['browsing']), failPut: true);
      await pumpWith(tester, server, const ChatModePill(botId: 'b1'));
      await tester.tap(find.byKey(const Key('chat-mode-pill')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('chat-mode-justBrowse')));
      await tester.pumpAndSettle();
      expect(find.byType(SnackBar), findsOneWidget);
      expect(find.text('Ask me'), findsOneWidget);
    });

    testWidgets('only for a bot on its Linux computer', (tester) async {
      final server = FakeBotServer(botJson(computer: 'mac_brave'));
      await pumpWith(tester, server, const ChatModePill(botId: 'b1'));
      expect(find.byKey(const Key('chat-mode-pill')), findsNothing);
    });
  });

  group('the profile row', () {
    testWidgets('shows three choices and the chosen one explained',
        (tester) async {
      final server = FakeBotServer(botJson(autoReview: true));
      await pumpWith(tester, server, const _CardHost());
      expect(find.text('Browsing actions'), findsOneWidget);
      for (final m in ChatMode.values) {
        expect(find.text(chatModeLabel(m)), findsOneWidget);
      }
      expect(find.text(chatModeExplanation(ChatMode.fullAuto)), findsOneWidget);
      expect(find.text(chatModeExplanation(ChatMode.askMe)), findsNothing);
    });

    testWidgets('choosing Ask me saves the topics with browsing', (tester) async {
      final server = FakeBotServer(botJson(autoReview: true));
      await pumpWith(tester, server, const _CardHost());
      await tester.tap(find.text('Ask me'));
      await tester.pumpAndSettle();
      expect(server.puts.single.data, {
        'mode': 'auto_edit',
        'ask_topics': ['files', 'browsing'],
        'auto_review': false,
      });
      expect(find.text(chatModeExplanation(ChatMode.askMe)), findsOneWidget);
    });

    testWidgets('a topic switch does not send auto_review', (tester) async {
      final server = FakeBotServer(botJson(autoReview: true));
      await pumpWith(tester, server, const _CardHost());
      await tester.tap(find.text('Tasks'));
      await tester.pumpAndSettle();
      expect(server.puts.single.data,
          {'mode': 'auto_edit', 'ask_topics': ['files', 'tasks']});
    });

    testWidgets('a Mac Brave bot has no browsing row', (tester) async {
      final server = FakeBotServer(botJson(computer: 'mac_brave'));
      await pumpWith(tester, server, const _CardHost());
      expect(find.text('Browsing actions'), findsNothing);
      expect(find.text('Full auto'), findsNothing);
    });
  });
}
