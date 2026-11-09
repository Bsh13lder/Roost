import 'package:dio/dio.dart' show RequestOptions;
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/api/models.dart';
import 'package:roost_mobile/api/providers.dart';
import 'package:roost_mobile/api/session_store.dart';
import 'package:roost_mobile/features/chat/chat_screen.dart';
import 'package:roost_mobile/live/live_connection.dart';
import 'package:roost_mobile/notify/notify_providers.dart';
import 'package:roost_mobile/voice/audio_ports.dart';

import '../fake_adapter.dart';
import 'voice_fakes.dart';

Map<String, Object?> msg(
  String id,
  String role,
  String body,
  int seq, {
  String thread = 't1',
}) => {
  'id': id,
  'thread_id': thread,
  'role': role,
  'body': body,
  'tainted': false,
  'seq': seq,
  'created_at': '2026-10-30T12:19:00+00:00',
  'kind': 'text',
  'author_bot_id': role == 'bot' ? 'b1' : null,
};

class _Harness {
  _Harness({this.available = true, this.transcribe, FakeRecorder? recorder})
    : recorder = recorder ?? FakeRecorder();

  final bool available;
  final FakeReply Function(RequestOptions o)? transcribe;
  final FakeRecorder recorder;
  final player = FakePlayer();
  late final FakeAdapter adapter = FakeAdapter(_answer);
  late final ProviderContainer container = ProviderContainer(
    overrides: [
      sessionStoreProvider.overrideWithValue(MemorySessionStore()),
      httpAdapterProvider.overrideWithValue(adapter),
      voiceRecorderProvider.overrideWithValue(recorder),
      voicePlayerProvider.overrideWithValue(player),
    ],
  );

  FakeReply _answer(RequestOptions o) {
    final path = o.uri.path;
    if (path == '/api/voice') {
      return FakeAdapter.json({
        'available': available,
        'speakers': [
          {'id': 'aiden', 'name': 'Aiden', 'best_in': 'English'},
        ],
        'tones': [
          {'id': 'natural', 'name': 'Natural'},
        ],
        'speeds': [1.0, 1.25],
      });
    }
    if (path == '/api/bots/b1/chat') {
      return FakeAdapter.json({'id': 't1', 'bot_id': 'b1'});
    }
    if (path == '/api/threads/t1/messages' && o.method == 'GET') {
      return FakeAdapter.json([msg('m1', 'bot', 'Hello there', 1)]);
    }
    if (path == '/api/voice/transcribe') {
      return transcribe!(o);
    }
    if (path.endsWith('/speech')) {
      return FakeAdapter.json({'parts': 1, 'speed': 1.5});
    }
    if (path.endsWith('/speech/0')) return FakeAdapter.json('spoken');
    return FakeAdapter.json({});
  }

  Future<void> open(WidgetTester tester, {bool readAloud = false}) async {
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: ChatScreen(botId: 'b1')),
      ),
    );
    await tester.pumpAndSettle();
    // After the saved session has loaded (which starts the bots afresh).
    container.read(liveProvider.notifier).seed([
      Bot.fromJson({
        'id': 'b1',
        'name': 'Gogi',
        'voice': {
          'speaker': 'aiden',
          'tone': 'natural',
          'speed': 1.5,
          'read_aloud': readAloud,
        },
      }),
    ]);
    await tester.pumpAndSettle();
  }

  void frame(Map<String, dynamic> f) => container.read(frameBusProvider).add(f);

  Iterable<String> get paths => adapter.requests.map((r) => r.uri.path);
}

