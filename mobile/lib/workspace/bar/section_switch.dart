import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../theme/accent.dart';
import '../../theme/tokens.dart';
import '../workspace_state.dart';

const workBarHeight = 52.0;

/// The Tasks · Notes · Calendar switch beside the bar.
class SectionSwitch extends ConsumerWidget {
  const SectionSwitch({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final current = ref.watch(workspaceSectionProvider);
    final accent = AccentColors.of(context).strong;
    return Container(
      height: workBarHeight,
      padding: const EdgeInsets.symmetric(horizontal: Tokens.space1),
      decoration: BoxDecoration(
        color: Tokens.panel,
        borderRadius: BorderRadius.circular(workBarHeight / 2),
        border: Border.all(color: Tokens.border),
      ),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        for (final s in WorkspaceSection.values)
          IconButton(
            key: Key('section-${s.name}'),
            tooltip: s.label,
            isSelected: s == current,
            visualDensity: VisualDensity.compact,
            icon: Icon(s.icon, color: s == current ? accent : Tokens.textSecondary),
            onPressed: () => ref.read(workspaceSectionProvider.notifier).state = s,
          ),
      ]),
    );
  }
}
