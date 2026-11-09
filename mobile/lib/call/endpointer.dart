import 'dart:math';
import 'dart:typed_data';

/// Hears when you start and stop talking in a call, from the mic's raw PCM
/// 16-bit mono at 16 kHz. Pure: feed it chunks, it hands back each finished
/// utterance (with a little audio from just before it) as raw PCM.
///
/// Shared contract E (the web's ENDPOINT_DEFAULTS hold the same values):
/// a 20 ms frame is loud when it is [endpointerOverFloorDb] above the room's
/// running floor and never quieter than [endpointerMinDb]; a turn starts
/// once [endpointerStartMs] of loud frames sit in a short sliding window (a
/// 20 ms click never starts one); it ends on a lower threshold (hysteresis)
/// after [endpointerEndSilenceMs] of quiet, and is dropped when it held less
/// than [endpointerMinSpeechMs] of voice. Guarded (while the bot speaks)
/// the thresholds rise, the start needs [endpointerGuardStartMs] and the
/// floor is frozen, so the phone's own speaker never counts as you.
const endpointerFrameMs = 20;
const endpointerPreRollMs = 300;
const endpointerEndSilenceMs = 700;
const endpointerStartMs = 120;
const endpointerMinSpeechMs = 350;
const endpointerMaxMs = 30000;
const endpointerMinDb = -50.0;
const endpointerOverFloorDb = 10.0;
const endpointerEndOverFloorDb = 6.0;
const endpointerGuardStartMs = 300;
const endpointerGuardMinDb = -30.0;
const endpointerGuardOverFloorDb = 20.0;

const _rate = 16000;
const _frameBytes = _rate * endpointerFrameMs ~/ 1000 * 2;
const _startFloorDb = -60.0;
const _floorFollow = 0.05;
const _levelLowDb = -60.0;
const _levelHighDb = -20.0;

/// The sliding window a start is judged in: the loud time plus a little.
const _windowSlackMs = 80;

class Endpointer {
  Endpointer({this.maxMs = endpointerMaxMs});

  final int maxMs;

  final List<Uint8List> _recent = [];
  final List<bool> _recentLoud = [];
  final BytesBuilder _speech = BytesBuilder(copy: false);
  Uint8List _carry = Uint8List(0);
  double _floorDb = _startFloorDb;
  bool _guarded = false;
  bool _speaking = false;
  int _voicedMs = 0;
  int _quietMs = 0;
  int _speechMs = 0;
  double _level = 0;

  /// True from the start of a turn until the utterance ends.
  bool get speaking => _speaking;

  /// Guard mode: the bot is speaking, so only a clear voice counts.
  bool get guarded => _guarded;

  /// The room's running floor, in dBFS.
  double get floorDb => _floorDb;

  /// The last frame's loudness, 0 (quiet) to 1 (loud), for the orb.
  double get level => _level;

  int get _startMs => _guarded ? endpointerGuardStartMs : endpointerStartMs;
  int get _windowFrames => (_startMs + _windowSlackMs) ~/ endpointerFrameMs;
  int get _keepFrames => max(endpointerPreRollMs ~/ endpointerFrameMs, _windowFrames);

  double get _startThreshold => _guarded
      ? max(endpointerGuardMinDb, _floorDb + endpointerGuardOverFloorDb)
      : max(endpointerMinDb, _floorDb + endpointerOverFloorDb);

  double get _endThreshold => _guarded
      ? max(endpointerGuardMinDb, _floorDb + endpointerGuardOverFloorDb)
      : max(endpointerMinDb, _floorDb + endpointerEndOverFloorDb);

  void reset() {
    _recent.clear();
    _recentLoud.clear();
    _speech.clear();
    _carry = Uint8List(0);
    _speaking = false;
    _voicedMs = _quietMs = _speechMs = 0;
    _level = 0;
  }

  /// On: the speaker plays, so start fresh with the higher bar and a frozen
  /// floor. Off: back to normal, keeping what was heard (a turn that cut in
  /// goes on).
  void guard(bool on) {
    if (on == _guarded) return;
    _guarded = on;
    if (on) reset();
  }

  /// End the turn now (you tapped the orb): its PCM, or null when nothing
  /// worth sending was heard.
  Uint8List? flush() => _speaking ? _finish() : null;

  /// One chunk in; a finished utterance's PCM out, or null.
  Uint8List? feed(Uint8List chunk) {
    final all = _carry.isEmpty ? chunk : (BytesBuilder()..add(_carry)..add(chunk)).takeBytes();
    var at = 0;
    Uint8List? done;
    while (all.length - at >= _frameBytes) {
      final frame = Uint8List.sublistView(all, at, at + _frameBytes);
      at += _frameBytes;
      done ??= _frame(Uint8List.fromList(frame));
    }
    _carry = Uint8List.fromList(Uint8List.sublistView(all, at));
    return done;
  }

  Uint8List? _frame(Uint8List frame) {
    final db = _db(frame);
    _level = ((db - _levelLowDb) / (_levelHighDb - _levelLowDb)).clamp(0.0, 1.0);
    if (!_speaking) return _idle(frame, db);
    _speech.add(frame);
    _speechMs += endpointerFrameMs;
    if (db > _endThreshold) {
      _voicedMs += endpointerFrameMs;
      _quietMs = 0;
    } else {
      _quietMs += endpointerFrameMs;
    }
    if (_quietMs >= endpointerEndSilenceMs || _speechMs >= maxMs) return _finish();
    return null;
  }

  Uint8List? _idle(Uint8List frame, double db) {
    final loud = db > _startThreshold;
    if (!loud && !_guarded) _floorDb += (db - _floorDb) * _floorFollow;
    _recent.add(frame);
    _recentLoud.add(loud);
    while (_recent.length > _keepFrames) {
      _recent.removeAt(0);
      _recentLoud.removeAt(0);
    }
    if (!_loudEnoughToStart()) return null;
    _speaking = true;
    for (final f in _recent) {
      _speech.add(f);
    }
    _voicedMs = _speechMs = _startMs;
    _quietMs = 0;
    _recent.clear();
    _recentLoud.clear();
    return null;
  }

  /// [_startMs] of loud frames within the last window.
  bool _loudEnoughToStart() {
    final from = max(0, _recentLoud.length - _windowFrames);
    var loudFrames = 0;
    for (var i = from; i < _recentLoud.length; i++) {
      if (_recentLoud[i]) loudFrames++;
    }
    return loudFrames * endpointerFrameMs >= _startMs;
  }

  Uint8List? _finish() {
    final pcm = _speech.takeBytes();
    final voiced = _voicedMs;
    _speaking = false;
    _voicedMs = _quietMs = _speechMs = 0;
    return voiced >= endpointerMinSpeechMs ? pcm : null;
  }

  static double _db(Uint8List frame) {
    final data = ByteData.sublistView(frame);
    var sum = 0.0;
    final n = frame.length ~/ 2;
    for (var i = 0; i < n; i++) {
      final s = data.getInt16(i * 2, Endian.little) / 32768;
      sum += s * s;
    }
    final rms = sqrt(sum / max(1, n));
    return rms <= 0 ? -100 : 20 * log(rms) / ln10;
  }
}
