import 'package:flutter/material.dart';

import '../../theme/accent.dart';
import '../../theme/tokens.dart';

/// One picker button under the reading: what it is and what it opens.
class QuickPick {
  const QuickPick(this.id, this.label, this.icon, this.onTap, {this.on = false});

  final String id;
  final String label;
  final IconData icon;
  final VoidCallback onTap;

  /// Lit when the line already has this detail.
  final bool on;
}

/// Below this width (a 320 dp phone) the picker buttons wrap onto a second
/// line instead of scrolling, so Date, Project and Priority always show.
const quickPickerWrapWidth = 360.0;

/// The one-line row's height.
const _rowHeight = 32.0;

/// Date · Project · Priority · Repeat · Remind, and the "?" help: small
/// buttons that write the same words typing would. A wide bar scrolls them
/// on one line; a narrow phone wraps them, so nothing ever overflows.
class QuickPickerRow extends StatelessWidget {
  const QuickPickerRow({super.key, required this.picks, required this.onHelp});

  final List<QuickPick> picks;
  final VoidCallback onHelp;

  @override
  Widget build(BuildContext context) {
    final help = IconButton(
      key: const Key('qp-help'),
      tooltip: 'Quick line help',
      visualDensity: VisualDensity.compact,
      padding: EdgeInsets.zero,
      constraints: const BoxConstraints.tightFor(width: _rowHeight, height: _rowHeight),
      icon: const Icon(Icons.help_outline, size: 20, color: Tokens.textSecondary),
      onPressed: onHelp,
    );
    return LayoutBuilder(builder: (context, box) {
      if (box.maxWidth < quickPickerWrapWidth) {
        return Wrap(
          key: const Key('qp-row'),
          spacing: Tokens.space2,
          runSpacing: Tokens.space1,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [for (final p in picks) _PickButton(p), help],
        );
      }
      return SizedBox(
        key: const Key('qp-row'),
        height: _rowHeight,
        child: Row(children: [
          Expanded(
            child: SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: Row(children: [
                for (final (i, p) in picks.indexed) ...[
                  if (i > 0) const SizedBox(width: Tokens.space2),
                  _PickButton(p),
                ],
              ]),
            ),
          ),
          help,
        ]),
      );
    });
  }
}

class _PickButton extends StatelessWidget {
  const _PickButton(this.pick);

  final QuickPick pick;

  @override
  Widget build(BuildContext context) {
    final accent = AccentColors.of(context);
    final ink = pick.on ? accent.strong : Tokens.textSecondary;
    return OutlinedButton.icon(
      key: Key('qp-${pick.id}'),
      onPressed: pick.onTap,
      icon: Icon(pick.icon, size: 16, color: ink),
      label: Text(pick.label, style: TextStyle(fontSize: Tokens.fsCaption, color: ink)),
      style: OutlinedButton.styleFrom(
        visualDensity: VisualDensity.compact,
        padding: const EdgeInsets.symmetric(horizontal: Tokens.space3),
        backgroundColor: pick.on ? accent.tint : Tokens.panel,
        side: BorderSide(color: pick.on ? accent.tint : Tokens.border),
        shape: const StadiumBorder(),
        minimumSize: const Size(0, 30),
        tapTargetSize: MaterialTapTargetSize.shrinkWrap,
      ),
    );
  }
}
