import 'dart:async';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/api/api_error.dart';
import 'package:roost_mobile/api/models.dart';
import 'package:roost_mobile/call/call_controller.dart';
import 'package:roost_mobile/call/call_mic.dart';
import 'package:roost_mobile/call/call_timing.dart';
import 'package:roost_mobile/features/chat/chat_controller.dart' show queuedNotice;
import 'package:roost_mobile/live/bot_frames.dart';
import 'package:roost_mobile/voice/audio_ports.dart';
import 'package:roost_mobile/voice/voice_api.dart';
import 'package:roost_mobile/voice/voice_models.dart';

import 'endpointer_test.dart' show tone, quiet;

class FakeCallMic implements CallMic {
  FakeCallMic({this.openError});
  Object? openError;
  StreamController<Uint8List>? _chunks;
  int opens = 0;
  int closes = 0;
  bool _parked = false;

  bool get closed => closes > 0 && closes >= opens;

  @override
  bool get supported => true;

  @override
  Future<Stream<Uint8List>> open() async {
    if (openError != null) throw openError!;
    opens++;
    _parked = false;
    _chunks = StreamController<Uint8List>();
    return _chunks!.stream;
  }

  @override
  Future<void> close() async {
    closes++;
    unawaited(_chunks?.close());
  }

  /// Android gave the mic's focus away: the stream stays open but silent.
  void pauseOnFocusLoss() => _parked = true;

  /// Speech then a pause, in 100 ms chunks.
  Future<void> say({int ms = 1000}) async {
    push(ms: ms);
    await pumpEventQueue();
  }

  /// The same without waiting (a widget test pumps instead).
  void push({int ms = 1000}) => _add([...quiet(300), ...tone(ms), ...quiet(1200)]);

  /// Speech with no pause after it (you are still talking).
  void pushVoice({int ms = 600}) => _add([...quiet(300), ...tone(ms)]);

  /// Only room noise, [ms] of it.
  void pushQuiet({int ms = 300}) => _add(quiet(ms));

  void _add(List<int> all) {
    if (_parked) return;
    for (var at = 0; at < all.length; at += 3200) {
      _chunks!.add(Uint8List.fromList(all.sublist(at, (at + 3200).clamp(0, all.length))));
    }
  }
}

Message msg(String id, String role, {String kind = 'text', int seq = 1, String body = 'Sure.'}) =>
    Message(id: id, threadId: 't1', role: role, body: body, seq: seq, createdAt: '', kind: kind);

/// Test timing: nothing fires by itself unless a test asks for it.
const quietTiming = CallTiming(
  heartbeat: Duration(seconds: 30),
  micStall: Duration(seconds: 30),
  speakerTail: Duration(milliseconds: 1),
  hearing: Duration(seconds: 30),
  thinking: Duration(seconds: 30),
  stillOnItAfter: Duration(seconds: 30),
  stillOnItEvery: Duration(seconds: 30),
  livePoll: Duration(milliseconds: 15),
  liveStall: Duration(seconds: 30),
);

Future<void> wait(int ms) => Future<void>.delayed(Duration(milliseconds: ms));

class Rig {
  Rig({
    this.heard = 'Add milk',
    this.warmError,
    FakeCallMic? mic,
    this.timing = quietTiming,
    this.botName = 'Gogi',
  }) : mic = mic ?? FakeCallMic() {
    addTearDown(call.dispose);
  }

  final FakeCallMic mic;
  final CallTiming timing;
  final String botName;
  String heard;
  Object? warmError;

  /// When set, warm waits for it.
  Completer<void>? warmGate;

  /// When set, transcribe never answers (it waits on this).
  Completer<String>? transcribeGate;
  Object? transcribeError;
  SendStatus sendStatus = SendStatus.started;
  Object? sendError;
  LiveSpeechPlan? livePlan;

  final transcribed = <Uint8List>[];
  final sent = <String>[];
  final spoken = <String>[];
  final lines = <String>[];
  final beats = <String?>[];
  final live = <(String, String)>[];
  final liveEvents = <LiveSpeechEvent>[];
  int ends = 0;
  int stops = 0;
  int haptics = 0;
  Completer<void> speaking = Completer<void>();
  Completer<void> liveSpeaking = Completer<void>();
  final frames = StreamController<Frame>.broadcast();

