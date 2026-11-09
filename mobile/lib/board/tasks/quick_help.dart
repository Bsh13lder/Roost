import 'package:flutter/material.dart';

import '../../theme/accent.dart';
import '../../theme/tokens.dart';
import 'quick_help_tokens.dart';

/// The "?" beside the quick line: every token it reads, with an English and
/// a Spanish example.
Future<void> showQuickHelp(BuildContext context) => showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (_) => DraggableScrollableSheet(
        expand: false,
        initialChildSize: 0.7,
        maxChildSize: 0.92,
        builder: (context, scroll) => ListView(
          controller: scroll,
          padding: const EdgeInsets.fromLTRB(
              Tokens.space4, 0, Tokens.space4, Tokens.space6),
          children: [
            const Text('Quick line help',
                style: TextStyle(fontSize: Tokens.fsHeading, fontWeight: FontWeight.w600)),
            const SizedBox(height: Tokens.space1),
            const Text("Type it all in one line. A chip's × puts its words back in the title.",
                style: TextStyle(fontSize: Tokens.fsLabel, color: Tokens.textSecondary)),
            const SizedBox(height: Tokens.space3),
            for (final t in taskTokens) _HelpRow(t),
          ],
        ),
      ),
    );

class _HelpRow extends StatelessWidget {
  const _HelpRow(this.token);

  final HelpToken token;

  @override
  Widget build(BuildContext context) {
    const faint = TextStyle(fontSize: Tokens.fsCaption, color: Tokens.textSecondary);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: Tokens.space2),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Container(
            padding: const EdgeInsets.symmetric(horizontal: Tokens.space2, vertical: 2),
            decoration: BoxDecoration(
              color: AccentColors.of(context).tint,
              borderRadius: BorderRadius.circular(Tokens.radiusSm),
            ),
            child: Text(token.token,
                style: TextStyle(
                    fontSize: Tokens.fsLabel,
                    fontFamily: 'monospace',
                    color: AccentColors.of(context).strong)),
          ),
          const SizedBox(width: Tokens.space2),
          Expanded(child: Text(token.means, style: const TextStyle(fontSize: Tokens.fsLabel))),
        ]),
        const SizedBox(height: Tokens.space1),
        Text('EN  ${token.en}', style: faint),
        Text('ES  ${token.es}', style: faint),
      ]),
    );
  }
}
