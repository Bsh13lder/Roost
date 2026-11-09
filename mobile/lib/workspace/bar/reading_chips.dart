import 'package:flutter/material.dart';

import '../../board/tasks/quick_chips.dart';
import '../../theme/accent.dart';
import '../../theme/tokens.dart';

/// The server's reading of the line: the title it will add (when it differs
/// from what you typed) and its chips, each with × to put its words back.
class ReadingChips extends StatelessWidget {
  const ReadingChips({
    super.key,
    required this.chips,
    required this.onRemove,
    required this.onConfirmBot,
    this.title,
  });

  final List<QuickChip> chips;
  final String? title;
  final ValueChanged<QuickChip> onRemove;
  final ValueChanged<String> onConfirmBot;

  @override
  Widget build(BuildContext context) {
    return Wrap(
      key: const Key('quick-chips'),
      spacing: Tokens.space2,
      runSpacing: Tokens.space1,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: [
        if (title != null && title!.isNotEmpty)
          Text(title!,
              key: const Key('quick-title'),
              style: const TextStyle(
                  fontSize: Tokens.fsLabel, fontWeight: FontWeight.w600)),
        for (final c in chips) _Chip(c, onRemove: onRemove, onConfirmBot: onConfirmBot),
      ],
    );
  }
}

class _Chip extends StatelessWidget {
  const _Chip(this.chip, {required this.onRemove, required this.onConfirmBot});

  final QuickChip chip;
  final ValueChanged<QuickChip> onRemove;
  final ValueChanged<String> onConfirmBot;

  Color _fill(BuildContext context) => switch (chip.tone) {
        ChipTone.read => AccentColors.of(context).tint,
        ChipTone.ask => Tokens.raised,
        ChipTone.warn => Tokens.raised,
      };

  Color _ink(BuildContext context) => switch (chip.tone) {
        ChipTone.read => AccentColors.of(context).strong,
        ChipTone.ask => Tokens.warn,
        ChipTone.warn => Tokens.textSecondary,
      };

  @override
  Widget build(BuildContext context) {
    final ink = _ink(context);
    final label = Text(chip.label, style: TextStyle(fontSize: Tokens.fsCaption, color: ink));
    final bot = chip.confirmBot;
    return Container(
      key: Key('chip-${chip.key}'),
      padding: EdgeInsets.only(
          left: Tokens.space2, right: chip.removable ? 0 : Tokens.space2),
      decoration: BoxDecoration(
        color: _fill(context),
        borderRadius: BorderRadius.circular(Tokens.radiusLg),
      ),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        if (bot != null)
          InkWell(onTap: () => onConfirmBot(bot), child: label)
        else
          Padding(padding: const EdgeInsets.symmetric(vertical: Tokens.space1), child: label),
        if (chip.removable)
          InkWell(
            key: Key('chip-remove-${chip.key}'),
            customBorder: const CircleBorder(),
            onTap: () => onRemove(chip),
            child: Padding(
              padding: const EdgeInsets.all(Tokens.space1),
              child: Icon(Icons.close, size: 14, color: ink),
            ),
          ),
      ]),
    );
  }
}
