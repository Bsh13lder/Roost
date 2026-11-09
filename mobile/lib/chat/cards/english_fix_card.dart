import 'package:flutter/material.dart';

import '../../api/models.dart';
import '../../theme/tokens.dart';
import '../english_fix.dart';

/// Correct my English: a quiet card right under your spoken message with the
/// corrected sentence, each mistake struck through beside the right words,
/// and what you said. It is never sent to a model, never spoken and never a
/// chat-list line; an unreadable body draws nothing.
class EnglishFixCard extends StatelessWidget {
  const EnglishFixCard({super.key, required this.message});

  final Message message;

  @override
  Widget build(BuildContext context) {
    final fix = parseEnglishFix(message.body);
    if (fix == null) return const SizedBox.shrink();
    return Align(
      key: Key('english-fix-${message.id}'),
      alignment: Alignment.centerRight,
      child: Container(
        margin: const EdgeInsets.fromLTRB(
            Tokens.space8 * 2, 0, Tokens.space3, Tokens.space2),
        padding: const EdgeInsets.symmetric(
            horizontal: Tokens.space3, vertical: Tokens.space2),
        decoration: BoxDecoration(
          color: Tokens.panel,
          border: Border.all(color: Tokens.border),
          borderRadius: BorderRadius.circular(Tokens.radiusMd),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            const Padding(
              padding: EdgeInsets.only(bottom: Tokens.space1),
              child: Text('Corrected',
                  style: TextStyle(
                      color: Tokens.textFaint, fontSize: Tokens.fsCaption)),
            ),
            EnglishFixText(fix),
            Padding(
              padding: const EdgeInsets.only(top: Tokens.space1),
              child: Text('You said: ${fix.said}',
                  key: const Key('english-fix-said'),
                  style: const TextStyle(
                      color: Tokens.textFaint, fontSize: Tokens.fsCaption)),
            ),
          ],
        ),
      ),
    );
  }
}

/// The corrected sentence as rich text: plain words in [baseColor], the wrong
/// words struck through in the danger colour, the right words in the success
/// colour; fixes that could not be placed follow as "wrong → right" lines.
class EnglishFixText extends StatelessWidget {
  const EnglishFixText(
    this.fix, {
    super.key,
    this.textAlign = TextAlign.start,
    this.baseColor = Tokens.text,
    this.fontSize = Tokens.fsBody,
  });

  final EnglishFix fix;
  final TextAlign textAlign;
  final Color baseColor;
  final double fontSize;

  @override
  Widget build(BuildContext context) {
    final shown = fixSegments(fix);
    return Column(
      crossAxisAlignment: textAlign == TextAlign.center
          ? CrossAxisAlignment.center
          : CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        Text.rich(
          TextSpan(children: _spans(shown.segments)),
          key: const Key('english-fix-sentence'),
          textAlign: textAlign,
          style: TextStyle(fontSize: fontSize, color: baseColor),
        ),
        for (final f in shown.unplaced)
          Text(arrowLine(f),
              textAlign: textAlign,
              style: TextStyle(fontSize: fontSize, color: Tokens.ok)),
      ],
    );
  }

  List<InlineSpan> _spans(List<FixSegment> segments) => [
        for (final s in segments)
          switch (s.kind) {
            FixPart.plain => TextSpan(text: s.text, style: TextStyle(color: baseColor)),
            FixPart.wrong => TextSpan(
                text: s.text,
                style: const TextStyle(
                    color: Tokens.danger,
                    decoration: TextDecoration.lineThrough,
                    decorationColor: Tokens.danger)),
            FixPart.right => TextSpan(children: [
                const TextSpan(text: ' '),
                TextSpan(
                    text: s.text,
                    style: const TextStyle(
                        color: Tokens.ok, fontWeight: FontWeight.w600)),
              ]),
          },
      ];
}
