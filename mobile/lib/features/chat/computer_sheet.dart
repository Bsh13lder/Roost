import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../api/models.dart';
import '../../computer/computer_screen.dart';
import '../../live/live_connection.dart';
import '../../theme/accent.dart';
import '../../theme/tokens.dart';
import '../../util/app_time.dart';
import '../../widgets/lensbot.dart';
import 'computer_card.dart';
import 'computer_motion.dart';
import 'computer_steps.dart';

/// What the bot is doing on its computer, and where: every step with its
/// account-zone time, Open computer and Take control. No screen here (owner,
/// 2026-10-26): it lives on the bot's computer screen.
Future<void> showComputerSheet(BuildContext context, ComputerRun run) =>
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      backgroundColor: Tokens.panel,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(
          top: Radius.circular(Tokens.radiusLg),
        ),
      ),
      builder: (_) => DraggableScrollableSheet(
        expand: false,
        initialChildSize: 0.9,
        minChildSize: 0.5,
        maxChildSize: 0.95,
        builder: (_, scroll) => ComputerSheet(run: run, scroll: scroll),
      ),
    );

/// The sheet's way to the screen.
const openComputerLabel = 'Open computer';

/// Closes the sheet and opens the bot's computer screen (view only, with
/// Take control there).
void openComputerFromSheet(BuildContext context, String botId) {
  final router = GoRouter.maybeOf(context);
  final navigator = Navigator.of(context)..pop();
  if (router != null) {
    router.push('/computer/$botId');
    return;
  }
  navigator.push(
    MaterialPageRoute<void>(builder: (_) => ComputerScreen(botId: botId)),
  );
}

class ComputerSheet extends ConsumerWidget {
  const ComputerSheet({super.key, required this.run, required this.scroll});

  /// The run as it was when the sheet opened; newer steps come live.
  final ComputerRun run;
  final ScrollController scroll;

  ComputerRun _latest(ComputerRuns runs) {
    for (final r in runs[run.threadId] ?? const <ComputerRun>[]) {
      if (r.runId == run.runId) return r;
    }
    return run;
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final runs = ref.watch(computerRunsProvider);
    final now = _latest(runs);
    final bot = ref.watch(liveProvider).bots[now.botId];
    final steps = now.steps.reversed.toList();
    return Column(
      key: const Key('computer-sheet'),
      children: [
        Expanded(
          child: CustomScrollView(
            controller: scroll,
            slivers: [
              const SliverToBoxAdapter(child: _Handle()),
              SliverToBoxAdapter(
                child: _Header(run: now, bot: bot),
              ),
              SliverToBoxAdapter(child: _StepsTitle(run: now)),
              SliverList.builder(
                itemCount: steps.length,
                itemBuilder: (_, i) => _StepTile(
                  step: steps[i],
                  current: i == 0 && !now.done,
                  last: i == steps.length - 1,
                ),
              ),
              const SliverToBoxAdapter(child: SizedBox(height: Tokens.space4)),
            ],
          ),
        ),
        _Buttons(botId: now.botId),
      ],
    );
  }
}

class _Handle extends StatelessWidget {
  const _Handle();

  @override
  Widget build(BuildContext context) => Center(
    child: Container(
      margin: const EdgeInsets.only(top: Tokens.space2, bottom: Tokens.space1),
      width: 36,
      height: 4,
      decoration: BoxDecoration(
        color: Tokens.borderStrong,
        borderRadius: BorderRadius.circular(2),
      ),
    ),
  );
}

class _Header extends StatelessWidget {
  const _Header({required this.run, this.bot});
  final ComputerRun run;
  final Bot? bot;

