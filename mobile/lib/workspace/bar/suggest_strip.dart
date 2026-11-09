import 'package:flutter/material.dart';

import '../../board/tasks/quick_suggest.dart';
import '../../theme/accent.dart';
import '../../theme/tokens.dart';

/// What could finish the token being typed, one tap each, in a quiet row
/// above the bar.
class SuggestStrip extends StatelessWidget {
  const SuggestStrip({super.key, required this.options, required this.onPick});

  final List<SuggestOption> options;
  final ValueChanged<SuggestOption> onPick;

  @override
  Widget build(BuildContext context) {
    final accent = AccentColors.of(context);
    return SizedBox(
      key: const Key('suggest-strip'),
      height: 34,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        itemCount: options.length,
        separatorBuilder: (_, _) => const SizedBox(width: Tokens.space2),
        itemBuilder: (context, i) {
          final o = options[i];
          return Material(
            color: i == 0 ? accent.tint : Tokens.raised,
            borderRadius: BorderRadius.circular(Tokens.radiusLg),
            child: InkWell(
              key: Key('suggest-${o.key}'),
              borderRadius: BorderRadius.circular(Tokens.radiusLg),
              onTap: () => onPick(o),
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: Tokens.space3),
                child: Row(mainAxisSize: MainAxisSize.min, children: [
                  Text(o.insert,
                      style: TextStyle(
                          fontSize: Tokens.fsLabel,
                          color: i == 0 ? accent.strong : Tokens.text)),
                  if (o.hint != null) ...[
                    const SizedBox(width: Tokens.space1),
                    Text(o.hint!,
                        style: const TextStyle(
                            fontSize: Tokens.fsCaption, color: Tokens.textFaint)),
                  ],
                ]),
              ),
            ),
          );
        },
      ),
    );
  }
}
