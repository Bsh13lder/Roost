import 'dart:async';
import 'dart:convert';

import 'package:dio/dio.dart' show RequestOptions;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/api/providers.dart';
import 'package:roost_mobile/api/session_store.dart';
import 'package:roost_mobile/voice/audio_ports.dart';
import 'package:roost_mobile/voice/speech_controller.dart';
import 'package:roost_mobile/voice/voice_api.dart';

import '../fake_adapter.dart';
import 'voice_fakes.dart';

/// The call's routes (shared contract A–C); a 404 means an old gateway.
class _Rig {
  _Rig({this.readyParts = 0});

  bool oldServer = false;
  int readyParts;
  final player = FakePlayer();
  late final FakeAdapter adapter = FakeAdapter(_answer);
  late final ProviderContainer container = ProviderContainer(overrides: [
    sessionStoreProvider.overrideWithValue(MemorySessionStore()),
    httpAdapterProvider.overrideWithValue(adapter),
    voicePlayerProvider.overrideWithValue(player),
  ]);

  VoiceApi get api => container.read(voiceApiProvider);
  SpeechController get speech => container.read(speechProvider.notifier);
  Iterable<RequestOptions> get requests => adapter.requests;

  FakeReply _answer(RequestOptions o) {
    final p = o.uri.path;
    if (p == '/api/voice/warm') return FakeAdapter.json({'ok': true});
    if (oldServer) return FakeAdapter.json({'detail': 'Not Found'}, status: 404);
    if (p == '/api/threads/t1/call') return FakeAdapter.json({'ok': true, 'expires_in': 60});
    if (p == '/api/bots/b1/voice/line/greeting') return FakeAdapter.json('hi-wav');
    if (p.startsWith('/api/bots/b1/voice/line/')) return FakeAdapter.json({'detail': 'no'}, status: 404);
    if (p == '/api/threads/t1/live-speech/r1') {
      return FakeAdapter.json({'parts': readyParts, 'done': readyParts >= 2, 'speed': 1.25});
    }
    final part = RegExp(r'^/api/threads/t1/live-speech/r1/(\d+)$').firstMatch(p);
    if (part != null) {
      final i = int.parse(part.group(1)!);
      return i < readyParts ? FakeAdapter.json('part$i') : FakeAdapter.json({'detail': 'later'}, status: 404);
    }
    return FakeAdapter.json({'detail': 'Not Found'}, status: 404);
  }
}

void main() {
  group('VoiceApi, the call routes', () {
    test('warm carries the bot id as JSON; an empty warm still works', () async {
      final r = _Rig();
      addTearDown(r.container.dispose);
      await r.api.warm(botId: 'b1');
      final sent = r.requests.single;
      expect(sent.uri.path, '/api/voice/warm');
      expect(sent.method, 'POST');
      expect(sent.data, {'bot_id': 'b1'});
      await r.api.warm();
      expect(r.requests.last.data, <String, Object?>{});
    });

    test('a fixed line comes as bytes; an unknown key or an old server is null', () async {
      final r = _Rig();
      addTearDown(r.container.dispose);
      expect(utf8.decode((await r.api.line('b1', 'greeting'))!), '"hi-wav"');
      expect(await r.api.line('b1', 'nope'), isNull);
      r.oldServer = true;
      expect(await r.api.line('b1', 'greeting'), isNull);
    });

    test('the heartbeat posts, with interrupted when you cut in; End deletes; 404s are quiet', () async {
      final r = _Rig();
      addTearDown(r.container.dispose);
      await r.api.callBeat('t1');
      expect(r.requests.last.method, 'POST');
      expect(r.requests.last.uri.path, '/api/threads/t1/call');
      expect(r.requests.last.data, <String, Object?>{});
      await r.api.callBeat('t1', interrupted: 'r1');
      expect(r.requests.last.data, {'interrupted': 'r1'});
      await r.api.callEnd('t1');
      expect(r.requests.last.method, 'DELETE');
      r.oldServer = true;
      await r.api.callBeat('t1');
      await r.api.callEnd('t1');
    });

    test('live speech: the plan, a part, and null for not-yet or an old server', () async {
      final r = _Rig(readyParts: 1);
      addTearDown(r.container.dispose);
      final plan = await r.api.liveSpeech('t1', 'r1');
      expect(plan, (parts: 1, done: false, speed: 1.25));
      expect(utf8.decode((await r.api.liveSpeechPart('t1', 'r1', 0))!), '"part0"');
      expect(await r.api.liveSpeechPart('t1', 'r1', 1), isNull);
      r.oldServer = true;
      expect(await r.api.liveSpeech('t1', 'r1'), isNull);
    });
  });

  group('SpeechController in a call', () {
    test('speakLine plays the bot\'s line once and is quiet on an old server', () async {
      final r = _Rig();
      addTearDown(r.container.dispose);
      final done = r.speech.speakLine('b1', 'greeting');
      await pumpEventQueue();
      expect(r.player.played.map((p) => p.body), ['"hi-wav"']);
      r.player.finish();
      await done;
      expect(r.container.read(speechProvider).key, isNull);
      r.oldServer = true;
      await r.speech.speakLine('b1', 'greeting');
      expect(r.player.played, hasLength(1));
      expect(r.container.read(speechProvider).error, isNull);
    });

    test('speakLive plays parts as they are announced, in order, and ends after done', () async {
      final r = _Rig(readyParts: 1);
      addTearDown(r.container.dispose);
      final events = StreamController<LiveSpeechEvent>();
      final done = r.speech.speakLive('t1', 'r1', events.stream);
      events.add((ready: 1, done: false, speed: 1.25));
      await pumpEventQueue();
      expect(r.player.played, [(body: '"part0"', speed: 1.25)]);
      r.readyParts = 2;
      events.add((ready: 2, done: true, speed: null));
      await pumpEventQueue();
      expect(r.player.played, hasLength(1), reason: 'part 1 waits for part 0 to end');
      r.player.finish();
      await pumpEventQueue();
      expect(r.player.played.last, (body: '"part1"', speed: 1.25));
      r.player.finish();
      await done;
      expect(r.container.read(speechProvider).key, isNull);
    });

    test('a part that 404s is tried again at the next event', () async {
      final r = _Rig(readyParts: 0);
      addTearDown(r.container.dispose);
      final events = StreamController<LiveSpeechEvent>();
      final done = r.speech.speakLive('t1', 'r1', events.stream);
      events.add((ready: 1, done: false, speed: 1.0));
      await pumpEventQueue();
      expect(r.player.played, isEmpty);
      r.readyParts = 1;
      events.add((ready: 1, done: true, speed: null));
      await pumpEventQueue();
      expect(r.player.played.map((p) => p.body), ['"part0"']);
      r.player.finish();
      await done;
    });

    test('stop cuts live speech short', () async {
      final r = _Rig(readyParts: 2);
      addTearDown(r.container.dispose);
      final events = StreamController<LiveSpeechEvent>();
      final done = r.speech.speakLive('t1', 'r1', events.stream);
      events.add((ready: 2, done: true, speed: 1.0));
      await pumpEventQueue();
      expect(r.player.played, hasLength(1));
      await r.speech.stop();
      await done;
      expect(r.player.played, hasLength(1));
    });
  });
}
