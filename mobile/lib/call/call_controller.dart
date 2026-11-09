import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart' show HapticFeedback;

import '../api/api_error.dart';
import '../api/models.dart';
import '../chat/english_fix.dart';
import '../features/chat/chat_controller.dart' show queuedNotice;
import '../live/bot_frames.dart';
import '../voice/audio_ports.dart';
import '../voice/read_aloud.dart';
import '../voice/voice_api.dart';
import '../voice/voice_models.dart';
import 'call_caption.dart';
import 'call_live_reply.dart';
import 'call_mic.dart';
import 'call_timing.dart';
import 'call_words.dart';
import 'endpointer.dart';

/// warming: the mic is being opened · listening: the mic is open · hearing:
/// your words are being turned into text · thinking: the bot works on your
/// message · speaking: its reply plays · asking: it waits on a card · off:
/// the call couldn't start · ended.
enum CallPhase { warming, listening, hearing, thinking, speaking, asking, off, ended }

const nothingCaughtText = "I didn't catch that.";
const warmingNote = 'Warming up the voice…';
const micStoppedNote = 'The microphone stopped. Tap End and call again.';
const pausedNote = 'Paused — open Roost to continue';
String thinkingTooLongNote(String bot) => '$bot is still working. Check the chat, or say something to go on.';
String saidNothingNote(String bot) => '$bot worked and said nothing.';

/// Talking over the bot stops it. One place to turn it off should a phone's
/// echo cancelling let its own speaker through the guard.
const callBargeIn = true;

typedef SendTurn = Future<SendStatus> Function(String text);
typedef SpeakLive = Future<void> Function(String threadId, String messageId, Stream<LiveSpeechEvent> events);
typedef CallBeat = Future<void> Function({String? interrupted});
typedef LiveSpeechLookup = Future<LiveSpeechPlan?> Function(String threadId, String messageId);

Future<void> _mediumHaptic() => HapticFeedback.mediumImpact();

/// One voice call with a bot: listen, hear, send as your own message, follow
/// the bot's reply as it streams and speak it, listen again. Nothing is
/// recorded to disk; every turn is an ordinary message in the bot's chat.
/// While the bot speaks the mic stays open behind a guard, so a clear voice
/// cuts it off; a tap on the orb sends what you said so far, or stops it.
class CallController extends ChangeNotifier {
  CallController({
    required this.mic,
    required this.warm,
    required this.transcribe,
    required this.send,
    required this.speak,
    required this.speakLive,
    required this.speakLine,
    required this.stopSpeaking,
    required this.beat,
    required this.endCall,
    required this.frames,
    required this.liveSpeech,
    this.haptic = _mediumHaptic,
    this.botName = 'Your bot',
    this.timing = const CallTiming(),
    Endpointer? endpointer,
  }) : _ears = endpointer ?? Endpointer();

  final CallMic mic;
  final Future<void> Function() warm;
  final Future<String> Function(Uint8List wav) transcribe;
  final SendTurn send;

  /// The stored reply, after the run (an older gateway, or no live parts).
  final Future<void> Function(Message reply) speak;
  final SpeakLive speakLive;
  final Future<void> Function(String key) speakLine;
  final Future<void> Function() stopSpeaking;
  final CallBeat beat;
  final Future<void> Function() endCall;
  final Stream<Frame> frames;
  final LiveSpeechLookup liveSpeech;
  final Future<void> Function() haptic;
  final String botName;
  final CallTiming timing;
  final Endpointer _ears;

  CallPhase _phase = CallPhase.warming;
  bool _muted = false;
  bool _mutedBeforePause = false;
  bool _lineBusy = false;
  bool _micReopened = false;
  bool _disposed = false;
  String? _error;
  String? _note;
  String? _heard;
  EnglishFix? _heardFix;
  String? _turnId;
  String? _saying;
  String? _activity;
  Future<void>? _warm;
  StreamSubscription<Uint8List>? _sub;
  List<Message> _messages = const [];
  Map<String, String> _streaming = const {};
  Set<String> _before = const {};
  final Set<String> _spoken = {};

