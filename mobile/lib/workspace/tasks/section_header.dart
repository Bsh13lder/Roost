import 'package:flutter/material.dart';

import '../../theme/tokens.dart';
import 'task_sections.dart';

/// A section's header: a chevron that turns as it folds, the title in bold
/// (red for Overdue), its count in grey, and an optional text action.
class SectionHeader extends StatelessWidget {
  const SectionHeader({
    super.key,
    required this.section,
    required this.folded,
    required this.onToggle,
    this.action,
  });

  final TaskSection section;
  final bool folded;
  final VoidCallback onToggle;
  final Widget? action;

  @override
  Widget build(BuildContext context) {
    final color = switch (section.tone) {
      SectionTone.late => Tokens.danger,
      SectionTone.done => Tokens.textSecondary,
      SectionTone.normal => Tokens.text,
    };
    return Semantics(
      header: true,
      expanded: !folded,
      child: InkWell(
        onTap: onToggle,
        child: Container(
          padding: const EdgeInsets.fromLTRB(
              Tokens.space2, Tokens.space4, Tokens.space2, Tokens.space2),
          decoration: const BoxDecoration(
            border: Border(bottom: BorderSide(color: Tokens.border)),
          ),
          child: Row(children: [
            AnimatedRotation(
              turns: folded ? -0.25 : 0,
              duration: const Duration(milliseconds: 200),
              child: const Icon(Icons.expand_more,
                  size: 20, color: Tokens.textSecondary),
            ),
            const SizedBox(width: Tokens.space2),
            // On a narrow phone the title gives way (ellipsis), never the action.
            Expanded(
              child: Row(children: [
                Flexible(
                  child: Text(section.title,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                          color: color,
                          fontSize: Tokens.fsLead,
                          fontWeight: FontWeight.w700)),
                ),
                const SizedBox(width: Tokens.space2),
                Text('${section.tasks.length}',
                    style: const TextStyle(
                        color: Tokens.textSecondary, fontSize: Tokens.fsLabel)),
              ]),
            ),
            ?action,
          ]),
        ),
      ),
    );
  }
}
