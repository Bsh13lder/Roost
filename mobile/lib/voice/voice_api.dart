import 'dart:typed_data';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api_client.dart';
import '../api/api_error.dart';
import '../api/providers.dart';
import 'voice_models.dart';

/// The gateway waits up to 180 s for the Mac's voice service (a first use
/// loads a model), so the phone waits a little longer than that.
const voiceReceiveTimeout = Duration(seconds: 190);

const voiceFailedText = "Voice couldn't do that just now. Try again.";

/// How many parts a message is spoken in, and the bot's speed.
typedef SpeechPlan = ({int parts, double speed});

/// `GET …/live-speech/{id}`: how many parts are ready, whether the reply is
/// finished, and the bot's speed (shared contract B).
typedef LiveSpeechPlan = ({int parts, bool done, double speed});

/// One step of a reply being spoken as it streams: how many parts are ready
/// so far, whether that is all of them, and the speed when known.
typedef LiveSpeechEvent = ({int ready, bool done, double? speed});

/// The voice routes (docs/plans/2026-10-30-roost-voice.md §2, V2, and the
/// call's routes of the shared contract A–C). Every route the gateway may
/// not have yet (an older server) fails soft: null, or nothing.
class VoiceApi {
  const VoiceApi(this._api);

  final ApiClient _api;

  Future<VoiceInfo> info() async =>
      VoiceInfo.fromJson(await _guard(() => _api.get('/api/voice')));

  /// `PUT /api/bots/{id}/voice` with the whole object; the updated bot.
  Future<Object?> save(String botId, BotVoice voice) => _guard(
    () => _api.put('/api/bots/${Uri.encodeComponent(botId)}/voice', voice.toJson()),
  );

  /// A WAV recording → its words. Nothing is sent as a message. With [botId]
  /// (voice tuning D1/D2) the ear reads that bot's names and language first.
  Future<String> transcribe(Uint8List wav, {String? botId}) =>
      _hear('/api/voice/transcribe', wav, botId);

  /// The recording so far, the mic still open → the live words (D4). An
  /// older gateway without the route gives nothing.
  Future<String> partial(Uint8List wav, {String? botId}) async {
    try {
      return await _hear('/api/voice/partial', wav, botId);
    } on ApiException catch (e) {
      if (e.status == 404) return '';
      rethrow;
    }
  }

  Future<String> _hear(String route, Uint8List wav, String? botId) async {
    final path = botId == null ? route : '$route?bot_id=${Uri.encodeQueryComponent(botId)}';
    final r = await _guard(
      () => _api.postBytes(path, wav, 'audio/wav', receiveTimeout: voiceReceiveTimeout),
    );
    final text = r is Map ? r['text'] : null;
    return text is String ? text : '';
  }

  /// Correct what I say before the send (voice tuning D3): the cleaned words
  /// and each fix; null when the words were fine, the switch is off, or the
  /// gateway is older than the route.
  Future<SpeechCorrection?> correct(String text, String botId) async {
    final r = await _orNull(
      () => _api.post('/api/voice/correct', {'text': text, 'bot_id': botId}, voiceReceiveTimeout),
    );
    if (r == null) return null;
    final found = SpeechCorrection.fromJson(r, text);
    return found.changed ? found : null;
  }

  /// A call opens: the Mac loads both voice models now (the first load takes
  /// about 25 s), so the first answer doesn't wait for them. With [botId]
  /// it also pre-makes the fixed lines in that bot's voice.
  Future<void> warm({String? botId}) => _guard(
    () => _api.post(
      '/api/voice/warm',
      {'bot_id': ?botId},
      voiceReceiveTimeout,
    ),
  );

  /// A fixed spoken line ("Hi, I'm listening.") in the bot's voice; null for
  /// an unknown key or a gateway without the route.
  Future<Uint8List?> line(String botId, String key) => _orNull(
    () => _api.getBytes(
      '/api/bots/${Uri.encodeComponent(botId)}/voice/line/${Uri.encodeComponent(key)}',
      receiveTimeout: voiceReceiveTimeout,
    ),
  );

  /// Starts or beats the call on a thread; with [interrupted], the reply you
  /// cut off. Best effort: an older gateway's 404 is nothing.
  Future<void> callBeat(String threadId, {String? interrupted}) => _quiet(
    () => _api.post(_call(threadId), {'interrupted': ?interrupted}),
  );