  late final CallController call = CallController(
    mic: mic,
    warm: () async {
      if (warmGate != null) await warmGate!.future;
      if (warmError != null) throw warmError!;
    },
    transcribe: (wav) async {
      transcribed.add(wav);
      if (transcribeError != null) throw transcribeError!;
      if (transcribeGate != null) return transcribeGate!.future;
      return heard;
    },
    send: (text) async {
      if (sendError != null) throw sendError!;
      sent.add(text);
      return sendStatus;
    },
    speak: (m) {
      spoken.add(m.id);
      speaking = Completer<void>();
      return speaking.future;
    },
    speakLive: (threadId, messageId, events) {
      live.add((threadId, messageId));
      events.listen(liveEvents.add);
      liveSpeaking = Completer<void>();
      return liveSpeaking.future;
    },
    speakLine: (key) async => lines.add(key),
    stopSpeaking: () async {
      stops++;
      if (!speaking.isCompleted) speaking.complete();
      if (!liveSpeaking.isCompleted) liveSpeaking.complete();
    },
    beat: ({String? interrupted}) async => beats.add(interrupted),
    endCall: () async => ends++,
    frames: frames.stream,
    liveSpeech: (threadId, messageId) async => livePlan,
    haptic: () async => haptics++,
    botName: botName,
    timing: timing,
  );

  void chat(List<Message> messages, BotStatus? status, {String? activity, Map<String, String> streaming = const {}}) =>
      call.chatChanged(messages, status, activity: activity, streaming: streaming);

  /// Start, let warm resolve and the greeting play.
  Future<void> up() async {
    await call.start();
    await pumpEventQueue();
    chat([msg('old', 'bot')], BotStatus.resting);
  }

  /// One heard turn, sent; the bot is now thinking.
  Future<void> turn() async {
    await mic.say();
    await pumpEventQueue();
  }
}

