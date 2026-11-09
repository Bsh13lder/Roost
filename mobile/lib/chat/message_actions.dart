import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../api/models.dart';
import '../theme/tokens.dart';
import 'cards/card_base.dart' show decodeBody;
import 'web_mark.dart';
import 'reactions.dart';

/// What the long-press menu can do: pick a tapback (null clears) or Reply.
typedef ReactCallback = void Function(Message message, String? key);

/// The long-press menu: five tapbacks, Reply and Copy. Copy copies
/// [copyText] (what the chat shows) when given, else the message's body.
Future<void> showMessageActions(
  BuildContext context, {
  required Message message,
  String? reaction,
  ReactCallback? onReact,
  void Function(Message message)? onReply,
  String? copyText,
  void Function(Message message)? onReadAloud,
  bool reading = false,
}) {
  return showModalBottomSheet<void>(
    context: context,
    builder: (sheet) => SafeArea(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (onReact != null)
            Padding(
              padding: const EdgeInsets.all(Tokens.space3),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                children: [
                  for (final e in reactionGlyphs.entries)
                    IconButton(
                      tooltip: e.value.label,
                      isSelected: reaction == e.key,
                      onPressed: () {
                        Navigator.pop(sheet);
                        onReact(message, reaction == e.key ? null : e.key);
                      },
                      icon: Text(e.value.glyph,
                          style: const TextStyle(fontSize: 24)),
                    ),
                ],
              ),
            ),
          if (onReply != null && canReplyTo(message))
            ListTile(
              leading: const Icon(Icons.reply_rounded),
              title: const Text('Reply'),
              onTap: () {
                Navigator.pop(sheet);
                onReply(message);
              },
            ),
          if (onReadAloud != null)
            ListTile(
              key: const Key('menu-read-aloud'),
              leading: Icon(reading
                  ? Icons.stop_circle_outlined
                  : Icons.volume_up_outlined),
              title: Text(reading ? 'Stop reading' : 'Read aloud'),
              onTap: () {
                Navigator.pop(sheet);
                onReadAloud(message);
              },
            ),
          ListTile(
            leading: const Icon(Icons.copy_rounded),
            title: const Text('Copy'),
            onTap: () {
              Clipboard.setData(ClipboardData(text: copyText ?? message.body));
              Navigator.pop(sheet);
            },
          ),
        ],
      ),
    ),
  );
}

/// The quote above a message that answers another.
class ReplyQuote extends StatelessWidget {
  const ReplyQuote({super.key, required this.quote, this.tainted = false});
  final String quote;
  final bool tainted;

  @override
  Widget build(BuildContext context) => Container(
        margin: const EdgeInsets.only(bottom: Tokens.space1),
        padding: const EdgeInsets.only(left: Tokens.space2),
        decoration: const BoxDecoration(
            border: Border(left: BorderSide(color: Tokens.borderStrong, width: 2))),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(quote,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(
                  color: Tokens.textFaint, fontSize: Tokens.fsLabel)),
          if (tainted) const WebMark(),
        ]),
      );
}

/// "Replying to …" over the composer, × drops it.
class ReplyChip extends StatelessWidget {
  const ReplyChip({super.key, required this.quote, required this.onCancel});
  final String quote;
  final VoidCallback onCancel;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.symmetric(
            horizontal: Tokens.space4, vertical: Tokens.space1),
        child: Row(children: [
          const Text('Replying to ',
              style:
                  TextStyle(color: Tokens.textFaint, fontSize: Tokens.fsLabel)),
          Expanded(
            child: Text(quote,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
                    color: Tokens.textSecondary, fontSize: Tokens.fsLabel)),
          ),
          IconButton(
              tooltip: 'Cancel reply',
              iconSize: 18,
              onPressed: onCancel,
              icon: const Icon(Icons.close_rounded)),
        ]),
      );
}

/// The words a reply quotes. A Stuck card (its Reply button) is quoted by its
/// host alone, in the server's fixed words (roost/stuck/texts.py
/// stuck_quote): its note may come from a web page.
String quoteSource(Message m) {
  if (m.kind != 'stuck') return m.body;
  final data = decodeBody(m.body);
  final host = data?['host'] is String ? data!['host'] as String : '';
  if (data?['sign_in'] == true) {
    return host.isEmpty
        ? 'Waiting for you to sign in'
        : 'Waiting for you to sign in to $host';
  }
  return host.isEmpty ? 'Needs your help' : 'Stuck on $host';
}

/// One line of at most 120 characters, an ellipsis when cut.
String quotePreview(String text) {
  final flat = text.split(RegExp(r'\s+')).where((s) => s.isNotEmpty).join(' ');
  return flat.length <= 120 ? flat : '${flat.substring(0, 119).trimRight()}…';
}
