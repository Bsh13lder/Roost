import 'dart:typed_data';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'just_audio_player.dart';
import 'record_recorder.dart';

/// A recorder and a player behind small interfaces, so tests never touch real
/// audio. The real ones (the `record` and `just_audio` packages) override
/// these providers' defaults; tests override them with fakes, and the
/// Unsupported* stand-ins remain for a build that can't record or play.

/// A failure with words the user can read.
class VoiceError implements Exception {
  const VoiceError(this.message);
  final String message;

  @override
  String toString() => message;
}

const micDeniedText =
    'Roost needs the microphone to hear you. Allow it in Settings.';
const micFailedText = "The microphone didn't start. Try again.";
const playFailedText = "That couldn't be played. Try again.";

/// Records one WAV (PCM 16-bit mono, 16 kHz) in memory: nothing is written
/// to disk.
abstract class VoiceRecorder {
  /// False when this build can't record (no mic button is shown).
  bool get supported;

  /// Asks for the microphone at first use; throws [VoiceError] when refused.
  Future<void> start();

  /// Stops and returns the whole recording as a WAV file's bytes.
  Future<Uint8List> stop();

  /// Stops and drops what was recorded.
  Future<void> cancel();

  /// What was recorded so far, as a WAV, the recording going on (the live
  /// words, voice tuning D4); null when this build cannot say.
  Uint8List? soFar();
}

/// Plays one WAV from memory at a speed that keeps the pitch.
abstract class VoicePlayer {
  bool get supported;

  /// Completes when the sound has finished or [stop] was called.
  Future<void> play(Uint8List wav, double speed);

  Future<void> stop();
}

class UnsupportedRecorder implements VoiceRecorder {
  const UnsupportedRecorder();

  @override
  bool get supported => false;

  @override
  Future<void> start() async => throw const VoiceError(micFailedText);

  @override
  Future<Uint8List> stop() async => Uint8List(0);

  @override
  Future<void> cancel() async {}

  @override
  Uint8List? soFar() => null;
}

class UnsupportedPlayer implements VoicePlayer {
  const UnsupportedPlayer();

  @override
  bool get supported => false;

  @override
  Future<void> play(Uint8List wav, double speed) async =>
      throw const VoiceError(playFailedText);

  @override
  Future<void> stop() async {}
}

final voiceRecorderProvider = Provider<VoiceRecorder>((ref) {
  final recorder = RecordVoiceRecorder();
  ref.onDispose(recorder.cancel);
  return recorder;
});

final voicePlayerProvider = Provider<VoicePlayer>((ref) {
  final player = JustAudioVoicePlayer();
  ref.onDispose(player.stop);
  return player;
});

/// A WAV file around raw little-endian PCM 16-bit samples.
Uint8List pcm16ToWav(
  Uint8List pcm, {
  required int sampleRate,
  int channels = 1,
}) {
  const header = 44;
  final out = ByteData(header + pcm.length);
  void ascii(int at, String s) {
    for (var i = 0; i < s.length; i++) {
      out.setUint8(at + i, s.codeUnitAt(i));
    }
  }

  final blockAlign = channels * 2;
  ascii(0, 'RIFF');
  out.setUint32(4, 36 + pcm.length, Endian.little);
  ascii(8, 'WAVE');
  ascii(12, 'fmt ');
  out.setUint32(16, 16, Endian.little);
  out.setUint16(20, 1, Endian.little); // PCM
  out.setUint16(22, channels, Endian.little);
  out.setUint32(24, sampleRate, Endian.little);
  out.setUint32(28, sampleRate * blockAlign, Endian.little);
  out.setUint16(32, blockAlign, Endian.little);
  out.setUint16(34, 16, Endian.little);
  ascii(36, 'data');
  out.setUint32(40, pcm.length, Endian.little);
  final bytes = out.buffer.asUint8List();
  bytes.setRange(header, header + pcm.length, pcm);
  return bytes;
}
