import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../api/providers.dart';

/// The shortest search the server is asked about.
const chatSearchMinChars = 2;

/// How long typing pauses before the server is asked.
const chatSearchDebounce = Duration(milliseconds: 350);

/// One message hit from `GET /api/chats/search`. The snippet is plain text.
class ChatHit {
  const ChatHit({
    required this.chatKind,
    required this.chatId,
    required this.name,
    required this.messageId,
    required this.snippet,
    required this.createdAt,
    required this.fromYou,
  });

  factory ChatHit.fromJson(Map<String, dynamic> j) => ChatHit(
        chatKind: '${j['chat_kind'] ?? ''}',
        chatId: '${j['chat_id'] ?? ''}',
        name: '${j['name'] ?? ''}',
        messageId: '${j['message_id'] ?? ''}',
        snippet: '${j['snippet'] ?? ''}',
        createdAt: '${j['created_at'] ?? ''}',
        fromYou: j['from_you'] == true,
      );

  final String chatKind, chatId, name, messageId, snippet, createdAt;
  final bool fromYou;

  bool get isBot => chatKind == 'bot';
}

List<ChatHit> parseChatHits(Object? data) => [
      if (data is Map)
        for (final r in (data['results'] as List? ?? const []))
          if (r is Map) ChatHit.fromJson(r.cast<String, dynamic>()),
    ];

/// Message hits for a (debounced) query; empty under the minimum length.
final chatSearchProvider =
    FutureProvider.family<List<ChatHit>, String>((ref, q) async {
  final query = q.trim();
  if (query.length < chatSearchMinChars) return const [];
  final data = await ref
      .watch(apiClientProvider)
      .get('/api/chats/search?q=${Uri.encodeQueryComponent(query)}');
  return parseChatHits(data);
});
