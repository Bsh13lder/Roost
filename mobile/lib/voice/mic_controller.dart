import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';

import '../api/api_error.dart';
import 'audio_ports.dart';
import 'voice_models.dart';

/// idle → recording (the live words come) → listening (the final words) →
/// checking (the correction, when the bot's switch is on).
enum MicPhase { idle, recording, listening, checking }

const nothingHeardText = "I didn't catch anything. Try again.";

/// A correction of what you said (voice tuning D3): the raw words, the
/// cleaned words and each fix.
@immutable
class SpokenCorrection {
  const SpokenCorrection({
    required this.said,
    required this.corrected,
    required this.fixes,
  });

  final String said;
  final String corrected;
  final List<SpeechFix> fixes;
}

/// Tap to record, tap to stop (it stops by itself at two minutes), then the
/// Mac turns the recording into words. While it records, the buffer so far
/// goes for a partial transcript every second ([live], voice tuning D4);
/// the final words are handed to [onText]; with [correct] given, the check
/// follows and a change comes through [onCorrected] (the words were checked
/// either way: [onChecked]). Nothing is ever sent as a message.
class MicController extends ChangeNotifier {
  MicController({
    required this.recorder,
    required this.transcribe,
    required this.onText,
    this.partial,
    this.correct,
    this.correctOn,
    this.onCorrected,
    this.onChecked,
    this.maxSeconds = voiceMaxSeconds,
    this.partialEvery = voicePartialEvery,
  });

  /// Whether to check right now (the bot's switch, read at the moment); null
  /// means whenever [correct] is given.
  final bool Function()? correctOn;

  final VoiceRecorder recorder;
  final Future<String> Function(Uint8List wav) transcribe;
  final void Function(String text) onText;

  /// The live route; null: no live words.
  final Future<String> Function(Uint8List wav)? partial;

  /// The check (null when the bot's Correct what I say is off); it answers
  /// null when the words were fine.
  final Future<SpeechCorrection?> Function(String text)? correct;
  final void Function(SpokenCorrection correction)? onCorrected;
  final VoidCallback? onChecked;
  final int maxSeconds;
  final Duration partialEvery;

  MicPhase _phase = MicPhase.idle;
  int _seconds = 0;
  String _live = '';
  String? _error;
  Timer? _tick;
  Timer? _partialTick;
  bool _partialInFlight = false;
  int _recordingNo = 0;
  bool _disposed = false;

  MicPhase get phase => _phase;
  int get seconds => _seconds;

  /// The words heard so far while recording; empty once it ends.
  String get live => _live;
  String? get error => _error;

  Future<void> start() async {
    if (_phase != MicPhase.idle) return;
    _set(error: null);
    try {
      await recorder.start();
    } on VoiceError catch (e) {
      _set(error: e.message);
      return;
    } catch (_) {
      _set(error: micFailedText);
      return;
    }
    if (_disposed) {
      unawaited(recorder.cancel());
      return;
    }
    _seconds = 0;
    _live = '';
    _recordingNo++;
    _tick = Timer.periodic(const Duration(seconds: 1), (_) => _onTick());
    if (partial != null) {
      _partialTick = Timer.periodic(partialEvery, (_) => _onPartialTick());
    }
    _set(phase: MicPhase.recording);
  }

  void _onTick() {
    _seconds++;
    if (_seconds >= maxSeconds) {
      unawaited(finish());
    } else {
      _notify();
    }
  }

  /// One partial at a time, while the buffer is short enough to be cheap.
  void _onPartialTick() {
    if (_partialInFlight || _phase != MicPhase.recording) return;
    if (_seconds > voicePartialMaxSeconds || _seconds < 1) return;
    final wav = recorder.soFar();
    if (wav == null) return;
    final no = _recordingNo;
    _partialInFlight = true;
    partial!(wav).then((text) {
      if (_disposed || no != _recordingNo || _phase != MicPhase.recording) return;
      if (text.trim().isNotEmpty) {
        _live = text.trim();
        _notify();
      }
    }).catchError((_) {
      // A live transcript that didn't come is nothing: the final one will.
    }).whenComplete(() => _partialInFlight = false);
  }

  void _stopTimers() {
    _tick?.cancel();
    _partialTick?.cancel();
    _partialTick = null;
    _recordingNo++; // a partial still in flight is dropped
  }

  /// Stop and hear it.
  Future<void> finish() async {
    if (_phase != MicPhase.recording) return;
    _stopTimers();
    _live = '';
    _set(phase: MicPhase.listening);
    try {
      final wav = await recorder.stop();
      final text = (await transcribe(wav)).trim();
      if (_disposed) return;
      if (text.isEmpty) {
        _error = nothingHeardText;
      } else {
        onText(text);
        await _check(text);
      }
    } on ApiException catch (e) {
      _error = e.message;
    } on VoiceError catch (e) {
      _error = e.message;
    } finally {
      _set(phase: MicPhase.idle);
    }
  }

  /// The check (voice tuning D3): a failure leaves the words as heard, and
  /// the gateway may still post its line after the send.
  Future<void> _check(String text) async {
    final check = correct;
    if (check == null || !(correctOn?.call() ?? true)) return;
    _set(phase: MicPhase.checking);
    try {
      final found = await check(text);
      if (_disposed) return;
      onChecked?.call();
      if (found != null && found.changed) {
        onCorrected?.call(SpokenCorrection(
            said: text, corrected: found.corrected, fixes: found.fixes));
      }
    } catch (_) {
      // Your words stay as heard.
    }
  }

  /// Stop and drop the recording.
  Future<void> cancel() async {
    if (_phase != MicPhase.recording) return;
    _stopTimers();
    _live = '';
    _set(phase: MicPhase.idle);
    await recorder.cancel();
  }

  void clearError() => _set(error: null);

  void _set({MicPhase? phase, Object? error = _keep}) {
    if (phase != null) _phase = phase;
    if (!identical(error, _keep)) _error = error as String?;
    _notify();
  }

  void _notify() {
    if (!_disposed) notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    _stopTimers();
    if (_phase == MicPhase.recording) unawaited(recorder.cancel());
    super.dispose();
  }
}

const _keep = Object();

/// The heard words go after what is already typed, with one space between.
void appendToComposer(TextEditingController controller, String text) {
  final current = controller.text;
  final glue = current.isEmpty || RegExp(r'\s$').hasMatch(current) ? '' : ' ';
  final next = '$current$glue$text';
  controller.value = TextEditingValue(
    text: next,
    selection: TextSelection.collapsed(offset: next.length),
  );
}