  @override
  Widget build(BuildContext context) {
    final host = run.host;
    final status = run.done
        ? 'Finished'
        : bot == null
        ? 'On it'
        : statusLabel(bot!.status);
    return Padding(
      padding: const EdgeInsets.fromLTRB(
        Tokens.space4,
        Tokens.space2,
        Tokens.space4,
        Tokens.space4,
      ),
      child: Row(
        children: [
          if (bot != null)
            LensbotAvatar(avatar: bot!.avatar, size: 40, status: bot!.status),
          if (bot != null) const SizedBox(width: Tokens.space3),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  bot?.name ?? 'Computer',
                  style: const TextStyle(
                    color: Tokens.text,
                    fontSize: Tokens.fsLead,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  [status, if (host != null) shortHost(host)].join(' · '),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    color: Tokens.textSecondary,
                    fontSize: Tokens.fsLabel,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _StepsTitle extends StatelessWidget {
  const _StepsTitle({required this.run});
  final ComputerRun run;

  @override
  Widget build(BuildContext context) {
    final hidden = run.count - run.steps.length;
    return Padding(
      padding: const EdgeInsets.fromLTRB(
        Tokens.space4,
        Tokens.space5,
        Tokens.space4,
        Tokens.space2,
      ),
      child: Row(
        children: [
          const Text(
            'Steps',
            style: TextStyle(
              color: Tokens.text,
              fontSize: Tokens.fsBody,
              fontWeight: FontWeight.w600,
            ),
          ),
          const Spacer(),
          Text(
            hidden > 0
                ? 'Newest ${run.steps.length} of ${run.count} · ${zoneCity()} time'
                : '${run.count} · ${zoneCity()} time',
            style: const TextStyle(
              color: Tokens.textFaint,
              fontSize: Tokens.fsCaption,
            ),
          ),
        ],
      ),
    );
  }
}

/// One step on the timeline: its icon on the rail, its words and its time.
class _StepTile extends StatelessWidget {
  const _StepTile({
    required this.step,
    required this.current,
    required this.last,
  });
  final ComputerStep step;
  final bool current;
  final bool last;

  @override
  Widget build(BuildContext context) {
    final accent = AccentColors.of(context);
    final iconColor = current ? accent.strong : Tokens.textSecondary;
    return IntrinsicHeight(
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const SizedBox(width: Tokens.space4),
          SizedBox(
            width: 32,
            child: Column(
              children: [
                Container(
                  width: 32,
                  height: 32,
                  decoration: BoxDecoration(
                    color: current ? accent.tint : Tokens.raised,
                    shape: BoxShape.circle,
                    border: Border.all(
                      color: current ? accent.accent : Tokens.border,
                    ),
                  ),
                  child: Icon(stepIcon(step.kind), size: 16, color: iconColor),
                ),
                if (!last)
                  Expanded(child: Container(width: 1.5, color: Tokens.border)),
              ],
            ),
          ),
          const SizedBox(width: Tokens.space3),
          Expanded(
            child: Padding(
              padding: const EdgeInsets.only(top: 6, bottom: Tokens.space4),
              child: Shimmer(
                active: current,
                child: Text(
                  step.line,
                  style: TextStyle(
                    color: current ? Tokens.text : Tokens.textSecondary,
                    fontSize: Tokens.fsBody,
                    height: 1.35,
                  ),
                ),
              ),
            ),
          ),
          const SizedBox(width: Tokens.space3),
          Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Text(
              _clock(step.at),
              style: const TextStyle(
                color: Tokens.textFaint,
                fontSize: Tokens.fsCaption,
                fontFeatures: [FontFeature.tabularFigures()],
              ),
            ),
          ),
          const SizedBox(width: Tokens.space4),
        ],
      ),
    );
  }

  static String _clock(String iso) {
    try {
      return appClock(iso);
    } on FormatException {
      return '';
    }
  }
}

class _Buttons extends StatelessWidget {
  const _Buttons({required this.botId});
  final String botId;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: const BoxDecoration(
        border: Border(top: BorderSide(color: Tokens.border)),
      ),
      child: SafeArea(
        top: false,
        child: Padding(
          padding: const EdgeInsets.all(Tokens.space4),
          child: Row(
            children: [
              Expanded(
                child: OutlinedButton.icon(
                  key: const Key('computer-sheet-open'),
                  style: OutlinedButton.styleFrom(
                    foregroundColor: Tokens.text,
                    side: const BorderSide(color: Tokens.borderStrong),
                  ),
                  icon: const Icon(Icons.desktop_windows_outlined, size: 18),
                  onPressed: () => openComputerFromSheet(context, botId),
                  label: const Text(openComputerLabel),
                ),
              ),
              const SizedBox(width: Tokens.space3),
              Expanded(
                child: FilledButton.icon(
                  icon: const Icon(Icons.pan_tool_alt_outlined, size: 18),
                  onPressed: () {
                    final router = GoRouter.maybeOf(context);
                    Navigator.of(context).pop();
                    router?.push('/computer/$botId?go=control');
                  },
                  label: const Text('Take control'),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
