import 'package:flutter/material.dart';

import '../theme/tokens.dart';

const webMarkName = 'From web content';
const webMarkExplained = 'Part of this came from a web page. Roost limits '
    'what the bot can do after reading it, so check it before you act on it.';

/// The "from web content" mark in the chat (2026-10-26, owner: "lets upgrade
/// little the quality of that web content mark. Up is ugly"): a small quiet
/// chip, a globe and "Web", under the text it marks. A tap says what it means.
class WebMark extends StatelessWidget {
  const WebMark({super.key});

  @override
  Widget build(BuildContext context) => Semantics(
        label: webMarkName,
        button: true,
        excludeSemantics: true,
        child: Tooltip(
          key: const Key('web-mark'),
          message: webMarkExplained,
          triggerMode: TooltipTriggerMode.tap,
          showDuration: const Duration(seconds: 6),
          child: Container(
            margin: const EdgeInsets.only(top: Tokens.space1),
            padding: const EdgeInsets.symmetric(
                horizontal: Tokens.space2, vertical: 2),
            decoration: BoxDecoration(
              border: Border.all(color: Tokens.border),
              borderRadius: BorderRadius.circular(Tokens.radiusLg),
            ),
            child: const Row(mainAxisSize: MainAxisSize.min, children: [
              Icon(Icons.public, size: 12, color: Tokens.textFaint),
              SizedBox(width: Tokens.space1),
              Text('Web',
                  style: TextStyle(
                      color: Tokens.textFaint, fontSize: Tokens.fsCaption)),
            ]),
          ),
        ),
      );
}
