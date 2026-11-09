import 'dart:convert';

import 'package:dio/dio.dart' show RequestOptions;
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/api/models.dart';
import 'package:roost_mobile/api/providers.dart';
import 'package:roost_mobile/api/session_store.dart';
import 'package:roost_mobile/call/call_mic.dart';
import 'package:roost_mobile/call/call_platform.dart';
import 'package:roost_mobile/features/chat/chat_screen.dart';
import 'package:roost_mobile/live/live_connection.dart';
import 'package:roost_mobile/voice/audio_ports.dart';

import '../fake_adapter.dart';
import '../voice/voice_chat_test.dart' show msg;
import '../voice/voice_fakes.dart';
import 'call_controller_test.dart' show FakeCallMic;

class _Rig {
  _Rig({this.available = true, this.liveServer = false});

  final bool available;

  /// A gateway with the call routes (contract A–C); false is tonight's.
  final bool liveServer;

  /// What the Mac hears you say.
  String heard = 'Add milk to my list';

  /// The bot's voice as `GET /api/bots/b1` tells it.
  Map<String, Object?> botVoice = {'speaker': 'aiden', 'tone': 'natural', 'speed': 1.0, 'read_aloud': false};
  final mic = FakeCallMic();
  final player = FakePlayer();
  final screenOn = <bool>[];
  final speaker = <bool>[];
  late final FakeAdapter adapter = FakeAdapter(_answer);
  late final ProviderContainer container = ProviderContainer(overrides: [
    sessionStoreProvider.overrideWithValue(MemorySessionStore()),
    httpAdapterProvider.overrideWithValue(adapter),
    voiceRecorderProvider.overrideWithValue(FakeRecorder()),
    voicePlayerProvider.overrideWithValue(player),
    callMicProvider.overrideWithValue(mic),
    keepScreenOnProvider.overrideWithValue((on) async => screenOn.add(on)),
    speakerphoneProvider.overrideWithValue((on) async => speaker.add(on)),
  ]);

  FakeReply _answer(RequestOptions o) {
    final path = o.uri.path;
    final notFound = FakeAdapter.json({'detail': 'Not Found'}, status: 404);
    return switch (path) {
      '/api/voice' => FakeAdapter.json({'available': available, 'speakers': [], 'tones': [], 'speeds': [1.0]}),
      '/api/bots/b1/chat' => FakeAdapter.json({'id': 't1', 'bot_id': 'b1'}),
      '/api/threads/t1/messages' when o.method == 'GET' => FakeAdapter.json([msg('m1', 'bot', 'Hello there', 1)]),
      '/api/threads/t1/messages' => FakeAdapter.json({'message_id': 'u2', 'status': 'started'}),
      '/api/voice/transcribe' => FakeAdapter.json({'text': heard}),
      '/api/voice/warm' => FakeAdapter.json({'ok': true}),
      '/api/threads/t1/call' => liveServer ? FakeAdapter.json({'ok': true}) : notFound,
      '/api/bots/b1/voice/line/greeting' => liveServer ? FakeAdapter.json('hi') : notFound,
      '/api/bots/b1/voice/line/bye' => liveServer ? FakeAdapter.json('bye') : notFound,
      '/api/bots/b1' => FakeAdapter.json({'id': 'b1', 'name': 'Gogi', 'voice': botVoice}),
      '/api/threads/t1/live-speech/r2' => liveServer ? FakeAdapter.json({'parts': 1, 'done': true, 'speed': 1.0}) : notFound,
      '/api/threads/t1/live-speech/r2/0' => liveServer ? FakeAdapter.json('live0') : notFound,
      '/api/threads/t1/messages/r2/speech' => FakeAdapter.json({'parts': 1, 'speed': 1.0}),
      '/api/threads/t1/messages/r2/speech/0' => FakeAdapter.json('spoken'),
      _ => notFound,
    };
  }

  Iterable<String> get posts => adapter.requests.where((r) => r.method == 'POST').map((r) => r.uri.path);
  Iterable<String> get gets => adapter.requests.where((r) => r.method == 'GET').map((r) => r.uri.path);

