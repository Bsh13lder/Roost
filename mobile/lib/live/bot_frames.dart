import '../api/models.dart';

typedef Frame = Map<String, dynamic>;

/// Pure reducer: the bots after one `/api/events` frame (the web's
/// `applyFrame` for snapshot, bot_status, bot_updated and bot_removed).
Map<String, Bot> applyBotFrame(Map<String, Bot> bots, Frame frame) {
  switch (frame['type']) {
    case 'snapshot':
      final list = (frame['bots'] as List? ?? const []).cast<Map>();
      return {
        for (final b in list)
          (b['id'] as String): Bot.fromJson(b.cast<String, dynamic>()),
      };
    case 'bot_updated':
      final raw = frame['bot'];
      if (raw is! Map) return bots;
      final bot = Bot.fromJson(raw.cast<String, dynamic>());
      return {...bots, bot.id: bot};
    case 'bot_removed':
      return {...bots}..remove(frame['bot_id']);
    case 'bot_status':
      final bot = bots[frame['bot_id']];
      if (bot == null) return bots;
      final status = Bot.fromJson({
        'id': bot.id,
        'status': frame['status'],
      }).status;
      return {
        ...bots,
        bot.id: bot.withStatus(status, frame['activity'] as String?),
      };
    default:
      return bots;
  }
}

/// A chat's messages after one frame for its thread. Streaming text lives in
/// [streaming] (message id to text so far) until `message_done`.
class ChatFrameResult {
  const ChatFrameResult(this.messages, this.streaming);

  final List<Message> messages;
  final Map<String, String> streaming;
}

ChatFrameResult applyChatFrame(
  String threadId,
  List<Message> messages,
  Map<String, String> streaming,
  Frame frame,
) {
  if (frame['thread_id'] != threadId) {
    return ChatFrameResult(messages, streaming);
  }
  switch (frame['type']) {
    case 'message':
      final raw = frame['message'];
      if (raw is! Map) return ChatFrameResult(messages, streaming);
      return ChatFrameResult(
        _upsert(messages, Message.fromJson(raw.cast<String, dynamic>())),
        streaming,
      );
    case 'text_delta':
      final id = frame['message_id'] as String;
      return ChatFrameResult(messages, {
        ...streaming,
        id: '${streaming[id] ?? ''}${frame['delta'] ?? ''}',
      });
    case 'message_done':
      final id = frame['message_id'] as String;
      final kept = messages.where((m) => m.id != id || m.seq != 0).toList();
      return ChatFrameResult(kept, {...streaming}..remove(id));
    default:
      return ChatFrameResult(messages, streaming);
  }
}

List<Message> _upsert(List<Message> messages, Message next) {
  final i = messages.indexWhere((m) => m.id == next.id);
  if (i == -1) return [...messages, next];
  final replacesPlaceholder = messages[i].seq == 0 && next.seq > 0;
  if (replacesPlaceholder) {
    return [...messages.sublist(0, i), ...messages.sublist(i + 1), next];
  }
  return [for (final m in messages) m.id == next.id ? next : m];
}