  // One turn's reply.
  bool _sawOnIt = false;
  bool _deltaSeen = false;
  bool _liveStarted = false;
  int _stillCount = 0;
  String? _replyId;
  String? _speakingId;
  LiveReplyFollower? _follower;

  Timer? _heartbeat;
  Timer? _stall;
  Timer? _thinkingTimer;
  Timer? _stillTimer;
  Timer? _liveStallTimer;

  CallPhase get phase => _phase;
  bool get muted => _muted;
  String? get error => _error;

  /// A quiet line, e.g. "I didn't catch that."
  String? get note => _note;

  /// What you said last.
  String? get heard => _heard;

  /// The corrected copy of what you said last (Correct my English), once the
  /// server has posted one for this turn; it takes the plain caption's place.
  EnglishFix? get heardFix => _heardFix;

  /// The reply as it streams, or is spoken.
  String? get saying => _saying;

  /// The bot's live activity words while it works.
  String? get activity => _activity;

  /// 0..1 while you talk, for the orb.
  double get level => _phase == CallPhase.listening && !_muted ? _ears.level : 0;

  // ── Start ──────────────────────────────────────────────────────────────

  /// Opens the mic first, then warms the voice behind it: a turn heard
  /// before the models are up waits for them; the greeting plays once they
  /// are, if you are not already talking.
  Future<void> start() async {
    _set(CallPhase.warming);
    if (!await _openMic()) return;
    if (_phase == CallPhase.ended) return;
    _set(CallPhase.listening, note: warmingNote);
    _armStall();
    _heartbeat = Timer.periodic(timing.heartbeat, (_) => _beat());
    unawaited(_beat());
    _warm = _runWarm();
    await _warm;
  }

  Future<void> _runWarm() async {
    try {
      await warm();
    } on ApiException catch (e) {
      if (e.status == 503) {
        await mic.close();
        return _fail(e.message);
      }
      // Anything else: the first answer just waits for the models.
    } catch (_) {
      // Same.
    }
    if (_phase == CallPhase.ended || _phase == CallPhase.off) return;
    if (_note == warmingNote) _note = null;
    _notify();
    if (_phase == CallPhase.listening) await _sayLine('greeting');
  }

  Future<bool> _openMic() async {
    try {
      final chunks = await mic.open();
      if (_phase == CallPhase.ended) {
        unawaited(mic.close());
        return false;
      }
      unawaited(_sub?.cancel());
      _sub = chunks.listen(_onChunk);
      return true;
    } on VoiceError catch (e) {
      _fail(e.message);
      return false;
    }
  }

  // ── The mic ────────────────────────────────────────────────────────────

  void _onChunk(Uint8List chunk) {
    _armStall();
    if (_muted || _lineBusy) return;
    switch (_phase) {
      case CallPhase.listening || CallPhase.asking:
        final utterance = _ears.feed(chunk);
        _notify();
        if (utterance != null) unawaited(_hear(utterance));
      case CallPhase.speaking:
        if (!callBargeIn) return;
        final utterance = _ears.feed(chunk);
        if (_ears.speaking || utterance != null) _bargeIn();
        if (utterance != null) unawaited(_hear(utterance));
      default:
        return;
    }
  }

  /// Android can park the mic's stream without a word (a lost audio focus):
  /// no chunk for [CallTiming.micStall] while listening opens it once more;
  /// a second stall is said.
  void _armStall() {
    _stall?.cancel();
    _stall = Timer(timing.micStall, _onMicStall);
  }

  Future<void> _onMicStall() async {
    if (_phase == CallPhase.ended || _phase == CallPhase.off) return;
    if (_phase != CallPhase.listening || _muted) return _armStall();
    if (_micReopened) {
      _note = micStoppedNote;
      return _notify();
    }
    _micReopened = true;
    await mic.close();
    if (_phase == CallPhase.ended) return;
    if (await _openMic()) _armStall();
  }

  // ── A turn ─────────────────────────────────────────────────────────────