void main() {
  testWidgets('mic: record, stop, and the words land in the composer unsent', (
    tester,
  ) async {
    final h = _Harness(
      transcribe: (o) => FakeAdapter.json({'text': 'book the flight'}),
    );
    addTearDown(h.container.dispose);
    await h.open(tester);
    await tester.enterText(find.byKey(const Key('composer')), 'Please');

    await tester.tap(find.byKey(const Key('mic')));
    await tester.pump();
    expect(h.recorder.started, isTrue);
    expect(find.byKey(const Key('recording-strip')), findsOneWidget);
    expect(find.byKey(const Key('mic-dot')), findsOneWidget);
    expect(find.text('0:00'), findsOneWidget);
    await tester.pump(const Duration(seconds: 2));
    expect(find.text('0:02'), findsOneWidget);

    await tester.tap(find.byKey(const Key('mic-stop')));
    await tester.pumpAndSettle();

    final sent = h.adapter.requests.firstWhere(
      (r) => r.uri.path == '/api/voice/transcribe',
    );
    expect(sent.method, 'POST');
    expect(sent.contentType, 'audio/wav');
    final field = tester.widget<TextField>(find.byKey(const Key('composer')));
    expect(field.controller!.text, 'Please book the flight');
    expect(
      h.paths.where((p) => p == '/api/threads/t1/messages'),
      hasLength(1),
      reason: 'only the first load; nothing was sent',
    );
  });

  testWidgets('mic: "Listening…" shows while the Mac hears it', (tester) async {
    final h = _Harness(transcribe: (o) => FakeAdapter.json({'text': 'hi'}));
    addTearDown(h.container.dispose);
    await h.open(tester);
    await tester.tap(find.byKey(const Key('mic')));
    await tester.pump();
    await tester.tap(find.byKey(const Key('mic-stop')));
    await tester.pump();
    expect(find.text('Listening…'), findsOneWidget);
    await tester.pumpAndSettle();
    expect(find.text('Listening…'), findsNothing);
  });

  testWidgets('mic: voice off on the Mac shows its words', (tester) async {
    final h = _Harness(
      transcribe: (o) => FakeAdapter.json({
        'detail': "Voice isn't running on your Mac yet.",
      }, status: 503),
    );
    addTearDown(h.container.dispose);
    await h.open(tester);
    await tester.tap(find.byKey(const Key('mic')));
    await tester.pump();
    await tester.tap(find.byKey(const Key('mic-stop')));
    await tester.pumpAndSettle();
    expect(find.text("Voice isn't running on your Mac yet."), findsOneWidget);
    expect(find.byKey(const Key('composer')), findsOneWidget);
  });

  testWidgets('mic: an unreadable recording (422) shows the gateway\'s words', (
    tester,
  ) async {
    final h = _Harness(
      transcribe: (o) => FakeAdapter.json({
        'detail': "That recording couldn't be read.",
      }, status: 422),
    );
    addTearDown(h.container.dispose);
    await h.open(tester);
    await tester.tap(find.byKey(const Key('mic')));
    await tester.pump();
    await tester.tap(find.byKey(const Key('mic-stop')));
    await tester.pumpAndSettle();
    expect(find.text("That recording couldn't be read."), findsOneWidget);
  });

  testWidgets('mic: a refused microphone says so; cancel drops a recording', (
    tester,
  ) async {
    final h = _Harness(
      recorder: FakeRecorder(startError: const VoiceError(micDeniedText)),
    );
    addTearDown(h.container.dispose);
    await h.open(tester);
    await tester.tap(find.byKey(const Key('mic')));
    await tester.pumpAndSettle();
    expect(find.text(micDeniedText), findsOneWidget);

    h.recorder.startError = null;
    await tester.tap(find.byKey(const Key('mic')));
    await tester.pump();
    await tester.tap(find.byKey(const Key('mic-cancel')));
    await tester.pumpAndSettle();
    expect(h.recorder.cancelled, isTrue);
    expect(find.byKey(const Key('composer')), findsOneWidget);
    expect(h.paths, isNot(contains('/api/voice/transcribe')));
  });

  testWidgets('mic: it stops by itself at two minutes', (tester) async {
    final h = _Harness(
      transcribe: (o) => FakeAdapter.json({'text': 'long one'}),
    );
    addTearDown(h.container.dispose);
    await h.open(tester);
    await tester.tap(find.byKey(const Key('mic')));
    await tester.pump();
    await tester.pump(const Duration(seconds: 120));
    await tester.pumpAndSettle();
    expect(h.paths, contains('/api/voice/transcribe'));
    final field = tester.widget<TextField>(find.byKey(const Key('composer')));
    expect(field.controller!.text, 'long one');
  });

  testWidgets('no mic and no speaker while voice is not running', (
    tester,
  ) async {
    final h = _Harness(available: false);
    addTearDown(h.container.dispose);
    await h.open(tester);
    expect(find.byKey(const Key('mic')), findsNothing);
    expect(find.byKey(const Key('speak-m1')), findsNothing);
  });

  testWidgets(
    'the speaker on a reply plays it at the bot\'s speed; tap stops',
    (tester) async {
      final h = _Harness();
      addTearDown(h.container.dispose);
      await h.open(tester);
      await tester.tap(find.byKey(const Key('speak-m1')));
      await tester.pumpAndSettle();
      expect(h.player.played, [(body: '"spoken"', speed: 1.5)]);
      expect(find.byTooltip('Stop reading'), findsOneWidget);
      await tester.tap(find.byKey(const Key('speak-m1')));
      await tester.pumpAndSettle();
      expect(find.byTooltip('Read aloud'), findsOneWidget);
      expect(h.player.stops, greaterThan(0));
    },
  );

  testWidgets('long-press offers Read aloud on a bot reply', (tester) async {
    final h = _Harness();
    addTearDown(h.container.dispose);
    await h.open(tester);
    await tester.longPress(find.text('13:19').first);
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('menu-read-aloud')));
    await tester.pumpAndSettle();
    expect(h.player.played.single.body, '"spoken"');
  });

  testWidgets('read aloud: a new reply in the open chat plays by itself', (
    tester,
  ) async {
    final h = _Harness();
    addTearDown(h.container.dispose);
    await h.open(tester, readAloud: true);
    expect(h.player.played, isEmpty, reason: 'old messages never play');

    h.frame({
      'type': 'message',
      'thread_id': 't1',
      'message': msg('m2', 'bot', 'Done!', 2),
    });
    await tester.pumpAndSettle();
    expect(h.player.played, [(body: '"spoken"', speed: 1.5)]);
    expect(h.paths, contains('/api/threads/t1/messages/m2/speech'));

    // Another chat's reply, and the same reply again, do not play.
    h.frame({
      'type': 'message',
      'thread_id': 't9',
      'message': msg('x1', 'bot', 'Elsewhere', 1, thread: 't9'),
    });
    h.frame({
      'type': 'message',
      'thread_id': 't1',
      'message': msg('m2', 'bot', 'Done!', 2),
    });
    await tester.pumpAndSettle();
    expect(h.player.played, hasLength(1));
  });

  testWidgets('read aloud: off stays quiet', (tester) async {
    final h = _Harness();
    addTearDown(h.container.dispose);
    await h.open(tester);
    h.frame({
      'type': 'message',
      'thread_id': 't1',
      'message': msg('m2', 'bot', 'One', 2),
    });
    await tester.pumpAndSettle();
    expect(h.player.played, isEmpty);
  });

  testWidgets('read aloud: not while the app is in the background', (
    tester,
  ) async {
    final h = _Harness();
    addTearDown(h.container.dispose);
    await h.open(tester, readAloud: true);
    h.container.read(appVisibleProvider.notifier).state = false;
    h.frame({
      'type': 'message',
      'thread_id': 't1',
      'message': msg('m2', 'bot', 'One', 2),
    });
    await tester.pumpAndSettle();
    expect(h.player.played, isEmpty);
  });

  testWidgets('read aloud: not while another screen is on top', (tester) async {
    final h = _Harness();
    addTearDown(h.container.dispose);
    await h.open(tester, readAloud: true);
    final nav = tester.state<NavigatorState>(find.byType(Navigator));
    nav.push(MaterialPageRoute<void>(builder: (_) => const Scaffold()));
    await tester.pumpAndSettle();
    h.frame({
      'type': 'message',
      'thread_id': 't1',
      'message': msg('m2', 'bot', 'One', 2),
    });
    await tester.pumpAndSettle();
    expect(h.player.played, isEmpty);
  });
}
