import 'package:dio/dio.dart' show RequestOptions;
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/api/providers.dart';
import 'package:roost_mobile/api/session_store.dart';
import 'package:roost_mobile/profile/bot_detail.dart';
import 'package:roost_mobile/voice/audio_ports.dart';
import 'package:roost_mobile/voice/voice_section.dart';

import '../fake_adapter.dart';
import 'voice_fakes.dart';

Map<String, Object?> _bot(Map<String, Object?> voice) => {
  'id': 'b1',
  'name': 'Gogi',
  'voice': voice,
};

class _Section extends ConsumerWidget {
  const _Section();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final bot = ref.watch(botDetailProvider('b1')).valueOrNull;
    return Scaffold(
      body: bot == null
          ? const SizedBox()
          : ListView(children: [VoiceSection(bot: bot)]),
    );
  }
}

void main() {
  late List<Object?> puts;
  late FakePlayer player;
  late FakeAdapter adapter;

  Future<void> pump(WidgetTester tester, {required bool available}) async {
    puts = [];
    player = FakePlayer();
    var voice = <String, Object?>{
      'speaker': 'aiden',
      'tone': 'natural',
      'speed': 1.0,
      'read_aloud': false,
      'correct_english': false,
    };
    adapter = FakeAdapter((RequestOptions o) {
      switch (o.uri.path) {
        case '/api/voice':
          return FakeAdapter.json({
            'available': available,
            'speakers': [
              {'id': 'aiden', 'name': 'Aiden', 'best_in': 'English'},
              {'id': 'sohee', 'name': 'Sohee', 'best_in': 'Korean'},
            ],
            'tones': [
              {'id': 'natural', 'name': 'Natural'},
              {'id': 'calm', 'name': 'Calm'},
            ],
            'speeds': [0.75, 1.0, 1.25],
            'languages': [
              {'id': 'auto', 'name': 'Auto-detect'},
              {'id': 'en', 'name': 'English'},
              {'id': 'es', 'name': 'Spanish'},
            ],
          });
        case '/api/bots/b1/voice':
          puts.add(o.data);
          voice = (o.data as Map).cast<String, Object?>();
          return FakeAdapter.json(_bot(voice));
        case '/api/bots/b1/voice/sample':
          return FakeAdapter.json('sample');
        case '/api/bots/b1':
          return FakeAdapter.json(_bot(voice));
      }
      return FakeAdapter.json({});
    });
    final container = ProviderContainer(
      overrides: [
        sessionStoreProvider.overrideWithValue(MemorySessionStore()),
        httpAdapterProvider.overrideWithValue(adapter),
        voicePlayerProvider.overrideWithValue(player),
      ],
    );
    addTearDown(container.dispose);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: _Section()),
      ),
    );
    await tester.pumpAndSettle();
  }

  testWidgets('shows the voice, tone and speed, and each change PUTs it all', (
    tester,
  ) async {
    await pump(tester, available: true);
    expect(find.text('Aiden · best in English'), findsOneWidget);
    expect(find.text('Natural'), findsOneWidget);
    expect(find.text('1×'), findsOneWidget);
    expect(find.byKey(const Key('voice-off')), findsNothing);

    await tester.tap(find.byKey(const Key('voice-speed')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('voice-choice-1.25')));
    await tester.pumpAndSettle();
    expect(puts.last, {
      'speaker': 'aiden',
      'tone': 'natural',
      'speed': 1.25,
      'read_aloud': false,
      'correct_speech': false,
      'correct_english': false,
      'language': 'auto',
    });
    expect(find.text('1.25×'), findsOneWidget);

    await tester.tap(find.byKey(const Key('voice-speaker')));
    await tester.pumpAndSettle();
    expect(find.text('Best in Korean'), findsOneWidget);
    await tester.tap(find.byKey(const Key('voice-choice-sohee')));
    await tester.pumpAndSettle();
    expect(puts.last, {
      'speaker': 'sohee',
      'tone': 'natural',
      'speed': 1.25,
      'read_aloud': false,
      'correct_speech': false,
      'correct_english': false,
      'language': 'auto',
    });

    await tester.tap(find.byKey(const Key('voice-tone')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('voice-choice-calm')));
    await tester.pumpAndSettle();
    expect((puts.last as Map)['tone'], 'calm');

    await tester.tap(find.byKey(const Key('voice-read-aloud')));
    await tester.pumpAndSettle();
    expect(puts.last, {
      'speaker': 'sohee',
      'tone': 'calm',
      'speed': 1.25,
      'read_aloud': true,
      'correct_speech': false,
      'correct_english': false,
      'language': 'auto',
    });
  });

  testWidgets('I speak: Auto-detect, or a language the ear supports; never Georgian (D2)', (
    tester,
  ) async {
    await pump(tester, available: true);
    expect(find.text('I speak'), findsOneWidget);
    expect(find.text('Auto-detect'), findsOneWidget);
    await tester.tap(find.byKey(const Key('voice-language')));
    await tester.pumpAndSettle();
    expect(find.text('Georgian'), findsNothing);
    await tester.tap(find.byKey(const Key('voice-choice-es')));
    await tester.pumpAndSettle();
    expect((puts.last as Map)['language'], 'es');
    expect(find.text('Spanish'), findsOneWidget);
  });

  testWidgets('Correct what I say is a switch with its hint; on PUTs it with the rest, under both names', (
    tester,
  ) async {
    await pump(tester, available: true);
    expect(find.text('Correct what I say'), findsOneWidget);
    expect(find.textContaining('in any language'), findsOneWidget);
    await tester.tap(find.byKey(const Key('voice-correct-english')));
    await tester.pumpAndSettle();
    expect(puts.last, {
      'speaker': 'aiden',
      'tone': 'natural',
      'speed': 1.0,
      'read_aloud': false,
      'correct_speech': true,
      'correct_english': true,
      'language': 'auto',
    });
    final sw = tester.widget<Switch>(find.byKey(const Key('voice-correct-english')));
    expect(sw.value, isTrue);
  });

  testWidgets('Try it plays the sample in the chosen voice at its speed', (
    tester,
  ) async {
    await pump(tester, available: true);
    await tester.tap(find.byKey(const Key('voice-try')));
    await tester.pumpAndSettle();
    final asked = adapter.requests.lastWhere(
      (r) => r.uri.path == '/api/bots/b1/voice/sample',
    );
    expect(asked.uri.queryParameters, {'speaker': 'aiden', 'tone': 'natural'});
    expect(player.played.single, (body: '"sample"', speed: 1.0));
    expect(find.text('Stop'), findsOneWidget);
    player.finish();
    await tester.pumpAndSettle();
    expect(find.text('Try it'), findsOneWidget);
  });

  testWidgets('voice off: one quiet line and nothing can change', (
    tester,
  ) async {
    await pump(tester, available: false);
    expect(find.text("Voice isn't running on your Mac yet."), findsOneWidget);
    await tester.tap(find.byKey(const Key('voice-speed')));
    await tester.tap(find.byKey(const Key('voice-read-aloud')));
    await tester.tap(find.byKey(const Key('voice-correct-english')));
    await tester.tap(find.byKey(const Key('voice-try')));
    await tester.pumpAndSettle();
    expect(puts, isEmpty);
    expect(player.played, isEmpty);
    expect(find.byKey(const Key('voice-choice-1.25')), findsNothing);
  });
}
