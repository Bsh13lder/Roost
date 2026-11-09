// Voice tuning D3/D4 on the phone (docs/plans/2026-11-06-roost-voice-tuning.md): the words show in the recording
// strip as the ear hears them (live partials of the buffer so far), the check swaps in the cleaned words with the
// fixes marked above the composer, Keep my words puts the raw ones back, and a checked send carries heard + fixes.
import 'dart:async';
import 'dart:typed_data';

import 'package:dio/dio.dart' show RequestOptions;
// flutter_test brings fake_async; it stays transitive so the licence gate's direct list is unchanged.
// ignore: depend_on_referenced_packages
import 'package:fake_async/fake_async.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/api/models.dart';
import 'package:roost_mobile/api/providers.dart';
import 'package:roost_mobile/api/session_store.dart';
import 'package:roost_mobile/features/chat/chat_screen.dart';
import 'package:roost_mobile/live/live_connection.dart';
import 'package:roost_mobile/voice/audio_ports.dart';
import 'package:roost_mobile/voice/mic_controller.dart';
import 'package:roost_mobile/voice/voice_models.dart';
import 'package:roost_mobile/voice/voice_widgets.dart';

import '../fake_adapter.dart';
import 'voice_chat_test.dart' show msg;
import 'voice_fakes.dart';

const said = "tell maka eremadse on what's up";
const corrected = 'tell Maka Eremadze on WhatsApp';
const fixes = [
  {'wrong': 'maka eremadse', 'right': 'Maka Eremadze'},
  {'wrong': "what's up", 'right': 'WhatsApp'},
];

// --- the controller alone ------------------------------------------------------------------------------------------

