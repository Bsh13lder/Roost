import 'dart:async';
import 'dart:typed_data';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/api/models.dart';
import 'package:roost_mobile/api/providers.dart';
import 'package:roost_mobile/api/session_store.dart';
import 'package:roost_mobile/live/bot_frames.dart';
import 'package:roost_mobile/voice/audio_ports.dart';
import 'package:roost_mobile/voice/read_aloud.dart';
import 'package:roost_mobile/voice/speech_controller.dart';
import 'package:roost_mobile/voice/voice_api.dart';
import 'package:roost_mobile/voice/voice_models.dart';

import '../fake_adapter.dart';
import 'voice_fakes.dart';

Message _msg(
  String id, {
  String role = 'bot',
  int seq = 1,
  String kind = 'text',
}) => Message(
  id: id,
  threadId: 't1',
  role: role,
  body: 'hi',
  seq: seq,
  createdAt: '',
  kind: kind,
);

void main() {
  group('a bot\'s voice is read tolerantly', () {
    test('missing voice reads as the defaults', () {
      final bot = Bot.fromJson({'id': 'b1', 'name': 'Gogi'});
      expect(bot.voice, const BotVoice());
      expect(bot.voice.speaker, 'aiden');
      expect(bot.voice.tone, 'natural');
      expect(bot.voice.speed, 1.0);
      expect(bot.voice.readAloud, isFalse);
      expect(bot.voice.correctEnglish, isFalse);
    });

    test('the switch reads from correct_speech, else the old correct_english; an old row without either is false', () {
      expect(BotVoice.fromJson({'correct_english': true}).correctSpeech, isTrue);
      expect(BotVoice.fromJson({'correct_english': true}).correctEnglish, isTrue);
      expect(BotVoice.fromJson({'correct_speech': true}).correctSpeech, isTrue);
      expect(BotVoice.fromJson({'correct_speech': false, 'correct_english': true}).correctSpeech, isFalse);
      expect(BotVoice.fromJson({'correct_english': 'yes'}).correctSpeech, isFalse);
      expect(BotVoice.fromJson({'read_aloud': true}).correctSpeech, isFalse);
      const v = BotVoice();
      expect(v.copyWith(correctSpeech: true), const BotVoice(correctSpeech: true));
      expect(v.copyWith(correctSpeech: true), isNot(v));
      final json = v.copyWith(correctSpeech: true).toJson();
      expect(json['correct_speech'], isTrue);
      expect(json['correct_english'], isTrue, reason: 'an older gateway reads the old name');
    });

    test('the language reads from the row, auto when missing, and rides in copyWith and toJson (D2)', () {
      expect(BotVoice.fromJson({'language': 'es'}).language, 'es');
      expect(BotVoice.fromJson({}).language, voiceLanguageAuto);
      expect(BotVoice.fromJson({'language': 3}).language, voiceLanguageAuto);
      expect(const BotVoice().copyWith(language: 'es').toJson()['language'], 'es');
    });

    test('wrong types fall back field by field', () {
      final v = BotVoice.fromJson({
        'speaker': 3,
        'tone': 'calm',
        'speed': 'fast',
        'read_aloud': 'yes',
      });
      expect(v, const BotVoice(tone: 'calm'));
      expect(BotVoice.fromJson('nonsense'), const BotVoice());
    });

    test(
      'an int speed and read_aloud are kept, and bot_updated carries them',
      () {
        final bots = applyBotFrame({}, {
          'type': 'bot_updated',
          'bot': {
            'id': 'b1',
            'voice': {
              'speaker': 'ryan',
              'tone': 'warm',
              'speed': 2,
              'read_aloud': true,
            },
          },
        });
        final v = bots['b1']!.voice;
        expect(
          v,
          const BotVoice(
            speaker: 'ryan',
            tone: 'warm',
            speed: 2.0,
            readAloud: true,
          ),
        );
        expect(bots['b1']!.withStatus(BotStatus.onIt, null).voice, v);
      },
    );

    test('toJson is the whole object', () {
      expect(const BotVoice(speed: 1.25, readAloud: true).toJson(), {
        'speaker': 'aiden',
        'tone': 'natural',
        'speed': 1.25,
        'read_aloud': true,
        'correct_speech': false,
        'correct_english': false,
        'language': 'auto',
      });
    });
  });

  test('speed and clock labels', () {
    expect(speedLabel(1.0), '1×');
    expect(speedLabel(1.25), '1.25×');
    expect(speedLabel(0.9), '0.9×');
    expect(recordingClock(7), '0:07');
    expect(recordingClock(119), '1:59');
  });

  test('voice info parses and skips broken rows', () {
    final info = VoiceInfo.fromJson({
      'available': true,
      'speakers': [
        {'id': 'aiden', 'name': 'Aiden', 'best_in': 'English'},
        {'name': 'no id'},
        'junk',
      ],
      'tones': [
        {'id': 'calm', 'name': 'Calm'},
      ],
      'speeds': [0.75, 1, 'x'],
    });
    expect(info.available, isTrue);
    expect(info.speakers.single.bestIn, 'English');
    expect(info.toneName('calm'), 'Calm');
    expect(info.speeds, [0.75, 1.0]);
    expect(VoiceInfo.fromJson(null).available, isFalse);
  });

  test('a WAV header around PCM 16-bit mono at 16 kHz', () {
    final wav = pcm16ToWav(Uint8List(32000), sampleRate: 16000);
    final d = ByteData.sublistView(wav);
    expect(String.fromCharCodes(wav.sublist(0, 4)), 'RIFF');
    expect(String.fromCharCodes(wav.sublist(8, 12)), 'WAVE');
    expect(d.getUint16(22, Endian.little), 1); // mono
    expect(d.getUint32(24, Endian.little), 16000);
    expect(d.getUint16(34, Endian.little), 16);
    expect(d.getUint32(40, Endian.little), 32000);
    expect(wav.length, 44 + 32000);
  });

  group('read replies aloud', () {
    test('only a new, finished bot reply or Report counts', () {
      final before = [_msg('m1'), _msg('p', seq: 0)];
      expect(
        newReplyToRead(
          before: before,
          after: [_msg('m1'), _msg('p', seq: 2)],
          alreadyRead: {},
        ),
        'p',
      );
      expect(
        newReplyToRead(
          before: before,
          after: [
            _msg('m1'),
            _msg('u', role: 'user'),
          ],
          alreadyRead: {},
        ),
        isNull,
      );
      expect(
        newReplyToRead(
          before: before,
          after: [
            _msg('m1'),
            _msg('r', kind: 'report'),
          ],
          alreadyRead: {},
        ),
        'r',
      );
      expect(
        newReplyToRead(
          before: before,
          after: [
            _msg('m1'),
            _msg('c', kind: 'approval'),
          ],
          alreadyRead: {},
        ),
        isNull,
      );
      // Replayed after a reconnect: already there.
      expect(
        newReplyToRead(before: before, after: before, alreadyRead: {}),
        isNull,
      );
      expect(
        newReplyToRead(
          before: before,
          after: [_msg('m1'), _msg('p', seq: 2)],
          alreadyRead: {'p'},
        ),
        isNull,
      );
    });

    test('plays only when on, loaded, on top and in front', () {
      expect(
        shouldReadAloud(
          readAloud: true,
          foreground: true,
          onTop: true,
          loaded: true,
        ),
        isTrue,
      );
      expect(
        shouldReadAloud(
          readAloud: false,
          foreground: true,
          onTop: true,
          loaded: true,
        ),
        isFalse,
      );
      expect(
        shouldReadAloud(
          readAloud: true,
          foreground: false,
          onTop: true,
          loaded: true,
        ),
        isFalse,
      );
      expect(
        shouldReadAloud(
          readAloud: true,
          foreground: true,
          onTop: false,
          loaded: true,
        ),
        isFalse,
      );
      expect(
        shouldReadAloud(
          readAloud: true,
          foreground: true,
          onTop: true,
          loaded: false,
        ),
        isFalse,
      );
    });
  });

  group('the speaker', () {
    late FakePlayer player;
    late FakeAdapter adapter;
    late ProviderContainer container;

    setUp(() {
      player = FakePlayer();
      adapter = FakeAdapter(
        (o) => switch (o.path) {
          '/api/threads/t1/messages/m1/speech' => FakeAdapter.json({
            'parts': 2,
            'speed': 1.25,
          }),
          '/api/threads/t1/messages/m1/speech/0' => FakeAdapter.json('part0'),
          '/api/threads/t1/messages/m1/speech/1' => FakeAdapter.json('part1'),
          '/api/threads/t1/messages/m2/speech' => FakeAdapter.json({
            'parts': 1,
            'speed': 1.0,
          }),
          '/api/threads/t1/messages/m2/speech/0' => FakeAdapter.json('other'),
          _ => FakeAdapter.json({'detail': 'nope'}, status: 404),
        },
      );
      container = ProviderContainer(
        overrides: [
          sessionStoreProvider.overrideWithValue(MemorySessionStore()),
          httpAdapterProvider.overrideWithValue(adapter),
          voicePlayerProvider.overrideWithValue(player),
        ],
      );
    });
    tearDown(() => container.dispose());

    test(
      'plays the parts in order at the bot\'s speed, fetching the next ahead',
      () async {
        final speech = container.read(speechProvider.notifier);
        final done = speech.toggle('t1', 'm1');
        await pumpEventQueue();
        expect(player.played, [(body: '"part0"', speed: 1.25)]);
        expect(container.read(speechProvider).key, 'm1');
        // Part 1 was asked for while part 0 plays.
        expect(
          adapter.requests.map((r) => r.path),
          contains('/api/threads/t1/messages/m1/speech/1'),
        );
        player.finish();
        await pumpEventQueue();
        expect(player.played.last, (body: '"part1"', speed: 1.25));
        player.finish();
        await done;
        expect(container.read(speechProvider).key, isNull);
      },
    );

    test('tap again stops; playing another message stops the first', () async {
      final speech = container.read(speechProvider.notifier);
      unawaited(speech.toggle('t1', 'm1'));
      await pumpEventQueue();
      unawaited(speech.toggle('t1', 'm2'));
      await pumpEventQueue();
      expect(container.read(speechProvider).key, 'm2');
      expect(player.played.map((p) => p.body), ['"part0"', '"other"']);

      await speech.toggle('t1', 'm2');
      await pumpEventQueue();
      expect(container.read(speechProvider).key, isNull);
      expect(player.stops, greaterThanOrEqualTo(2));
      expect(player.played.length, 2, reason: 'm1 never went on to part 1');
    });

    test('a failure leaves its words for the snack bar', () async {
      await container.read(speechProvider.notifier).toggle('t1', 'gone');
      expect(container.read(speechProvider).key, isNull);
      expect(container.read(speechProvider).error, "That wasn't found.");
    });
  });

  group('voice is assumed until the server says no', () {
    ProviderContainer make(FakeAdapter adapter) => ProviderContainer(
      overrides: [
        sessionStoreProvider.overrideWithValue(MemorySessionStore()),
        httpAdapterProvider.overrideWithValue(adapter),
      ],
    );

    test('loading reads as available; the server\'s no is final', () async {
      final c = make(FakeAdapter((o) => FakeAdapter.json({'available': false})));
      addTearDown(c.dispose);
      final sub = c.listen(voiceAvailableProvider, (_, _) {});
      expect(c.read(voiceAvailableProvider), isTrue, reason: 'still loading');
      await pumpEventQueue();
      expect(c.read(voiceAvailableProvider), isFalse);
      sub.close();
    });

    test('the server\'s yes', () async {
      final c = make(FakeAdapter((o) => FakeAdapter.json({'available': true})));
      addTearDown(c.dispose);
      final sub = c.listen(voiceAvailableProvider, (_, _) {});
      await pumpEventQueue();
      expect(c.read(voiceAvailableProvider), isTrue);
      sub.close();
    });

    test('no answer at all (a sleeping Mac, a lost tailnet) keeps the Call button', () async {
      final c = make(SwitchAdapter((o) => FakeAdapter.json({}), down: true));
      addTearDown(c.dispose);
      final sub = c.listen(voiceAvailableProvider, (_, _) {});
      await pumpEventQueue();
      expect(c.read(voiceInfoProvider).hasError, isTrue);
      expect(c.read(voiceAvailableProvider), isTrue);
      sub.close();
    });

    test('an old gateway with no voice route (404) means no voice', () async {
      final c = make(FakeAdapter((o) => FakeAdapter.json({'detail': 'no'}, status: 404)));
      addTearDown(c.dispose);
      final sub = c.listen(voiceAvailableProvider, (_, _) {});
      await pumpEventQueue();
      expect(c.read(voiceAvailableProvider), isFalse);
      sub.close();
    });
  });
}