  Future<void> _hear(Uint8List pcm) async {
    _clearReplyWatch();
    _set(CallPhase.hearing, note: null);
    final warm = _warm;
    if (warm != null) await warm;
    if (_phase != CallPhase.hearing) return;
    String text;
    try {
      final wav = pcm16ToWav(pcm, sampleRate: voiceSampleRate);
      text = (await transcribe(wav).timeout(timing.hearing)).trim();
    } on ApiException catch (e) {
      return _sayLineThen('say_again', note: e.message);
    } on TimeoutException {
      return _sayLineThen('say_again');
    }
    if (_phase != CallPhase.hearing) return;
    if (text.isEmpty) return _sayLineThen('not_caught', note: nothingCaughtText);
    _heard = text;
    _heardFix = null;
    _turnId = null;
    if (isGoodbye(text)) return _goodbye();
    _saying = null;
    _before = {for (final m in _messages) m.id};
    _set(CallPhase.thinking);
    await _send(text);
  }

  Future<void> _send(String text) async {
    SendStatus status;
    try {
      status = await send(text);
    } on ApiException catch (e) {
      return _listen(note: e.message);
    } catch (e) {
      return _listen(note: '$e');
    }
    if (_phase != CallPhase.thinking) return;
    _sawOnIt = false;
    _deltaSeen = false;
    _stillCount = 0;
    if (status == SendStatus.queued) {
      _note = queuedNotice;
      _notify();
    }
    _thinkingTimer = Timer(timing.thinking, _thinkingTooLong);
    _stillTimer = Timer(timing.stillOnItAfter, _stillOnIt);
    _watchPlaceholder();
  }

  Future<void> _goodbye() async {
    _notify();
    await _sayLine('bye');
    await end();
  }

  void _thinkingTooLong() {
    if (_phase == CallPhase.thinking) _listen(note: thinkingTooLongNote(botName));
  }

  void _stillOnIt() {
    if (_phase != CallPhase.thinking || _deltaSeen || _stillCount >= CallTiming.stillOnItMax) return;
    _stillCount++;
    unawaited(_sayLine('still_on_it'));
    if (_stillCount < CallTiming.stillOnItMax) _stillTimer = Timer(timing.stillOnItEvery, _stillOnIt);
  }

  // ── The bot's reply ────────────────────────────────────────────────────

  /// The chat changed (a message, streamed text, a status): follow the
  /// reply's placeholder for live speech, its text for the caption, and the
  /// end of the run for what to do when nothing was spoken.
  void chatChanged(
    List<Message> messages,
    BotStatus? status, {
    String? activity,
    Map<String, String> streaming = const {},
  }) {
    _messages = messages;
    _streaming = streaming;
    _activity = activity;
    _followHeardFix();
    if (_phase == CallPhase.thinking || _phase == CallPhase.asking || _phase == CallPhase.speaking) {
      _updateReply(status);
    }
    _notify();
  }

  /// Your message of this turn is the newest of yours since the send; the
  /// english_fix line that names it (or, while its id is unknown, one that
  /// quotes your words) is the corrected copy to show.
  void _followHeardFix() {
    if (_heard == null) return;
    for (final m in _messages) {
      if (m.fromUser && m.kind == 'text' && !_before.contains(m.id)) _turnId = m.id;
    }
    for (final m in _messages) {
      if (m.kind != 'english_fix' || _before.contains(m.id)) continue;
      final fix = parseEnglishFix(m.body);
      if (fix == null) continue;
      final mine = _turnId == null ? fix.said == _heard : fix.messageId == _turnId;
      if (mine) _heardFix = fix;
    }
  }

