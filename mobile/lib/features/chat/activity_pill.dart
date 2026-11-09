import 'package:flutter/material.dart';

import '../../api/models.dart';
import '../../theme/accent.dart';
import '../../theme/tokens.dart';
import '../../util/app_time.dart';
import '../../widgets/working_bot.dart';
import 'activity_icon.dart';
import 'activity_sheet.dart';
import 'chat_flow.dart';
import 'computer_card.dart';
import 'computer_motion.dart';
import 'computer_sheet.dart';
import 'computer_steps.dart';
import 'on_it_lead.dart';
import 'run_steps.dart';
import 'working_timer.dart';

/// The widest the pill grows on a big screen (the computer card's width).
const activityPillMaxWidth = computerCardMaxWidth;

/// A run in the chat: the live pill (and the computer's compact line when it
/// uses the computer) while the bot works, then one quiet line. Never the
/// screen (owner, 2026-10-26).
class ActivityItemView extends StatelessWidget {
  const ActivityItemView({super.key, required this.item, this.avatar});

  final ActivityItem item;

  /// The bot's look: its robot works in the live pill.
  final Avatar? avatar;

  @override
  Widget build(BuildContext context) {
    void open() => showActivitySheet(context, item);
    final computer = item.computer;
    final swap = AnimatedSwitcher(
      duration: motion(context),
      switchInCurve: Curves.easeOutCubic,
      switchOutCurve: Curves.easeInCubic,
      child: item.live
          ? Column(
              key: const Key('activity-live'),
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                ActivityPill(
                  kind: item.run.pillKind,
                  line: item.run.pillLine,
                  working: item.run.pillWorking,
                  avatar: avatar,
                  since: _startOf(item.run),
                  onTap: open,
                ),
                if (computer != null && !computer.done)
                  ComputerCard(run: computer, onTap: () => showComputerSheet(context, computer)),
              ],
            )
          : ActivityDoneLine(
              key: const Key('activity-done'),
              words: item.doneLine,
              usedComputer: computer != null || item.run.steps.any((s) => s.kind == 'computer'),
              onTap: open,
            ),
    );
    if (reduceMotion(context)) return swap;
    return AnimatedSize(
      duration: cardMotion,
      curve: Curves.easeOutCubic,
      alignment: Alignment.topLeft,
      child: swap,
    );
  }
}

/// When a run began, for the live timer; null before its first step.
DateTime? _startOf(ActivityRun run) {
  if (run.steps.isEmpty) return null;
  try {
    return parseServerTime(run.startedAt);
  } on FormatException {
    return null;
  }
}

/// The bot works and no step has come yet: its robot, what it is doing in
/// words (its streamed lead, else its activity, else "Reading your message")
/// and how long it has been at it. Never the words "On it" (owner, 2026-10-27).
class LiveBotPill extends StatefulWidget {
  const LiveBotPill({super.key, required this.bot, this.words});

  final Bot bot;

  /// The reply's streamed "On it: …" lead, when it has come.
  final String? words;

  @override
  State<LiveBotPill> createState() => _LiveBotPillState();
}

class _LiveBotPillState extends State<LiveBotPill> {
  final _since = DateTime.now();

  @override
  Widget build(BuildContext context) => ActivityPill(
        kind: 'think',
        line: workingWords(widget.words ?? widget.bot.activity),
        working: true,
        avatar: widget.bot.avatar,
        since: _since,
      );
}

/// "◌ Browsing web.whatsapp.com…" in a calm capsule that shimmers while it
/// works. With the bot's [avatar], its own robot acts the step out in place of
/// the icon (owner, 2026-10-27), and [since] adds a timer ("12s").
class ActivityPill extends StatelessWidget {
  const ActivityPill({
    super.key,
    required this.kind,
    required this.line,
    this.working = true,
    this.onTap,
    this.avatar,
    this.since,
  });

  final String kind;
  final String line;
  final bool working;
  final VoidCallback? onTap;
  final Avatar? avatar;
  final DateTime? since;