  Future<void> open(WidgetTester tester) async {
    await tester.pumpWidget(UncontrolledProviderScope(
      container: container,
      child: const MaterialApp(home: ChatScreen(botId: 'b1')),
    ));
    await tester.pumpAndSettle();
    container.read(liveProvider.notifier).seed([Bot.fromJson({'id': 'b1', 'name': 'Gogi'})]);
    await tester.pumpAndSettle();
  }

  void frame(Map<String, Object?> f) => container.read(frameBusProvider).add(f);
}

Future<void> settle(WidgetTester tester) async {
  for (var i = 0; i < 20; i++) {
    await tester.pump(const Duration(milliseconds: 50));
  }
}

void main() {
  testWidgets('an empty box shows Call; typing turns it into Send', (tester) async {
    final r = _Rig();
    addTearDown(r.container.dispose);
    await r.open(tester);
    expect(find.byKey(const Key('call')), findsOneWidget);
    expect(find.text('Ask Gogi'), findsOneWidget);
    await tester.enterText(find.byKey(const Key('composer')), 'Hi');
    await tester.pump();
    expect(find.byKey(const Key('call')), findsNothing);
    expect(find.byKey(const Key('send')), findsOneWidget);
    final asked = r.gets.where((p) => p == '/api/voice').length;
    await tester.enterText(find.byKey(const Key('composer')), '');
    await tester.pumpAndSettle();
    expect(r.gets.where((p) => p == '/api/voice').length, asked + 1, reason: 'asked again as the box empties');
  });

  testWidgets('no Call while voice is off on the Mac', (tester) async {
    final r = _Rig(available: false);
    addTearDown(r.container.dispose);
    await r.open(tester);
    expect(find.byKey(const Key('call')), findsNothing);
  });

  testWidgets('a call on tonight\'s gateway: warm up, hear you, send it, speak the stored reply, end',
      (tester) async {
    final r = _Rig();
    addTearDown(r.container.dispose);
    await r.open(tester);
    await tester.tap(find.byKey(const Key('call')));
    await settle(tester);
    expect(find.byKey(const Key('call-screen')), findsOneWidget);
    expect(r.posts, contains('/api/voice/warm'));
    expect(r.posts, contains('/api/threads/t1/call'));
    expect(r.screenOn, [true]);
    expect(r.speaker, [true]);
    expect(find.text('Listening'), findsOneWidget);

    r.mic.push();
    await settle(tester);
    expect(r.posts, contains('/api/voice/transcribe'));
    final sent = r.adapter.requests.lastWhere((q) => q.uri.path == '/api/threads/t1/messages' && q.method == 'POST');
    expect(sent.data, {'text': 'Add milk to my list', 'call': true, 'spoken': true});
    expect(find.text('“Add milk to my list”'), findsOneWidget);
    expect(find.text('Thinking…'), findsOneWidget);

    r.frame({'type': 'message', 'thread_id': 't1', 'message': msg('r2', 'bot', 'Added milk.', 3)});
    await settle(tester);
    expect(find.text('Speaking'), findsOneWidget);
    expect(find.text('Added milk.'), findsWidgets);
    expect(r.player.played.map((p) => p.body), ['"spoken"']);
    r.player.finish();
    await settle(tester);
    expect(find.text('Listening'), findsOneWidget);

    await tester.tap(find.byKey(const Key('call-mute')));
    await settle(tester);
    expect(find.text('Muted'), findsOneWidget);
    await tester.tap(find.byKey(const Key('call-speaker')));
    await tester.pump();
    expect(r.speaker, [true, false]);

    await tester.tap(find.byKey(const Key('call-end')));
    await settle(tester);
    expect(find.byKey(const Key('call-screen')), findsNothing);
    expect(r.mic.closed, isTrue);
    expect(r.screenOn, [true, false]);
    expect(r.adapter.requests.where((q) => q.method == 'DELETE').map((q) => q.uri.path), ['/api/threads/t1/call']);
    expect(find.text('Added milk.'), findsOneWidget); // the reply stays in the chat
  });

  testWidgets('a call on a gateway with live speech: the greeting, then the reply spoken as it streams',
      (tester) async {
    final r = _Rig(liveServer: true);
    addTearDown(r.container.dispose);
    await r.open(tester);
    await tester.tap(find.byKey(const Key('call')));
    await settle(tester);
    expect(r.player.played.map((p) => p.body), ['"hi"']);
    r.player.finish();
    await settle(tester);

    r.mic.push();
    await settle(tester);
    expect(find.text('Thinking…'), findsOneWidget);
    r.frame({'type': 'message', 'thread_id': 't1', 'message': msg('r2', 'bot', '', 0)});
    r.frame({'type': 'text_delta', 'thread_id': 't1', 'message_id': 'r2', 'delta': 'On it: adding.\nMilk is on.'});
    await tester.pump();
    expect(find.text('Milk is on.'), findsOneWidget);
    r.frame({'type': 'speech_ready', 'thread_id': 't1', 'message_id': 'r2', 'part': 0, 'done': true});
    await settle(tester);
    expect(find.text('Speaking'), findsOneWidget);
    expect(r.player.played.map((p) => p.body), ['"hi"', '"live0"']);
    r.frame({'type': 'message_done', 'thread_id': 't1', 'message_id': 'r2'});
    r.frame({'type': 'message', 'thread_id': 't1', 'message': msg('r2', 'bot', 'On it: adding.\nMilk is on.', 3)});
    r.player.finish();
    await settle(tester);
    expect(find.text('Listening'), findsOneWidget);
    expect(r.gets, isNot(contains('/api/threads/t1/messages/r2/speech')), reason: 'never also the stored reply');
    await tester.tap(find.byKey(const Key('call-end')));
    await settle(tester);
    expect(find.byKey(const Key('call-screen')), findsNothing);
  });

  testWidgets('the corrected copy of your words takes the plain caption\'s place on the call screen', (tester) async {
    final r = _Rig();
    addTearDown(r.container.dispose);
    await r.open(tester);
    await tester.tap(find.byKey(const Key('call')));
    await settle(tester);
    r.mic.push();
    await settle(tester);
    expect(find.text('“Add milk to my list”'), findsOneWidget);
    r.frame({'type': 'message', 'thread_id': 't1', 'message': msg('u2', 'user', 'Add milk to my list', 2)});
    r.frame({
      'type': 'message',
      'thread_id': 't1',
      'message': {
        ...msg('f1', 'activity', '', 3),
        'kind': 'english_fix',
        'body': jsonEncode({
          'message_id': 'u2',
          'said': 'Add milk to my list',
          'corrected': 'Add milk to my list, please',
          'fixes': [
            {'wrong': 'list', 'right': 'list, please'},
          ],
        }),
      },
    });
    await settle(tester);
    expect(find.text('“Add milk to my list”'), findsNothing);
    expect(find.byKey(const Key('call-heard-fix')), findsOneWidget);
    expect(find.byKey(const Key('english-fix-sentence')), findsOneWidget);
    expect(find.text('Thinking…'), findsOneWidget, reason: 'the line is never spoken or treated as a reply');
    await tester.tap(find.byKey(const Key('call-end')));
    await settle(tester);
  });

  testWidgets('a bot_updated frame mid-call changes the speed its fixed lines play at', (tester) async {
    final r = _Rig(liveServer: true)..heard = 'bye';
    addTearDown(r.container.dispose);
    await r.open(tester);
    await tester.tap(find.byKey(const Key('call')));
    await settle(tester);
    expect(r.player.played.map((p) => (p.body, p.speed)), [('"hi"', 1.0)]);
    r.player.finish();
    await settle(tester);
    r.botVoice = {...r.botVoice, 'speed': 1.5};
    r.frame({'type': 'bot_updated', 'bot': {'id': 'b1', 'name': 'Gogi', 'voice': r.botVoice}});
    await settle(tester);
    r.mic.push();
    await settle(tester);
    r.player.finish();
    await settle(tester);
    expect(r.player.played.map((p) => (p.body, p.speed)), [('"hi"', 1.0), ('"bye"', 1.5)]);
    expect(find.byKey(const Key('call-screen')), findsNothing);
  });
}
