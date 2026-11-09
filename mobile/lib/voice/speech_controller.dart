import 'dart:async';
import 'dart:math';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api_error.dart';
import 'audio_ports.dart';
import 'voice_api.dart';
import 'voice_models.dart';

/// What is being read aloud: one message (or a voice sample) at a time.
@immutable
class SpeechState {
  const SpeechState({this.key, this.loading = false, this.error});

  /// The message id (or sample key) playing or about to play.
  final String? key;

  /// True until the first part has arrived.
  final bool loading;

  /// The last failure's words, until the next play.
  final String? error;
}

/// A live part that 404s after the reply is done is asked for again this
/// often, this many times, before the rest is let go.
const liveRetryDelay = Duration(milliseconds: 400);
const liveRetryMax = 15;

/// Plays a message's parts in order at its bot's speed, fetching the next part
/// while one plays. Playing anything else stops what was playing.
class SpeechController extends Notifier<SpeechState> {
  int _generation = 0;

  @override
  SpeechState build() => const SpeechState();

  VoicePlayer get _player => ref.read(voicePlayerProvider);
  VoiceApi get _api => ref.read(voiceApiProvider);

  bool isPlaying(String key) => state.key == key;

  /// Something is playing or about to.
  bool get busy => state.key != null;

  Future<void> stop() async {
    _generation++;
    state = const SpeechState();
    await _player.stop();
  }

  /// Tap once to hear a bot's reply or Report; tap again to stop.
  Future<void> toggle(String threadId, String messageId) async {
    if (state.key == messageId) return stop();
    return speak(threadId, messageId);
  }

  Future<void> speak(String threadId, String messageId) async {
    final gen = await _begin(messageId);
    Future<Uint8List>? next;
    try {
      final plan = await _api.speechPlan(threadId, messageId);
      if (gen != _generation) return;
      if (plan.parts > 0) next = _api.speechPart(threadId, messageId, 0);
      for (var i = 0; i < plan.parts; i++) {
        final bytes = await next!;
        next = i + 1 < plan.parts ? _api.speechPart(threadId, messageId, i + 1) : null;
        if (gen != _generation) return;
        state = SpeechState(key: messageId);
        await _player.play(bytes, plan.speed);
        if (gen != _generation) return;
      }
    } on ApiException catch (e) {
      _fail(gen, e.message);
    } on VoiceError catch (e) {
      _fail(gen, e.message);
    } finally {
      next?.ignore();
      _end(gen);
    }
  }

  /// A fixed line ("Hi, I'm listening.") in the bot's voice. Quiet when the
  /// gateway has no such line (an older server) or it can't be played.
  Future<void> speakLine(String botId, String key, {double speed = defaultSpeed}) async {
    final stateKey = 'line:$key';
    final gen = await _begin(stateKey);
    try {
      final bytes = await _api.line(botId, key);
      if (bytes == null || gen != _generation) return;
      state = SpeechState(key: stateKey);
      await _player.play(bytes, speed);
    } on ApiException catch (_) {
      // Text notes stand in for the line.
    } on VoiceError catch (_) {
      // Same.
    } finally {
      _end(gen);
    }
  }

  /// A reply spoken as it streams: [events] say how many parts are ready;
  /// each is fetched in order and played whole. A part that 404s is tried
  /// again at the next event. Ends after the done event's last part, or on
  /// [stop].
  Future<void> speakLive(String threadId, String messageId, Stream<LiveSpeechEvent> events) async {
    final gen = await _begin(messageId);
    final live = _LiveParts(events);
    try {
      await _playLive(gen, threadId, messageId, live);
    } on ApiException catch (e) {
      _fail(gen, e.message);
    } on VoiceError catch (e) {
      _fail(gen, e.message);
    } finally {
      live.close();
      _end(gen);
    }
  }

  Future<void> _playLive(int gen, String threadId, String messageId, _LiveParts live) async {
    var next = 0;
    var retries = 0;
    while (gen == _generation) {
      if (next >= live.ready) {
        if (live.done) return;
        await live.change();
        continue;
      }
      final bytes = await _api.liveSpeechPart(threadId, messageId, next);
      if (gen != _generation) return;
      if (bytes == null) {
        if (!live.done) {
          await live.change();
        } else if (retries++ < liveRetryMax) {
          await Future<void>.delayed(liveRetryDelay);
        } else {
          return;
        }
        continue;
      }
      state = SpeechState(key: messageId);
      await _player.play(bytes, live.speed);
      next++;
    }
  }

  /// Try it: one sample line at [speed].
  Future<void> playSample(String key, Future<Uint8List> Function() fetch, double speed) async {
    if (state.key == key) return stop();
    final gen = await _begin(key);
    try {
      final bytes = await fetch();
      if (gen != _generation) return;
      state = SpeechState(key: key);
      await _player.play(bytes, speed);
    } on ApiException catch (e) {
      _fail(gen, e.message);
    } on VoiceError catch (e) {
      _fail(gen, e.message);
    } finally {
      _end(gen);
    }
  }

  Future<int> _begin(String key) async {
    final gen = ++_generation;
    state = SpeechState(key: key, loading: true);
    await _player.stop();
    return gen;
  }

  void _fail(int gen, String message) {
    if (gen == _generation) state = SpeechState(error: message);
  }

  void _end(int gen) {
    if (gen == _generation && state.key != null) {
      state = const SpeechState();
    }
  }
}

/// The latest word on a live reply: parts ready, done, speed; [change]
/// resolves at the next event (or when the stream ends).
class _LiveParts {
  _LiveParts(Stream<LiveSpeechEvent> events) {
    _sub = events.listen(_on, onDone: () {
      done = true;
      _wake();
    });
  }

  late final StreamSubscription<LiveSpeechEvent> _sub;
  Completer<void> _next = Completer<void>();
  int ready = 0;
  bool done = false;
  double speed = defaultSpeed;

  void _on(LiveSpeechEvent e) {
    ready = max(ready, e.ready);
    done = done || e.done;
    if (e.speed != null) speed = e.speed!;
    _wake();
  }

  void _wake() {
    if (!_next.isCompleted) _next.complete();
  }

  Future<void> change() {
    if (_next.isCompleted) _next = Completer<void>();
    return _next.future;
  }

  /// Never awaited: a cancel on a stream that already closed may not settle
  /// until the next frame, and the caller has nothing to wait for.
  void close() => unawaited(_sub.cancel());
}

final speechProvider = NotifierProvider<SpeechController, SpeechState>(
  SpeechController.new,
);