  void _updateReply(BotStatus? status) {
    if (status == BotStatus.onIt) _sawOnIt = true;
    if (_phase == CallPhase.thinking) _watchPlaceholder();
    _followCaption();
    if (status == BotStatus.onIt) return;
    final follower = _follower;
    if (_phase == CallPhase.speaking) {
      if (follower != null && !follower.done) _armLiveStall();
      return;
    }
    final reply = _newReply();
    if (follower != null && follower.confirmed) {
      // The server speaks this reply live; never also through /speech.
      if (reply != null) _spoken.add(reply.id);
      if (!follower.done) _armLiveStall();
      return;
    }
    if (reply != null) return unawaited(_speak(reply));
    if (status == BotStatus.askingYou || status == BotStatus.stuck) {
      if (_phase != CallPhase.asking) _askYou();
      return;
    }
    if (_sawOnIt && _phase == CallPhase.thinking) _listen(note: saidNothingNote(botName));
  }

  /// The reply's placeholder (a bot message with seq 0, new since the send)
  /// carries the id that `speech_ready` frames name.
  void _watchPlaceholder() {
    if (_replyId != null) return;
    Message? placeholder;
    for (final m in _messages) {
      if (m.role == 'bot' && m.seq == 0 && !_before.contains(m.id)) placeholder = m;
    }
    if (placeholder == null) return;
    final p = placeholder;
    _replyId = p.id;
    _follower = LiveReplyFollower(
      threadId: p.threadId,
      messageId: p.id,
      frames: frames,
      poll: () => liveSpeech(p.threadId, p.id),
      pollEvery: timing.livePoll,
      onEvent: _onLiveEvent,
    )..start();
  }

  void _followCaption() {
    final id = _replyId;
    if (id == null) return;
    final text = _streaming[id];
    if (text == null || text.isEmpty) return;
    _deltaSeen = true;
    final caption = callCaption(text);
    if (caption != null) _saying = caption;
  }

  Message? _newReply() {
    Message? reply;
    for (final m in _messages) {
      if (canSpeak(m) && !_before.contains(m.id) && !_spoken.contains(m.id)) reply = m;
    }
    return reply;
  }

  void _onLiveEvent(LiveSpeechEvent event) {
    final follower = _follower;
    if (follower == null) return;
    if (event.done) _liveStallTimer?.cancel();
    if (_liveStarted || event.ready == 0) return;
    _liveStarted = true;
    _spoken.add(follower.messageId);
    _startSpeaking(follower.messageId);
    unawaited(_speakLiveReply(follower));
  }

  Future<void> _speakLiveReply(LiveReplyFollower follower) async {
    try {
      await speakLive(follower.threadId, follower.messageId, follower.events);
    } catch (_) {
      // The speech state carries the words.
    }
    await _afterSpeaking();
  }

  /// The run is over but the server has not said done: give it a moment,
  /// then take the parts there are, or fall back to the stored reply when
  /// none came.
  void _armLiveStall() {
    if (_liveStallTimer?.isActive ?? false) return;
    _liveStallTimer = Timer(timing.liveStall, _onLiveStall);
  }

  void _onLiveStall() {
    final follower = _follower;
    if (follower == null || follower.done) return;
    if (follower.ready > 0) return follower.forceDone();
    _clearReplyWatch();
    final reply = _newReply();
    if (reply != null) return unawaited(_speak(reply));
    if (_phase == CallPhase.thinking) _listen(note: saidNothingNote(botName));
  }

  Future<void> _speak(Message reply) async {
    _clearReplyWatch();
    _spoken.add(reply.id);
    _saying = callCaption(reply.body);
    _startSpeaking(reply.id);
    try {
      await speak(reply);
    } catch (_) {
      // speechFailed carries the words.
    }
    await _afterSpeaking();
  }

  void _startSpeaking(String messageId) {
    _speakingId = messageId;
    _thinkingTimer?.cancel();
    _stillTimer?.cancel();
    _ears.guard(true);
    _set(CallPhase.speaking);
  }

  /// After the bot's voice: a short tail, then the mic arms again.
  Future<void> _afterSpeaking() async {
    if (_phase != CallPhase.speaking) return;
    await Future<void>.delayed(timing.speakerTail);
    if (_phase != CallPhase.speaking) return;
    _listen();
  }

  void _askYou() {
    _thinkingTimer?.cancel();
    _stillTimer?.cancel();
    _set(CallPhase.asking, note: null);
    unawaited(_sayLine('asking'));
  }

