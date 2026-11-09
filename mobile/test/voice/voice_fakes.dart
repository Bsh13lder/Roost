import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:roost_mobile/voice/audio_ports.dart';

/// A recorder that records nothing: [wav] is what stop hands back.
class FakeRecorder implements VoiceRecorder {
  FakeRecorder({this.startError});

  Object? startError;
  bool started = false;
  bool cancelled = false;
  final Uint8List wav = pcm16ToWav(Uint8List(320), sampleRate: 16000);

  @override
  bool get supported => true;

  @override
  Future<void> start() async {
    if (startError != null) throw startError!;
    started = true;
  }

  @override
  Future<Uint8List> stop() async => wav;

  @override
  Future<void> cancel() async => cancelled = true;

  /// How many times the live words asked for the buffer so far.
  int snapshots = 0;

  @override
  Uint8List? soFar() {
    snapshots++;
    return wav;
  }
}

/// A player that plays nothing: each play waits until [finish] or [stop].
class FakePlayer implements VoicePlayer {
  final List<({String body, double speed})> played = [];
  int stops = 0;
  Completer<void>? _current;

  @override
  bool get supported => true;

  @override
  Future<void> play(Uint8List wav, double speed) {
    played.add((body: utf8.decode(wav), speed: speed));
    _current = Completer<void>();
    return _current!.future;
  }

  /// The sound that is playing ends by itself.
  void finish() {
    final c = _current;
    if (c != null && !c.isCompleted) c.complete();
  }

  @override
  Future<void> stop() async {
    stops++;
    finish();
  }
}
