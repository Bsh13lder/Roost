import 'package:flutter/material.dart';

import '../../chat/cards/english_fix_card.dart';
import '../../chat/english_fix.dart';
import '../../theme/tokens.dart';
import '../../voice/mic_controller.dart';

/// Correct what I say (voice tuning D3): above the composer, the cleaned
/// sentence with each fix marked (the wrong words struck through, the right
/// words beside them) and what you said, so you check before you send; Keep
/// my words puts the raw transcript back.
class SpokenFixStrip extends StatelessWidget {
  const SpokenFixStrip({
    super.key,
    required this.correction,
    required this.onKeep,
  });

  final SpokenCorrection correction;
  final VoidCallback onKeep;

  @override
  Widget build(BuildContext context) {
    final fix = EnglishFix(
      messageId: '',
      said: correction.said,
      corrected: correction.corrected,
      fixes: [for (final f in correction.fixes) WordFix(f.wrong, f.right)],
    );
    return Container(
      key: const Key('spoken-fix'),
      margin: const EdgeInsets.fromLTRB(Tokens.space3, 0, Tokens.space3, Tokens.space1),
      padding: const EdgeInsets.symmetric(horizontal: Tokens.space3, vertical: Tokens.space2),
      decoration: BoxDecoration(
        color: Tokens.panel,
        border: Border.all(color: Tokens.border),
        borderRadius: BorderRadius.circular(Tokens.radiusMd),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                const Text('Corrected what you said',
                    style: TextStyle(color: Tokens.textFaint, fontSize: Tokens.fsCaption)),
                const SizedBox(height: Tokens.space1),
                EnglishFixText(fix, fontSize: Tokens.fsLabel),
                Padding(
                  padding: const EdgeInsets.only(top: Tokens.space1),
                  child: Text('You said: ${correction.said}',
                      key: const Key('spoken-fix-said'),
                      style: const TextStyle(color: Tokens.textFaint, fontSize: Tokens.fsCaption)),
                ),
              ],
            ),
          ),
          TextButton(
            key: const Key('keep-my-words'),
            onPressed: onKeep,
            child: const Text('Keep my words'),
          ),
        ],
      ),
    );
  }
}
