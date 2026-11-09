// StreamAudioSource is marked experimental in just_audio; the version is pinned in pubspec.lock.
// ignore_for_file: experimental_member_use

import 'dart:async';
import 'dart:typed_data';

import 'package:just_audio/just_audio.dart';

import 'audio_ports.dart';

/// Where the player is in its sound.
enum PlayerPhase { other, completed, idle }

/// The little of just_audio a voice player needs, so a test can fake its
/// shape: `play()` returns as soon as the sound starts, and the sound ends
/// on its own later, as a phase.
abstract class PlayerPort {
  Stream<PlayerPhase> get phases;
  Future<void> setBytes(Uint8List wav);
  Future<void> setSpeed(double speed);
  Future<void> play();
  Future<void> stop();
}

/// The real player (`just_audio`, MIT/Apache-2.0): a WAV from memory, so the
/// player never needs the session cookie; setSpeed keeps the pitch. It
/// never takes or handles audio focus itself (the call's mic must keep its
/// stream while a reply plays), so interruptions are left alone.
class JustAudioVoicePlayer implements VoicePlayer {
  JustAudioVoicePlayer() : _port = _JustAudioPort();

  JustAudioVoicePlayer.withPort(this._port);

  final PlayerPort _port;

  @override
  bool get supported => true;

  /// Plays the whole sound: back only once it has finished (or was
  /// stopped), then stopped, so the next part never cuts this one.
  @override
  Future<void> play(Uint8List wav, double speed) async {
    try {
      // The phase stream replays its last value (idle, from the last stop),
      // so the end is the first idle or completed after this sound loads.
      final ended = _port.phases
          .skipWhile((p) => p != PlayerPhase.other)
          .firstWhere((p) => p != PlayerPhase.other);
      await _port.setBytes(wav);
      await _port.setSpeed(speed);
      await _port.play();
      await ended;
      await _port.stop();
    } on PlayerException {
      throw const VoiceError(playFailedText);
    } on PlayerInterruptedException {
      return; // stopped for the next part or message
    }
  }

  @override
  Future<void> stop() => _port.stop();
}

class _JustAudioPort implements PlayerPort {
  final AudioPlayer _player = AudioPlayer(
    handleInterruptions: false,
    handleAudioSessionActivation: false,
  );

  @override
  Stream<PlayerPhase> get phases => _player.processingStateStream.map((s) => switch (s) {
        ProcessingState.completed => PlayerPhase.completed,
        ProcessingState.idle => PlayerPhase.idle,
        _ => PlayerPhase.other,
      });

  @override
  Future<void> setBytes(Uint8List wav) => _player.setAudioSource(_WavBytes(wav));

  @override
  Future<void> setSpeed(double speed) => _player.setSpeed(speed);

  @override
  Future<void> play() => _player.play();

  @override
  Future<void> stop() => _player.stop();
}

class _WavBytes extends StreamAudioSource {
  _WavBytes(this._bytes);

  final Uint8List _bytes;

  @override
  Future<StreamAudioResponse> request([int? start, int? end]) async {
    final from = start ?? 0;
    final to = end ?? _bytes.length;
    return StreamAudioResponse(
      sourceLength: _bytes.length,
      contentLength: to - from,
      offset: from,
      stream: Stream.value(_bytes.sublist(from, to)),
      contentType: 'audio/wav',
    );
  }
}