  String get _words {
    final t = line.trim().replaceAll(RegExp(r'[.…]+$'), '');
    return working ? '$t…' : t;
  }

  @override
  Widget build(BuildContext context) {
    final accent = AccentColors.of(context);
    return Padding(
      key: const Key('activity-pill'),
      padding: const EdgeInsets.symmetric(horizontal: Tokens.space4, vertical: Tokens.space1),
      child: Align(
        alignment: Alignment.centerLeft,
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: activityPillMaxWidth),
          child: Material(
            color: Tokens.panel,
            shape: StadiumBorder(side: BorderSide(color: accent.accent.withValues(alpha: 0.3))),
            clipBehavior: Clip.antiAlias,
            child: InkWell(
              onTap: onTap,
              child: Padding(
                padding: const EdgeInsets.fromLTRB(Tokens.space1 + 2, Tokens.space1 + 2,
                    Tokens.space3, Tokens.space1 + 2),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    _mark(context, accent, kind, avatar),
                    const SizedBox(width: Tokens.space2 + 2),
                    Flexible(
                      child: AnimatedSwitcher(
                        duration: motion(context, const Duration(milliseconds: 200)),
                        layoutBuilder: (current, previous) => Stack(
                          alignment: Alignment.centerLeft,
                          children: [...previous, ?current],
                        ),
                        child: Shimmer(
                          key: ValueKey(_words),
                          active: working,
                          child: Text(
                            _words,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(color: Tokens.text, fontSize: Tokens.fsLabel),
                          ),
                        ),
                      ),
                    ),
                    if (since != null) ...[
                      const SizedBox(width: Tokens.space2),
                      WorkingTimer(since: since!),
                    ],
                    if (onTap != null) ...[
                      const SizedBox(width: Tokens.space1),
                      const Icon(Icons.chevron_right_rounded, size: 18, color: Tokens.textFaint),
                    ],
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// The bot's robot at work, else the step's moving icon in a tinted circle.
Widget _mark(BuildContext context, AccentColors accent, String kind, Avatar? avatar) {
  if (avatar != null) return WorkingBot(avatar: avatar, kind: kind);
  return Container(
    width: _iconCircle,
    height: _iconCircle,
    decoration: BoxDecoration(color: accent.tint, shape: BoxShape.circle),
    alignment: Alignment.center,
    child: AnimatedSwitcher(
      duration: motion(context, const Duration(milliseconds: 200)),
      child: ActivityIcon(key: ValueKey(kind), kind: kind, color: accent.strong, size: 16),
    ),
  );
}

const _iconCircle = 28.0;

/// After the run: "Worked for 42 s · 6 steps  ›".
class ActivityDoneLine extends StatelessWidget {
  const ActivityDoneLine({
    super.key,
    required this.words,
    required this.onTap,
    this.usedComputer = false,
  });

  final String words;
  final VoidCallback onTap;
  final bool usedComputer;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.symmetric(
            horizontal: Tokens.space4 - Tokens.space2, vertical: Tokens.space1),
        child: Align(
          alignment: Alignment.centerLeft,
          child: InkWell(
            onTap: onTap,
            borderRadius: BorderRadius.circular(Tokens.radiusSm),
            child: Padding(
              padding: const EdgeInsets.symmetric(
                  horizontal: Tokens.space2, vertical: Tokens.space2 - 2),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(
                    usedComputer ? Icons.desktop_windows_outlined : Icons.auto_awesome_outlined,
                    size: 15,
                    color: Tokens.textFaint,
                  ),
                  const SizedBox(width: Tokens.space2),
                  Flexible(
                    child: Text(
                      words,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(color: Tokens.textSecondary, fontSize: Tokens.fsLabel),
                    ),
                  ),
                  const SizedBox(width: Tokens.space1),
                  const Icon(Icons.chevron_right_rounded, size: 18, color: Tokens.textFaint),
                ],
              ),
            ),
          ),
        ),
      );
}

/// A computer run no run claimed (an older server): its line.
Widget computerRunTile(ComputerRun run) => ComputerRunView(key: ValueKey('run-${run.runId}'), run: run);
