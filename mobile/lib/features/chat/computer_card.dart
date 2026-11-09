import 'package:flutter/material.dart';

import '../../theme/accent.dart';
import '../../theme/tokens.dart';
import 'computer_motion.dart';
import 'computer_sheet.dart';
import 'computer_steps.dart';

/// The widest the line grows on a big screen.
const computerCardMaxWidth = 440.0;

/// The icon for a step's kind.
IconData stepIcon(String kind) => switch (kind) {
  'look' => Icons.visibility_outlined,
  'wait' => Icons.hourglass_empty_rounded,
  'scroll' => Icons.swap_vert_rounded,
  'click' => Icons.ads_click_rounded,
  'type' => Icons.keyboard_outlined,
  'key' => Icons.keyboard_return_rounded,
  'open_page' => Icons.public_rounded,
  'open_app' => Icons.apps_rounded,
  'tab' => Icons.tab_outlined,
  _ => Icons.bolt_rounded,
};

/// A run in the chat: one compact line while the bot works, then one quiet
/// done line for every run, the newest too. The chat never shows the screen
/// (owner, 2026-10-26): the steps sheet's Open computer goes to it.
class ComputerRunView extends StatelessWidget {
  const ComputerRunView({super.key, required this.run});

  final ComputerRun run;

  @override
  Widget build(BuildContext context) {
    void open() => showComputerSheet(context, run);
    final swap = AnimatedSwitcher(
      duration: motion(context),
      switchInCurve: Curves.easeOutCubic,
      switchOutCurve: Curves.easeInCubic,
      child: run.done
          ? ComputerDoneLine(
              key: const Key('computer-done'),
              run: run,
              onTap: open,
            )
          : ComputerCard(
              key: const Key('computer-card'),
              run: run,
              onTap: open,
            ),
    );
    // AnimatedSize with no time re-lays itself out mid-layout: skip it then.
    if (reduceMotion(context)) return swap;
    return AnimatedSize(
      duration: cardMotion,
      curve: Curves.easeOutCubic,
      alignment: Alignment.topLeft,
      child: swap,
    );
  }
}

/// The live line, in the activity pill's capsule: the step's icon, the site,
/// the step now in words and its number. A tap opens the steps.
class ComputerCard extends StatelessWidget {
  const ComputerCard({super.key, required this.run, required this.onTap});

  final ComputerRun run;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final accent = AccentColors.of(context);
    return Padding(
      padding: const EdgeInsets.symmetric(
        horizontal: Tokens.space4,
        vertical: Tokens.space1,
      ),
      child: Align(
        alignment: Alignment.centerLeft,
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: computerCardMaxWidth),
          child: Material(
            color: Tokens.panel,
            shape: StadiumBorder(
              side: BorderSide(color: accent.accent.withValues(alpha: 0.3)),
            ),
            clipBehavior: Clip.antiAlias,
            child: InkWell(
              onTap: onTap,
              child: Padding(
                padding: const EdgeInsets.fromLTRB(
                  Tokens.space1 + 2,
                  Tokens.space1 + 2,
                  Tokens.space3,
                  Tokens.space1 + 2,
                ),
                child: _LineRow(run: run),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _LineRow extends StatelessWidget {
  const _LineRow({required this.run});
  final ComputerRun run;

  static const _faint = TextStyle(
    color: Tokens.textFaint,
    fontSize: Tokens.fsCaption,
    fontFeatures: [FontFeature.tabularFigures()],
  );

  @override
  Widget build(BuildContext context) {
    final accent = AccentColors.of(context);
    final step = run.current;
    final host = run.host;
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 28,
          height: 28,
          decoration: BoxDecoration(color: accent.tint, shape: BoxShape.circle),
          child: Icon(stepIcon(step.kind), size: 16, color: accent.strong),
        ),
        const SizedBox(width: Tokens.space2 + 2),
        if (host != null) ...[
          Flexible(
            flex: 2,
            child: Text(
              shortHost(host),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: _faint,
            ),
          ),
          const Padding(
            padding: EdgeInsets.symmetric(horizontal: Tokens.space1 + 2),
            child: Text('·', style: _faint),
          ),
        ],
        Flexible(
          flex: 3,
          child: AnimatedSwitcher(
            duration: motion(context, const Duration(milliseconds: 200)),
            layoutBuilder: (current, previous) => Stack(
              alignment: Alignment.centerLeft,
              children: [...previous, ?current],
            ),
            child: Shimmer(
              key: ValueKey(step.step),
              child: Text(
                step.line,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
                  color: Tokens.text,
                  fontSize: Tokens.fsLabel,
                ),
              ),
            ),
          ),
        ),
        const SizedBox(width: Tokens.space2),
        Text('Step ${run.count}', style: _faint),
        const SizedBox(width: Tokens.space1),
        const Icon(
          Icons.chevron_right_rounded,
          size: 18,
          color: Tokens.textFaint,
        ),
      ],
    );
  }
}

/// After the run: "Used its computer · upwork.com · 6 steps  ›".
class ComputerDoneLine extends StatelessWidget {
  const ComputerDoneLine({super.key, required this.run, required this.onTap});

  final ComputerRun run;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(
        horizontal: Tokens.space4 - Tokens.space2,
        vertical: Tokens.space1,
      ),
      child: Align(
        alignment: Alignment.centerLeft,
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(Tokens.radiusSm),
          child: Padding(
            padding: const EdgeInsets.symmetric(
              horizontal: Tokens.space2,
              vertical: Tokens.space2 - 2,
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Icon(
                  Icons.desktop_windows_outlined,
                  size: 15,
                  color: Tokens.textFaint,
                ),
                const SizedBox(width: Tokens.space2),
                Flexible(
                  child: Text(
                    doneLine(run),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      color: Tokens.textSecondary,
                      fontSize: Tokens.fsLabel,
                    ),
                  ),
                ),
                const SizedBox(width: Tokens.space1),
                const Icon(
                  Icons.chevron_right_rounded,
                  size: 18,
                  color: Tokens.textFaint,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
