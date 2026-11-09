import 'package:flutter/material.dart';

import '../theme/tokens.dart';

/// The "?" sheet: the same sections as Grok's, for this screen's gestures.
const helpSections = <(String, String)>[
  ('Take control',
      'Press Take control to run the computer yourself. The bot waits until you press I\'m done.'),
  ('Scroll', 'Drag with two fingers. Up reads further down the page.'),
  ('Click and drag', 'Tap to click. Press and move one finger to drag.'),
  ('Trackpad',
      'Press the mouse button at the top to move a pointer with one finger, like a laptop. Tap anywhere to click where the pointer is. Press it again for direct touch.'),
  ('Right-click', 'Press and hold, or tap with two fingers.'),
  ('Zoom in', 'Pinch with two fingers. When zoomed, two fingers move the view.'),
  ('Type',
      'Press the keyboard button and type. What you type goes to the computer and is never saved here.'),
  ('I\'m done',
      'Gives the computer back. You can say which account you used, and whether to stay signed in.'),
];

Future<void> showComputerHelp(BuildContext context) => showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Tokens.panel,
      builder: (_) => SafeArea(
        child: ListView(
          shrinkWrap: true,
          padding: const EdgeInsets.all(Tokens.space4),
          children: [
            const Text('Using the computer',
                style: TextStyle(
                    fontSize: Tokens.fsHeading, fontWeight: FontWeight.w600)),
            for (final (title, body) in helpSections)
              Padding(
                padding: const EdgeInsets.only(top: Tokens.space3),
                child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(title,
                          style: const TextStyle(fontWeight: FontWeight.w600)),
                      Text(body,
                          style: const TextStyle(color: Tokens.textSecondary)),
                    ]),
              ),
          ],
        ),
      ),
    );
