import 'dart:typed_data';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:record/record.dart';

import '../voice/audio_ports.dart';
import '../voice/voice_models.dart';

/// The call's open mic: raw PCM 16-bit mono at 16 kHz, in memory only, with
/// the phone's echo cancelling, noise suppression and auto gain on. Tests
/// use a fake.
abstract class CallMic {
  bool get supported;

  /// Asks for the microphone at first use; throws [VoiceError] when refused.
  Future<Stream<Uint8List>> open();

  Future<void> close();
}

/// The call's recording settings (shared contract H). `audioInterruption:
/// none` is the one that matters: with the default (`pause`) the first
/// reply's playback took Android's audio focus and parked the mic stream
/// for good, with no error, while the screen kept saying "Listening".
const callRecordConfig = RecordConfig(
  encoder: AudioEncoder.pcm16bits,
  sampleRate: voiceSampleRate,
  numChannels: 1,
  echoCancel: true,
  noiseSuppress: true,
  autoGain: true,
  audioInterruption: AudioInterruptionMode.none,
  androidConfig: AndroidRecordConfig(manageBluetooth: false),
);

/// The real one (`record`, BSD-3).
class RecordCallMic implements CallMic {
  final AudioRecorder _recorder = AudioRecorder();

  @override
  bool get supported => true;

  @override
  Future<Stream<Uint8List>> open() async {
    if (!await _recorder.hasPermission()) throw const VoiceError(micDeniedText);
    try {
      return await _recorder.startStream(callRecordConfig);
    } catch (_) {
      throw const VoiceError(micFailedText);
    }
  }

  @override
  Future<void> close() async {
    try {
      await _recorder.stop();
    } catch (_) {
      // Already stopped.
    }
  }
}

final callMicProvider = Provider<CallMic>((ref) {
  final mic = RecordCallMic();
  ref.onDispose(mic.close);
  return mic;
});