void main() {
  group('starting', () {
    test('the mic opens before the voice is warm, then the greeting plays once', () async {
      final r = Rig()..warmGate = Completer();
      final started = r.call.start();
      await pumpEventQueue();
      expect(r.call.phase, CallPhase.listening);
      expect(r.call.note, warmingNote);
      expect(r.mic.opens, 1);
      expect(r.lines, isEmpty);
      r.warmGate!.complete();
      await started;
      await pumpEventQueue();
      expect(r.call.note, isNull);
      expect(r.lines, ['greeting']);
      expect(r.beats, [null], reason: 'the call is registered at open');
    });

    test('a turn heard before warm resolves is transcribed after it', () async {
      final r = Rig()..warmGate = Completer();
      unawaited(r.call.start());
      await pumpEventQueue();
      await r.mic.say();
      expect(r.call.phase, CallPhase.hearing);
      expect(r.transcribed, isEmpty);
      r.warmGate!.complete();
      await pumpEventQueue();
      expect(r.transcribed, hasLength(1));
      expect(r.sent, ['Add milk']);
      expect(r.lines, isEmpty, reason: 'no greeting in the middle of your turn');
    });

    test('voice off on the Mac says so and closes the mic', () async {
      final r = Rig(warmError: const ApiException(voiceOffText, status: 503));
      await r.call.start();
      await pumpEventQueue();
      expect(r.call.phase, CallPhase.off);
      expect(r.call.error, voiceOffText);
      expect(r.mic.closed, isTrue);
    });

    test('any other warm trouble is waited out quietly', () async {
      final r = Rig(warmError: const ApiException('Slow.', status: 502));
      await r.call.start();
      await pumpEventQueue();
      expect(r.call.phase, CallPhase.listening);
      expect(r.call.note, isNull);
    });

    test('a mic that is refused says so', () async {
      final r = Rig(mic: FakeCallMic(openError: const VoiceError(micDeniedText)));
      await r.call.start();
      expect(r.call.phase, CallPhase.off);
      expect(r.call.error, micDeniedText);
    });
  });

  group('a turn', () {
    test('what you say is heard and sent as your message', () async {
      final r = Rig();
      await r.up();
      await r.turn();
      expect(r.transcribed, hasLength(1));
      expect(String.fromCharCodes(r.transcribed.single.sublist(0, 4)), 'RIFF');
      expect(r.sent, ['Add milk']);
      expect(r.call.heard, 'Add milk');
      expect(r.call.phase, CallPhase.thinking);
    });

    test('nothing heard: the not_caught line, and listening again', () async {
      final r = Rig(heard: '  ');
      await r.up();
      await r.turn();
      expect(r.sent, isEmpty);
      expect(r.call.phase, CallPhase.listening);
      expect(r.call.note, nothingCaughtText);
      expect(r.lines.last, 'not_caught');
    });

    test('a transcribe failure: say_again, with the words as a note', () async {
      final r = Rig();
      await r.up();
      r.transcribeError = const ApiException('Voice hiccup.');
      await r.turn();
      expect(r.call.phase, CallPhase.listening);
      expect(r.call.note, 'Voice hiccup.');
      expect(r.lines.last, 'say_again');
    });

    test('hearing that takes too long: say_again', () async {
      final r = Rig(timing: quietTiming.copyWith(hearing: const Duration(milliseconds: 30)));
      await r.up();
      r.transcribeGate = Completer();
      await r.turn();
      expect(r.call.phase, CallPhase.hearing);
      await wait(80);
      expect(r.call.phase, CallPhase.listening);
      expect(r.lines.last, 'say_again');
    });

    test('queued: the quiet line, and it keeps waiting', () async {
      final r = Rig()..sendStatus = SendStatus.queued;
      await r.up();
      await r.turn();
      expect(r.call.phase, CallPhase.thinking);
      expect(r.call.note, queuedNotice);
    });

    test('a send that fails: its words, and listening again', () async {
      final r = Rig()..sendError = const ApiException("Can't reach Roost.");
      await r.up();
      await r.turn();
      expect(r.sent, isEmpty);
      expect(r.call.phase, CallPhase.listening);
      expect(r.call.note, "Can't reach Roost.");
    });

    test('tapping the orb while you talk sends now', () async {
      final r = Rig();
      await r.up();
      r.mic.pushVoice(ms: 600);
      await pumpEventQueue();
      expect(r.transcribed, isEmpty);
      await r.call.orbTapped();
      await pumpEventQueue();
      expect(r.transcribed, hasLength(1));
      expect(r.sent, ['Add milk']);
    });

    test('the mic is ignored while it thinks or speaks, and while muted', () async {
      final r = Rig();
      await r.up();
      r.call.toggleMute();
      expect(r.call.muted, isTrue);
      await r.turn();
      expect(r.transcribed, isEmpty);
      r.call.toggleMute();
      await r.turn();
      expect(r.call.phase, CallPhase.thinking);
      await r.turn();
      expect(r.transcribed, hasLength(1));
    });
  });

  group('the bot\'s answer', () {
    test('the stored reply is spoken once its run is over, then it listens again after the tail', () async {
      final r = Rig(timing: quietTiming.copyWith(speakerTail: const Duration(milliseconds: 40)));
      await r.up();
      await r.turn();
      final all = [msg('old', 'bot'), msg('u1', 'user'), msg('r1', 'bot', body: 'On it: adding.\nDone!')];
      r.chat(all, BotStatus.onIt);
      expect(r.call.phase, CallPhase.thinking);
      r.chat(all, BotStatus.resting);
      expect(r.call.phase, CallPhase.speaking);
      expect(r.spoken, ['r1']);
      expect(r.call.saying, 'Done!');
      r.speaking.complete();
      await pumpEventQueue();
      expect(r.call.phase, CallPhase.speaking, reason: 'the speaker tail');
      await wait(80);
      expect(r.call.phase, CallPhase.listening);
      r.chat(all, BotStatus.resting);
      expect(r.spoken, ['r1']);
    });

    test('a run that ends with no words says so', () async {
      final r = Rig();
      await r.up();
      await r.turn();
      r.chat([msg('old', 'bot'), msg('u1', 'user'), msg('p', 'bot', seq: 0)], BotStatus.onIt);
      r.chat([msg('old', 'bot'), msg('u1', 'user')], BotStatus.resting);
      expect(r.call.phase, CallPhase.listening);
      expect(r.call.note, 'Gogi worked and said nothing.');
    });

    test('resting before the run even started is not an answer', () async {
      final r = Rig();
      await r.up();
      await r.turn();
      r.chat([msg('old', 'bot'), msg('u1', 'user')], BotStatus.resting);
      expect(r.call.phase, CallPhase.thinking);
    });

    test('a card-only reply: asking, with the asking line', () async {
      final r = Rig();
      await r.up();
      await r.turn();
      r.chat([msg('old', 'bot'), msg('p', 'bot', seq: 0), msg('a', 'bot', kind: 'approval')], BotStatus.askingYou);
      expect(r.spoken, isEmpty);
      expect(r.call.phase, CallPhase.asking);
      expect(r.lines.last, 'asking');
      await r.turn();
      expect(r.sent, hasLength(2));
      expect(r.call.phase, CallPhase.thinking);
    });

    test('thinking that takes too long gives the call back', () async {
      final r = Rig(timing: quietTiming.copyWith(thinking: const Duration(milliseconds: 30)));
      await r.up();
      await r.turn();
      await wait(80);
      expect(r.call.phase, CallPhase.listening);
      expect(r.call.note, thinkingTooLongNote('Gogi'));
    });

    test('the status word while thinking is the bot\'s activity', () async {
      final r = Rig();
      await r.up();
      await r.turn();
      r.chat([msg('old', 'bot')], BotStatus.onIt, activity: 'checking your list.');
      expect(r.call.activity, 'checking your list.');
    });
  });

  group('keeping the mic alive', () {
    test('a parked mic is opened again once; a second stall says so', () async {
      final r = Rig(timing: quietTiming.copyWith(micStall: const Duration(milliseconds: 50)));
      await r.up();
      r.mic.pauseOnFocusLoss();
      await wait(75);
      expect(r.mic.opens, 2);
      expect(r.call.note, isNull);
      await r.turn();
      expect(r.transcribed, hasLength(1));
      r.chat([msg('old', 'bot'), msg('r1', 'bot')], BotStatus.resting);
      r.speaking.complete();
      await pumpEventQueue();
      await wait(10);
      r.mic.pauseOnFocusLoss();
      await wait(130);
      expect(r.mic.opens, 2);
      expect(r.call.note, micStoppedNote);
    });

    test('the heartbeat beats while the call is up and End deletes it', () async {
      final r = Rig(timing: quietTiming.copyWith(heartbeat: const Duration(milliseconds: 20)));
      await r.up();
      await wait(70);
      expect(r.beats.length, greaterThanOrEqualTo(3));
      await r.call.end();
      expect(r.ends, 1);
      final n = r.beats.length;
      await wait(50);
      expect(r.beats.length, n);
    });

    test('pausing the app mutes with a note; resuming unmutes', () async {
      final r = Rig();
      await r.up();
      r.call.pause();
      expect(r.call.muted, isTrue);
      expect(r.call.note, pausedNote);
      r.call.resume();
      expect(r.call.muted, isFalse);
      expect(r.call.note, isNull);
    });

    test('a mute you chose survives a pause and resume', () async {
      final r = Rig();
      await r.up();
      r.call.toggleMute();
      r.call.pause();
      r.call.resume();
      expect(r.call.muted, isTrue);
    });
  });

  test('a reply that could not be played says why', () async {
    final r = Rig();
    await r.up();
    r.call.speechFailed('No sound.');
    expect(r.call.note, 'No sound.');
  });

  test('ending closes the mic, stops speaking and tells the server', () async {
    final r = Rig();
    await r.up();
    await r.call.end();
    expect(r.mic.closed, isTrue);
    expect(r.stops, 1);
    expect(r.ends, 1);
    expect(r.call.phase, CallPhase.ended);
  });
}
