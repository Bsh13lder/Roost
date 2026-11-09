import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../theme/accent.dart';
import '../../theme/tokens.dart';

const _swatchSize = 40.0;
const _ringWidth = 2.0;

/// A row of the six accent colours; a tap applies one at once.
class AccentSwatches extends ConsumerWidget {
  const AccentSwatches({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final chosen = ref.watch(accentProvider);
    return Wrap(
      spacing: Tokens.space3,
      runSpacing: Tokens.space3,
      children: [
        for (final choice in Tokens.accents)
          _Swatch(
            choice: choice,
            selected: choice.id == chosen.id,
            onTap: () => ref.read(accentProvider.notifier).choose(choice),
          ),
      ],
    );
  }
}

class _Swatch extends StatelessWidget {
  const _Swatch({
    required this.choice,
    required this.selected,
    required this.onTap,
  });

  final AccentChoice choice;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      selected: selected,
      label: choice.label,
      child: InkWell(
        key: Key('accent-${choice.id}'),
        customBorder: const CircleBorder(),
        onTap: onTap,
        child: Container(
          width: _swatchSize,
          height: _swatchSize,
          decoration: BoxDecoration(
            color: choice.accent,
            shape: BoxShape.circle,
            border: Border.all(
              color: selected ? Tokens.text : Tokens.border,
              width: _ringWidth,
            ),
          ),
          child: selected
              ? const Icon(Icons.check, color: Tokens.onAccent, size: 20)
              : null,
        ),
      ),
    );
  }
}
