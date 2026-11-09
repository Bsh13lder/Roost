import 'dart:async';
import 'dart:math';

import '../live/bot_frames.dart';
import '../voice/voice_api.dart';

/// Follows one reply being spoken by the server as it streams (shared
/// contract B): `speech_ready` frames for its message id, with a poll of
/// `GET …/live-speech/{id}` in between in case a frame was missed. Events
/// are prefix-stable counts of ready parts; [confirmed] turns true at the
/// first sign the server knows this reply as a call's (a frame, or a plan),
/// so an older gateway's 404s leave it false and the stored reply is spoken
/// the old way once the run is over.
class LiveReplyFollower {
  LiveReplyFollower({
    required this.threadId,
    required this.messageId,
    required Stream<Frame> frames,
    required Future<LiveSpeechPlan?> Function() poll,
    required Duration pollEvery,
    required void Function(LiveSpeechEvent event) onEvent,
  })  : _frames = frames,
        _poll = poll,
        _pollEvery = pollEvery,
        _onEvent = onEvent;

  final String threadId;
  final String messageId;
  final Stream<Frame> _frames;
  final Future<LiveSpeechPlan?> Function() _poll;
  final Duration _pollEvery;
  final void Function(LiveSpeechEvent event) _onEvent;

  final _events = StreamController<LiveSpeechEvent>();
  StreamSubscription<Frame>? _sub;
  Timer? _timer;
  bool _polling = false;
  bool _confirmed = false;
  int _ready = 0;
  bool _done = false;

  /// The events, buffered until someone listens (the speaker).
  Stream<LiveSpeechEvent> get events => _events.stream;

  bool get confirmed => _confirmed;
  int get ready => _ready;
  bool get done => _done;

  void start() {
    _sub = _frames.listen(_onFrame);
    _timer = Timer.periodic(_pollEvery, (_) => _pollNow());
  }

  /// The run is over and the server never said done: take what is there.
  void forceDone() {
    if (!_done) _update(_ready, true, null);
  }

  void dispose() {
    _timer?.cancel();
    _sub?.cancel();
    if (!_events.isClosed) _events.close();
  }

  void _onFrame(Frame f) {
    if (f['type'] != 'speech_ready' || f['message_id'] != messageId || f['thread_id'] != threadId) return;
    final part = f['part'];
    if (part is! int) return;
    _update(part + 1, f['done'] == true, null);
  }

  Future<void> _pollNow() async {
    if (_polling || _done) return;
    _polling = true;
    try {
      final plan = await _poll();
      if (plan == null || _done) return;
      _confirmed = true;
      if (plan.parts > _ready || plan.done) _update(plan.parts, plan.done, plan.speed);
    } catch (_) {
      // No answer this time; the next poll or frame will tell.
    } finally {
      _polling = false;
    }
  }

  void _update(int ready, bool done, double? speed) {
    if (_events.isClosed) return;
    final grew = ready > _ready || (done && !_done);
    _confirmed = true;
    _ready = max(_ready, ready);
    _done = _done || done;
    if (!grew) return;
    final event = (ready: _ready, done: _done, speed: speed);
    _onEvent(event);
    _events.add(event);
    if (_done) {
      _timer?.cancel();
      _events.close();
    }
  }
}