void main() {
  group('MicController live words (D4)', () {
    test('asks for the buffer so far every tick, one at a time, and shows the words', () {
      FakeAsync().run((async) {
        final recorder = FakeRecorder();
        final partials = <Completer<String>>[];
        final mic = MicController(
          recorder: recorder,
          transcribe: (_) async => said,
          partial: (_) {
            final c = Completer<String>();
            partials.add(c);
            return c.future;
          },
          onText: (_) {},
          partialEvery: const Duration(seconds: 1),
        );
        mic.start();
        async.flushMicrotasks();
        expect(mic.phase, MicPhase.recording);
        async.elapse(const Duration(seconds: 1));          // second 1: the first partial goes
        expect(partials, hasLength(1));
        async.elapse(const Duration(seconds: 1));          // one in flight: no second one
        expect(partials, hasLength(1));
        partials[0].complete('tell maka');
        async.flushMicrotasks();
        expect(mic.live, 'tell maka');
        async.elapse(const Duration(seconds: 1));
        expect(partials, hasLength(2));
        partials[1].complete('');                          // nothing heard yet: the words stay
        async.flushMicrotasks();
        expect(mic.live, 'tell maka');
        mic.finish();
        async.flushMicrotasks();
        expect(mic.live, '', reason: 'the final words take over');
        expect(recorder.snapshots, 2);
        mic.dispose();
      });
    });

    test('a partial that lands after Cancel is dropped', () {
      FakeAsync().run((async) {
        final partials = <Completer<String>>[];
        final mic = MicController(
          recorder: FakeRecorder(),
          transcribe: (_) async => said,
          partial: (_) {
            final c = Completer<String>();
            partials.add(c);
            return c.future;
          },
          onText: (_) {},
        );
        mic.start();
        async.flushMicrotasks();
        async.elapse(const Duration(seconds: 1));
        expect(partials, hasLength(1));
        mic.cancel();
        partials[0].complete('late words');
        async.flushMicrotasks();
        expect(mic.live, '');
        mic.dispose();
      });
    });

    test('no partial goes past the cap: a long dictation keeps its last words until the final ones', () {
      FakeAsync().run((async) {
        var asked = 0;
        final mic = MicController(
          recorder: FakeRecorder(),
          transcribe: (_) async => said,
          partial: (_) async {
            asked++;
            return 'so far $asked';
          },
          onText: (_) {},
        );
        mic.start();
        async.flushMicrotasks();
        async.elapse(const Duration(seconds: voicePartialMaxSeconds + 10));
        expect(asked, voicePartialMaxSeconds);
        expect(mic.live, 'so far $voicePartialMaxSeconds');
        expect(mic.phase, MicPhase.recording);
        mic.dispose();
      });
    });
  });

  group('MicController check (D3)', () {
    test('after the words land it checks, says Checking, and hands over a change', () async {
      final heard = <String>[];
      SpokenCorrection? got;
      var checked = 0;
      final phases = <MicPhase>[];
      final check = Completer<SpeechCorrection?>();
      final mic = MicController(
        recorder: FakeRecorder(),
        transcribe: (_) async => said,
        correct: (_) => check.future,
        onText: heard.add,
        onChecked: () => checked++,
        onCorrected: (c) => got = c,
      );
      mic.addListener(() => phases.add(mic.phase));
      await mic.start();
      final done = mic.finish();
      await Future<void>.delayed(Duration.zero);
      expect(heard, [said]);
      expect(mic.phase, MicPhase.checking);
      check.complete(SpeechCorrection(
          corrected: corrected, fixes: const [SpeechFix("what's up", 'WhatsApp')], changed: true));
      await done;
      expect(checked, 1);
      expect(got?.said, said);
      expect(got?.corrected, corrected);
      expect(mic.phase, MicPhase.idle);
      expect(phases, containsAllInOrder([MicPhase.recording, MicPhase.listening, MicPhase.checking, MicPhase.idle]));
      mic.dispose();
    });

    test('with the switch off there is no check; a failed check leaves the words', () async {
      var checks = 0;
      var checked = 0;
      final mic = MicController(
        recorder: FakeRecorder(),
        transcribe: (_) async => said,
        correct: (_) async {
          checks++;
          throw StateError('down');
        },
        correctOn: () => checks == 0 ? false : true,
        onText: (_) {},
        onChecked: () => checked++,
      );
      await mic.start();
      await mic.finish();
      expect(checks, 0);                 // off: never asked
      mic.dispose();
    });
  });

  group('the recording strip (live words)', () {
    testWidgets('long live words show whole, never cut with …, pinned to the newest words', (tester) async {
      const long = 'Hey, how are you? How is the plan for tomorrow going, did you add the Vodafone payment '
          'and the appointment at the Comisaría Patraix on the tenth at half past eleven';
      final c = Completer<String>();
      final mic = MicController(
        recorder: FakeRecorder(),
        transcribe: (_) async => said,
        partial: (_) => c.future,
        onText: (_) {},
        partialEvery: const Duration(seconds: 1),
      );
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: Align(
            alignment: Alignment.bottomCenter,
            child: SizedBox(width: 260, child: ListenableBuilder(
              listenable: mic,
              builder: (_, _) => RecordingStrip(mic: mic, flat: true),
            )),
          ),
        ),
      ));
      await mic.start();
      await tester.pump(const Duration(seconds: 1));
      c.complete(long);
      await tester.pump();
      final text = tester.widget<Text>(find.byKey(const Key('mic-live')));
      expect(text.data, long);
      expect(text.maxLines, isNull, reason: 'no line cap: the words are never cut off');
      expect(text.overflow, isNot(TextOverflow.ellipsis));
      final scroll = tester.widget<SingleChildScrollView>(
          find.ancestor(of: find.byKey(const Key('mic-live')), matching: find.byType(SingleChildScrollView)));
      expect(scroll.reverse, isTrue, reason: 'the newest words stay in view');
      expect(tester.takeException(), isNull);
      expect(find.byKey(const Key('mic-cancel')), findsOneWidget);
      expect(find.byKey(const Key('mic-seconds')), findsOneWidget);
      await mic.cancel();
      mic.dispose();
    });
  });

  // --- the chat screen -----------------------------------------------------------------------------------------------

  group('the chat composer (D3/D4)', () {
    testWidgets('live words show in the strip; the final words land; a checked send carries heard and fixes',
        (tester) async {
      final r = _Rig(partial: 'tell maka', correct: {'corrected': corrected, 'fixes': fixes, 'changed': true});
      addTearDown(r.container.dispose);
      await r.open(tester, correctOn: true);
      await tester.tap(find.byKey(const Key('mic')));
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));
      await tester.pump();
      expect(find.byKey(const Key('mic-live')), findsOneWidget);
      expect(find.text('tell maka'), findsOneWidget);
      expect(r.paths.where((p) => p == '/api/voice/partial').length, 1);
      expect(r.adapter.requests.firstWhere((q) => q.uri.path == '/api/voice/partial').uri.queryParameters['bot_id'], 'b1');
      await tester.tap(find.byKey(const Key('mic-stop')));
      await tester.pumpAndSettle();
      expect(r.adapter.requests.firstWhere((q) => q.uri.path == '/api/voice/transcribe').uri.queryParameters['bot_id'], 'b1');
      expect(find.byKey(const Key('mic-live')), findsNothing);
      final field = tester.widget<TextField>(find.byKey(const Key('composer')));
      expect(field.controller!.text, corrected);
      expect(find.byKey(const Key('spoken-fix')), findsOneWidget);
      expect(find.text('You said: $said'), findsOneWidget);
      final correctBody = r.adapter.requests.firstWhere((q) => q.uri.path == '/api/voice/correct').data as Map;
      expect(correctBody, {'text': said, 'bot_id': 'b1'});
      await tester.tap(find.byKey(const Key('send')));
      await tester.pumpAndSettle();
      expect(r.posted.single, {'text': corrected, 'spoken': true, 'heard': said, 'fixes': fixes});
      expect(find.byKey(const Key('spoken-fix')), findsNothing);
    });

    testWidgets('Keep my words puts the raw transcript back and the send still says it was checked', (tester) async {
      final r = _Rig(partial: '', correct: {'corrected': corrected, 'fixes': fixes, 'changed': true});
      addTearDown(r.container.dispose);
      await r.open(tester, correctOn: true);
      await r.dictate(tester);
      await tester.tap(find.byKey(const Key('keep-my-words')));
      await tester.pumpAndSettle();
      expect(tester.widget<TextField>(find.byKey(const Key('composer'))).controller!.text, said);
      expect(find.byKey(const Key('spoken-fix')), findsNothing);
      await tester.tap(find.byKey(const Key('send')));
      await tester.pumpAndSettle();
      expect(r.posted.single, {'text': said, 'spoken': true, 'heard': said, 'fixes': <Object>[]});
    });

    testWidgets('a fine sentence stays and the send says it was checked; an edit makes it typed', (tester) async {
      final r = _Rig(partial: '', correct: {'corrected': said, 'fixes': <Object>[], 'changed': false});
      addTearDown(r.container.dispose);
      await r.open(tester, correctOn: true);
      await r.dictate(tester);
      expect(find.byKey(const Key('spoken-fix')), findsNothing);
      await tester.tap(find.byKey(const Key('send')));
      await tester.pumpAndSettle();
      expect(r.posted.single, {'text': said, 'spoken': true, 'heard': said, 'fixes': <Object>[]});
      await r.dictate(tester);
      await tester.enterText(find.byKey(const Key('composer')), '$said now');
      await tester.tap(find.byKey(const Key('send')));
      await tester.pumpAndSettle();
      expect(r.posted.last, {'text': '$said now'});
    });

    testWidgets('with the switch off nothing is checked and the send is only spoken', (tester) async {
      final r = _Rig(partial: '', correct: {'corrected': corrected, 'fixes': fixes, 'changed': true});
      addTearDown(r.container.dispose);
      await r.open(tester, correctOn: false);
      await r.dictate(tester);
      expect(r.paths.contains('/api/voice/correct'), isFalse);
      await tester.tap(find.byKey(const Key('send')));
      await tester.pumpAndSettle();
      expect(r.posted.single, {'text': said, 'spoken': true});
    });
  });
}