  // ── Cutting in ─────────────────────────────────────────────────────────

  /// You spoke over the bot: it stops, the server hears which reply was cut,
  /// and your words so far are kept.
  void _bargeIn() {
    final cut = _speakingId;
    _ears.guard(false);
    _set(CallPhase.listening);
    unawaited(stopSpeaking());
    unawaited(_beat(interrupted: cut));
    unawaited(haptic());
  }

  /// The orb: while it speaks, stop it; while you talk, send now.
  Future<void> orbTapped() async {
    if (_phase == CallPhase.speaking) return interrupt();
    if (_phase != CallPhase.listening && _phase != CallPhase.asking) return;
    final utterance = _ears.flush();
    if (utterance != null) await _hear(utterance);
  }

  /// Tap the orb while it speaks: stop and listen.
  Future<void> interrupt() async {
    if (_phase != CallPhase.speaking) return;
    _listen();
    await stopSpeaking();
  }

  // ── Lines and notes ────────────────────────────────────────────────────

  /// A fixed line in the bot's voice; the mic is deaf while it plays, and
  /// forgets the room right after.
  Future<void> _sayLine(String key) async {
    if (_phase == CallPhase.ended || _phase == CallPhase.off) return;
    _lineBusy = true;
    try {
      await speakLine(key);
    } catch (_) {
      // The note (when there is one) stands in.
    } finally {
      _lineBusy = false;
    }
    if (_phase == CallPhase.listening || _phase == CallPhase.asking) _ears.reset();
  }

  Future<void> _sayLineThen(String key, {String? note}) async {
    _listen(note: note);
    await _sayLine(key);
  }

  /// A reply couldn't be played: say why; the call listens again.
  void speechFailed(String message) {
    _note = message;
    _notify();
  }

  // ── Mute, pause, end ───────────────────────────────────────────────────

  void toggleMute() {
    _muted = !_muted;
    _ears.reset();
    _notify();
  }

  /// The app went behind: deaf until it is back.
  void pause() {
    _mutedBeforePause = _muted;
    _muted = true;
    _note = pausedNote;
    _notify();
  }

  void resume() {
    _muted = _mutedBeforePause;
    if (_note == pausedNote) _note = null;
    _ears.reset();
    _notify();
  }

  Future<void> end() async {
    if (_phase == CallPhase.ended) return;
    _set(CallPhase.ended);
    _cancelTimers();
    _clearReplyWatch();
    final sub = _sub;
    _sub = null;
    await stopSpeaking();
    // The mic stops by itself once closed; never wait on the cancel.
    unawaited(sub?.cancel());
    await mic.close();
    try {
      await endCall();
    } catch (_) {
      // Best effort.
    }
  }

  Future<void> _beat({String? interrupted}) async {
    try {
      await beat(interrupted: interrupted);
    } catch (_) {
      // Best effort; the next beat may do.
    }
  }

  void _listen({String? note}) {
    _clearReplyWatch();
    _ears.guard(false);
    _ears.reset();
    _set(CallPhase.listening, note: note);
  }

  void _clearReplyWatch() {
    _follower?.dispose();
    _follower = null;
    _replyId = null;
    _liveStarted = false;
    _thinkingTimer?.cancel();
    _stillTimer?.cancel();
    _liveStallTimer?.cancel();
  }

  void _cancelTimers() {
    _heartbeat?.cancel();
    _stall?.cancel();
    _thinkingTimer?.cancel();
    _stillTimer?.cancel();
    _liveStallTimer?.cancel();
  }

  void _fail(String message) {
    _error = message;
    _cancelTimers();
    _set(CallPhase.off);
  }

  void _set(CallPhase phase, {Object? note = _keep}) {
    if (_phase == CallPhase.ended && phase != CallPhase.ended) return;
    _phase = phase;
    if (!identical(note, _keep)) _note = note as String?;
    _notify();
  }

  void _notify() {
    if (!_disposed) notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    _cancelTimers();
    _follower?.dispose();
    _sub?.cancel();
    super.dispose();
  }
}

const _keep = Object();
