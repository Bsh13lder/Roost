import '../api/models.dart';
import 'cards/card_base.dart';

/// The server's five tapback keys, each with a glyph and its words.
const reactionGlyphs = <String, ({String glyph, String label})>{
  'thumbs_up': (glyph: '👍', label: 'Thumbs up'),
  'heart': (glyph: '❤️', label: 'Heart'),
  'laugh': (glyph: '😂', label: 'Laughing'),
  'check': (glyph: '✅', label: 'Done'),
  'question': (glyph: '❓', label: 'Question'),
};

/// Each message's tapback: the newest reaction row for it wins, and a null
/// key clears it. Returns a new map; the messages are never changed.
Map<String, String> foldReactions(List<Message> messages) {
  final folded = <String, String>{};
  for (final m in messages) {
    if (m.kind != 'reaction') continue;
    final d = decodeBody(m.body);
    final target = d?['target_id'];
    if (target is! String) continue;
    final key = d!['key'];
    if (key == null) {
      folded.remove(target);
    } else if (key is String && reactionGlyphs.containsKey(key)) {
      folded[target] = key;
    }
  }
  return folded;
}

/// Only conversation messages can be quoted (roost/talk/replies.py).
const _replyKinds = {'text', 'card_answer', 'handoff', 'report'};

bool canReplyTo(Message m) =>
    _replyKinds.contains(m.kind) &&
    (m.role == 'user' || m.role == 'bot') &&
    m.seq > 0;