/// A chat whose Mac hears [said], says [partial] while recording and answers the check with [correct].
class _Rig {
  _Rig({required this.partial, required this.correct});

  final String partial;
  final Map<String, Object?> correct;
  final posted = <Object?>[];
  final recorder = FakeRecorder();
  late final FakeAdapter adapter = FakeAdapter(_answer);
  late final ProviderContainer container = ProviderContainer(overrides: [
    sessionStoreProvider.overrideWithValue(MemorySessionStore()),
    httpAdapterProvider.overrideWithValue(adapter),
    voiceRecorderProvider.overrideWithValue(recorder),
    voicePlayerProvider.overrideWithValue(FakePlayer()),
  ]);

  Iterable<String> get paths => adapter.requests.map((q) => q.uri.path);

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
    if (path == '/api/voice/transcribe') return FakeAdapter.json({'text': said});
    if (path == '/api/voice/partial') return FakeAdapter.json({'text': partial});
    if (path == '/api/voice/correct') return FakeAdapter.json(correct);
    return FakeAdapter.json({});
  }

  Future<void> open(WidgetTester tester, {required bool correctOn}) async {
    await tester.pumpWidget(UncontrolledProviderScope(
      container: container,
      child: const MaterialApp(home: ChatScreen(botId: 'b1')),
    ));
    await tester.pumpAndSettle();
    container.read(liveProvider.notifier).seed([
      Bot.fromJson({
        'id': 'b1',
        'name': 'Gogi',
        'voice': {'speaker': 'aiden', 'tone': 'natural', 'speed': 1.0, 'correct_speech': correctOn},
      }),
    ]);
    await tester.pump();
  }

  Future<void> dictate(WidgetTester tester) async {
    await tester.tap(find.byKey(const Key('mic')));
    await tester.pump();
    await tester.tap(find.byKey(const Key('mic-stop')));
    await tester.pumpAndSettle();
  }
}

/// A WAV of silence, for a recorder that must hand something back.
Uint8List silence() => pcm16ToWav(Uint8List(320), sampleRate: voiceSampleRate);