  /// Ends the call on a thread (idempotent).
  Future<void> callEnd(String threadId) => _quiet(() => _api.delete(_call(threadId)));

  /// The reply's parts spoken as it streams; null until the server knows
  /// the reply as a call's, or on an older gateway.
  Future<LiveSpeechPlan?> liveSpeech(String threadId, String messageId) async {
    final r = await _orNull(() => _api.get(_live(threadId, messageId)));
    if (r == null) return null;
    final parts = r is Map ? r['parts'] : null;
    final speed = r is Map ? r['speed'] : null;
    return (
      parts: parts is num ? parts.toInt() : 0,
      done: r is Map && r['done'] == true,
      speed: speed is num && speed > 0 ? speed.toDouble() : defaultSpeed,
    );
  }

  /// One live part's WAV; null while it is not ready yet.
  Future<Uint8List?> liveSpeechPart(String threadId, String messageId, int part) => _orNull(
    () => _api.getBytes('${_live(threadId, messageId)}/$part', receiveTimeout: voiceReceiveTimeout),
  );

  Future<SpeechPlan> speechPlan(String threadId, String messageId) async {
    final r = await _guard(() => _api.get(_speech(threadId, messageId)));
    final parts = r is Map ? r['parts'] : null;
    final speed = r is Map ? r['speed'] : null;
    return (
      parts: parts is num ? parts.toInt() : 0,
      speed: speed is num && speed > 0 ? speed.toDouble() : defaultSpeed,
    );
  }

  Future<Uint8List> speechPart(String threadId, String messageId, int part) => _guard(
    () => _api.getBytes('${_speech(threadId, messageId)}/$part', receiveTimeout: voiceReceiveTimeout),
  );

  Future<Uint8List> sample(String botId, String speaker, String tone) {
    final q = Uri(queryParameters: {'speaker': speaker, 'tone': tone}).query;
    return _guard(
      () => _api.getBytes(
        '/api/bots/${Uri.encodeComponent(botId)}/voice/sample?$q',
        receiveTimeout: voiceReceiveTimeout,
      ),
    );
  }

  String _speech(String threadId, String messageId) =>
      '/api/threads/${Uri.encodeComponent(threadId)}/messages/'
      '${Uri.encodeComponent(messageId)}/speech';

  String _live(String threadId, String messageId) =>
      '/api/threads/${Uri.encodeComponent(threadId)}/live-speech/${Uri.encodeComponent(messageId)}';

  String _call(String threadId) => '/api/threads/${Uri.encodeComponent(threadId)}/call';

  /// The client words a 5xx as "Roost had a problem"; voice says what it is.
  Future<T> _guard<T>(Future<T> Function() call) async {
    try {
      return await call();
    } on ApiException catch (e) {
      throw switch (e.status) {
        503 => const ApiException(voiceOffText, status: 503),
        502 => const ApiException(voiceFailedText, status: 502),
        _ => e,
      };
    }
  }

  /// A 404 is null (not there, or not yet); anything else is still an error.
  Future<T?> _orNull<T>(Future<T> Function() call) async {
    try {
      return await _guard(call);
    } on ApiException catch (e) {
      if (e.status == 404) return null;
      rethrow;
    }
  }

  /// Best effort: whatever went wrong stays quiet.
  Future<void> _quiet(Future<Object?> Function() call) async {
    try {
      await call();
    } on ApiException {
      // An older gateway, or no answer: the call goes on without it.
    }
  }
}

final voiceApiProvider = Provider<VoiceApi>((ref) => VoiceApi(ref.watch(apiClientProvider)));

/// Asked again whenever a screen that needs it opens, the app comes back to
/// the front, or the composer empties. An error stays an error, so the
/// screens can tell "not asked yet" from "the server said no".
final voiceInfoProvider = FutureProvider.autoDispose<VoiceInfo>(
  (ref) => ref.read(voiceApiProvider).info(),
);

/// Voice is assumed until the server says otherwise: true while the answer
/// loads or when no answer came at all (a sleeping Mac, a lost tailnet),
/// false only when the gateway answered that voice is off or has no voice
/// route. The call's own warm step says "Voice isn't running on your Mac
/// yet." when it is really off.
final voiceAvailableProvider = Provider.autoDispose<bool>((ref) {
  final info = ref.watch(voiceInfoProvider);
  if (info.hasValue) return info.value!.available;
  final error = info.error;
  if (error != null) return error is ApiException && error.status == null;
  return true;
});
