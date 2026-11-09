import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../api/api_error.dart';
import '../../api/models.dart';
import '../../api/providers.dart';
import '../../live/bot_frames.dart';
import '../../live/live_connection.dart';
import '../../media/media_ref.dart';
import '../../voice/voice_models.dart';

class ChatState {
  const ChatState({
    this.threadId,
    this.messages = const [],
    this.streaming = const {},
    this.loading = true,
    this.error,
    this.notice,
  });

  final String? threadId;
  final List<Message> messages;
  final Map<String, String> streaming;
  final bool loading;
  final String? error;

  /// A quiet line under the chat, e.g. "Queued, I'll pick it up next".
  final String? notice;

  ChatState copyWith({
    String? threadId,
    List<Message>? messages,
    Map<String, String>? streaming,
    bool? loading,
    String? Function()? error,
    String? Function()? notice,
  }) =>
      ChatState(
        threadId: threadId ?? this.threadId,
        messages: messages ?? this.messages,
        streaming: streaming ?? this.streaming,
        loading: loading ?? this.loading,
        error: error != null ? error() : this.error,
        notice: notice != null ? notice() : this.notice,
      );
}

const queuedNotice = "Queued, I'll pick it up next";

/// One bot's endless chat: opens the thread, loads the messages and follows
/// the live frames for it.
class ChatController extends FamilyNotifier<ChatState, String> {
  late String botId;
  StreamSubscription<Frame>? _sub;

  @override
  ChatState build(String arg) {
    botId = arg;
    ref.onDispose(() => _sub?.cancel());
    Future.microtask(load);
    return const ChatState();
  }

  Future<void> load() async {
    final api = ref.read(apiClientProvider);
    try {
      final thread = await api.post('/api/bots/$botId/chat') as Map;
      final threadId = thread['id'] as String;
      final data = await api.get('/api/threads/$threadId/messages') as List;
      state = state.copyWith(
        threadId: threadId,
        messages: [
          for (final j in data) Message.fromJson((j as Map).cast<String, dynamic>()),
        ],
        loading: false,
        error: () => null,
      );
      _follow(threadId);
    } on ApiException catch (e) {
      state = state.copyWith(loading: false, error: () => e.message);
    }
  }

  void _follow(String threadId) {
    _sub?.cancel();
    _sub = ref.read(frameBusProvider).stream.listen((frame) {
      final next = applyChatFrame(
          threadId, state.messages, state.streaming, frame);
      state = state.copyWith(messages: next.messages, streaming: next.streaming);
    });
  }

  /// Sends your message; the gateway's answer (started, queued, steered).
  /// In a call ([call]) the server beats the call first and skips the steer
  /// debounce. [spoken] says the words came from the voice service as they
  /// are (a call turn, an unedited dictation), so the server may post a
  /// corrected copy. A failure sets [ChatState.error] and is thrown too, so a
  /// caller that waits can act on it; one that doesn't should `.ignore()`.
  Future<SendStatus> send(
    String text, {
    String? replyTo,
    bool call = false,
    bool spoken = false,
    String? heard,
    List<SpeechFix> fixes = const [],
    List<MediaRef> media = const [],
  }) async {
    final threadId = state.threadId;
    final body = text.trim();
    if (threadId == null || (body.isEmpty && media.isEmpty)) return SendStatus.started;
    try {
      final r = await ref.read(apiClientProvider).post('/api/threads/$threadId/messages', {
        'text': body,
        'reply_to': ?replyTo,
        if (call) 'call': true,
        if (spoken) 'spoken': true,
        // Voice tuning D3: the composer already checked the words; the
        // gateway keeps the marks with no second model call.
        if (spoken && heard != null) 'heard': heard,
        if (spoken && heard != null) 'fixes': [for (final f in fixes) f.toJson()],
        if (media.isNotEmpty) 'media_ids': [for (final m in media) m.id],
      }) as Map;
      final status = parseSendStatus(r['status']);
      _addMine(threadId, r['message_id'] as String, body, status, media);
      return status;
    } on ApiException catch (e) {
      state = state.copyWith(error: () => e.message);
      rethrow;
    }
  }

  void _addMine(String threadId, String id, String body, SendStatus status,
      [List<MediaRef> media = const []]) {
    final mine = Message(
      id: id,
      threadId: threadId,
      role: 'user',
      body: body,
      media: media,
      seq: 0,
      createdAt: DateTime.now().toUtc().toIso8601String(),
      kind: 'text',
    );
    final known = state.messages.any((m) => m.id == mine.id);
    state = state.copyWith(
      messages: known ? state.messages : [...state.messages, mine],
      error: () => null,
      notice: () => status == SendStatus.queued ? queuedNotice : null,
    );
  }

  /// A tapback on a message; a null key clears it. The reaction row comes
  /// back as a live message.
  Future<void> react(Message message, String? key) async {
    final threadId = state.threadId;
    if (threadId == null) return;
    try {
      await ref.read(apiClientProvider).put(
          '/api/threads/$threadId/messages/${message.id}/reaction',
          {'key': key});
    } on ApiException catch (e) {
      state = state.copyWith(error: () => e.message);
    }
  }

  Future<void> stop() async {
    try {
      await ref.read(apiClientProvider).post('/api/bots/$botId/stop');
    } on ApiException catch (e) {
      state = state.copyWith(error: () => e.message);
    }
  }
}

final chatProvider =
    NotifierProvider.family<ChatController, ChatState, String>(
  ChatController.new,
);
