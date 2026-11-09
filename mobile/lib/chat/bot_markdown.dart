import 'package:flutter/material.dart';
import 'package:flutter_markdown_plus/flutter_markdown_plus.dart';

import '../theme/accent.dart';
import '../theme/tokens.dart';

/// A bot's words as markdown, the one look every bot message shares (a reply
/// and a Report alike). No raw HTML is drawn and no image is ever fetched.
class BotMarkdown extends StatelessWidget {
  const BotMarkdown(this.text, {super.key});
  final String text;

  @override
  Widget build(BuildContext context) => MarkdownBody(
        data: text,
        selectable: true,
        imageBuilder: (uri, title, alt) => Text(
          alt ?? 'image',
          style: const TextStyle(color: Tokens.textFaint),
        ),
        onTapLink: (text, href, title) {},
        styleSheet: MarkdownStyleSheet(
          p: const TextStyle(fontSize: Tokens.fsLead, color: Tokens.text),
          a: TextStyle(color: AccentColors.of(context).strong),
          code: const TextStyle(
            fontFamily: 'monospace',
            backgroundColor: Tokens.raised,
            fontSize: Tokens.fsBody,
          ),
          codeblockDecoration: BoxDecoration(
            color: Tokens.raised,
            borderRadius: BorderRadius.circular(Tokens.radiusSm),
          ),
        ),
      );
}
