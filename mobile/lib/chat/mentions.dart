import 'package:flutter/material.dart';

import '../theme/tokens.dart';

class MentionOption {
  const MentionOption(this.id, this.name);
  final String id;
  final String name;
}

/// "@" names one of your other bots; "#" one of your projects (2026-10-26:
/// the server reads "#Name" against your projects and tells the bot).
const mentionBot = '@';
const mentionProject = '#';

const _word = r'[\p{L}\p{N}_.-]*';
RegExp _beforeCaret(String trigger) =>
    RegExp('(?:^|\\s)$trigger($_word)\$', unicode: true);
RegExp _partial(String trigger) => RegExp('$trigger($_word)\$', unicode: true);

/// "@word" (or "#word") right before the caret, at the start or after
/// whitespace, so an e-mail address (me@scout) or "a#1" never opens the
/// list. Null when none.
String? mentionQuery(String textBeforeCaret, [String trigger = mentionBot]) =>
    _beforeCaret(trigger).firstMatch(textBeforeCaret)?.group(1);

/// The text and caret after picking [name] in place of the partial word.
({String text, int caret}) insertMention(String text, int caret, String name,
    [String trigger = mentionBot]) {
  final before =
      text.substring(0, caret).replaceFirst(_partial(trigger), '$trigger$name ');
  return (text: before + text.substring(caret), caret: before.length);
}

/// The options whose name starts with what is typed after "@".
List<MentionOption> matchingOptions(
        String? query, List<MentionOption> options) =>
    query == null
        ? const []
        : [
            for (final o in options)
              if (o.name.toLowerCase().startsWith(query.toLowerCase())) o
          ];

/// The list of bot names over the composer while an @word is being typed.
class MentionList extends StatelessWidget {
  const MentionList(
      {super.key,
      required this.options,
      required this.onPick,
      this.trigger = mentionBot});
  final List<MentionOption> options;
  final String trigger;
  final void Function(MentionOption option) onPick;

  @override
  Widget build(BuildContext context) {
    if (options.isEmpty) return const SizedBox.shrink();
    return Container(
      key: const Key('mention-list'),
      constraints: const BoxConstraints(maxHeight: 180),
      margin: const EdgeInsets.symmetric(horizontal: Tokens.space2),
      decoration: BoxDecoration(
        color: Tokens.overlay,
        border: Border.all(color: Tokens.border),
        borderRadius: BorderRadius.circular(Tokens.radiusMd),
      ),
      child: ListView(
        shrinkWrap: true,
        children: [
          for (final o in options)
            ListTile(
                dense: true,
                title: Text('$trigger${o.name}'),
                onTap: () => onPick(o)),
        ],
      ),
    );
  }
}
