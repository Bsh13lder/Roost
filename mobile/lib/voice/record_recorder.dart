import 'dart:async';
import 'dart:typed_data';

import 'package:record/record.dart';

import 'audio_ports.dart';
import 'voice_models.dart';

/// The real recorder (`record`, BSD-3): PCM 16-bit mono at 16 kHz streamed
/// into memory and wrapped as a WAV. Nothing is written to disk.
class RecordVoiceRecorder implements VoiceRecorder {
  final AudioRecorder _recorder = AudioRecorder();
  final BytesBuilder _pcm = BytesBuilder(copy: false);
  StreamSubscription<Uint8List>? _sub;
  Completer<void>? _done;

  @override
  bool get supported => true;

  @override
  Future<void> start() async {
    // Asks for the microphone the first time.
    if (!await _recorder.hasPermission()) throw const VoiceError(micDeniedText);
    _pcm.clear();
    final done = Completer<void>();
    _done = done;
    try {
      final stream = await _recorder.startStream(const RecordConfig(
        encoder: AudioEncoder.pcm16bits,
        sampleRate: voiceSampleRate,
        numChannels: 1,
      ));
      _sub = stream.listen(_pcm.add,
          onDone: done.complete, onError: (_) => done.complete());
    } catch (_) {
      throw const VoiceError(micFailedText);
    }
  }

  @override
  Future<Uint8List> stop() async {
    await _recorder.stop();
    await _done?.future.timeout(const Duration(seconds: 1), onTimeout: () {});
    await _sub?.cancel();
    _sub = null;
    return pcm16ToWav(_pcm.takeBytes(), sampleRate: voiceSampleRate);
  }

  @override
  Future<void> cancel() async {
    await _recorder.cancel();
    await _sub?.cancel();
    _sub = null;
    _pcm.clear();
  }

  /// A copy of the samples so far (the builder keeps them).
  @override
  Uint8List? soFar() => pcm16ToWav(_pcm.toBytes(), sampleRate: voiceSampleRate);
}
