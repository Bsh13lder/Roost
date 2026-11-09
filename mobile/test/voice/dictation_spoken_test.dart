import 'package:dio/dio.dart' show RequestOptions;
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/api/providers.dart';
import 'package:roost_mobile/api/session_store.dart';
import 'package:roost_mobile/features/chat/chat_screen.dart';
import 'package:roost_mobile/voice/audio_ports.dart';

import '../fake_adapter.dart';
import 'voice_chat_test.dart' show msg;
import 'voice_fakes.dart';

/// A chat whose Mac hears [heard]; every POST of a message is kept.
class _Rig {
  _Rig();

  final heard = 'book the flight';
  final posted = <Object?>[];
  late final FakeAdapter adapter = FakeAdapter(_answer);
  late final ProviderContainer container = ProviderContainer(overrides: [
    sessionStoreProvider.overrideWithValue(MemorySessionStore()),
    httpAdapterProvider.overrideWithValue(adapter),
    voiceRecorderProvider.overrideWithValue(FakeRecorder()),
    voicePlayerProvider.overrideWithValue(FakePlayer()),
  ]);

  FakeReply _answer(RequestOptions o) {
    final path = o.uri.path;
    if (path == '/api/voice') {
      return FakeAdapter.json({'available': true, 'speakers': [], 'tones': [], 'speeds': [1.0]});
    }
    if (path == '/api/bots/b1/chat') return FakeAdapter.json({'id': 't1', 'bot_id': 'b1'});
    if (path == '/api/threads/t1/messages' && o.method == 'GET') {
      return FakeAdapter.json([msg('m1', 'bot', 'Hello there', 1)]);
    }
    if (path == '/api/threads/t1/messages' && o.method == 'POST') {
      posted.add(o.data);
      return FakeAdapter.json({'message_id': 'u${posted.length}', 'status': 'started'});
    }
    if (path == '/api/voice/transcribe') return FakeAdapter.json({'text': heard});
    return FakeAdapter.json({});
  }

  Future<void> open(WidgetTester tester) async {
    await tester.pumpWidget(UncontrolledProviderScope(
      container: container,
      child: const MaterialApp(home: ChatScreen(botId: 'b1')),
    ));
    await tester.pumpAndSettle();
  }

  Future<void> dictate(WidgetTester tester) async {
    await tester.tap(find.byKey(const Key('mic')));
    await tester.pump();
    await tester.tap(find.byKey(const Key('mic-stop')));
    await tester.pumpAndSettle();
  }

  Future<void> send(WidgetTester tester) async {
    await tester.tap(find.byKey(const Key('send')));
    await tester.pumpAndSettle();
  }
}

void main() {
  testWidgets('a dictated message sent as it was heard is spoken', (tester) async {
    final r = _Rig();
    addTearDown(r.container.dispose);
    await r.open(tester);
    await r.dictate(tester);
    expect(tester.widget<TextField>(find.byKey(const Key('composer'))).controller!.text, 'book the flight');
    await r.send(tester);
    expect(r.posted, [
      {'text': 'book the flight', 'spoken': true},
    ]);
  });

  testWidgets('two dictations in a row are still your spoken words', (tester) async {
    final r = _Rig();
    addTearDown(r.container.dispose);
    await r.open(tester);
    await r.dictate(tester);
    await r.dictate(tester);
    await r.send(tester);
    expect(r.posted, [
      {'text': 'book the flight book the flight', 'spoken': true},
    ]);
  });

  testWidgets('a keystroke after the dictation makes it an ordinary typed message', (tester) async {
    final r = _Rig();
    addTearDown(r.container.dispose);
    await r.open(tester);
    await r.dictate(tester);
    await tester.enterText(find.byKey(const Key('composer')), 'book the flight today');
    await tester.pump();
    await r.send(tester);
    expect(r.posted, [
      {'text': 'book the flight today'},
    ]);
  });

  testWidgets('dictation added to typed words is not spoken, and the flag does not outlive a send', (tester) async {
    final r = _Rig();
    addTearDown(r.container.dispose);
    await r.open(tester);
    await tester.enterText(find.byKey(const Key('composer')), 'Please');
    await tester.pump();
    await r.dictate(tester);
    await r.send(tester);
    await tester.enterText(find.byKey(const Key('composer')), 'typed');
    await tester.pump();
    await r.send(tester);
    expect(r.posted, [
      {'text': 'Please book the flight'},
      {'text': 'typed'},
    ]);
  });
}
