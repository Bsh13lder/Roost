import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../api/models.dart';
import '../../chat/web_mark.dart';
import '../../live/live_connection.dart';
import '../../theme/accent.dart';
import '../../theme/tokens.dart';
import '../../util/app_time.dart';
import '../../widgets/lensbot.dart';
import 'activity_icon.dart';
import 'chat_flow.dart';
import 'computer_motion.dart';
import 'computer_sheet.dart';
import 'run_steps.dart';

/// What the bot did in a run, in plain words: every step with its account-zone
/// time, and the raw lines only inside a closed Technical details fold.
Future<void> showActivitySheet(BuildContext context, ActivityItem item) =>
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      backgroundColor: Tokens.panel,
      shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(Tokens.radiusLg))),
      builder: (_) => DraggableScrollableSheet(
        expand: false,
        initialChildSize: 0.7,
        minChildSize: 0.4,
        maxChildSize: 0.95,
        builder: (_, scroll) => ActivitySheet(item: item, scroll: scroll),
      ),
    );

/// One line on the timeline.
class SheetEntry {
  const SheetEntry(this.kind, this.line, this.at,
      {this.current = false, this.failed = false, this.tainted = false});
  final String kind;
  final String line;
  final String at;
  final bool current;
  final bool failed;

  /// A note only: the Web mark.
  final bool tainted;

  bool get isNote => kind == noteKind;
}

/// The run's steps, its folded notes and (with no steps of its own) its
/// computer steps, oldest first; the newest step glows while it runs.
List<SheetEntry> sheetEntries(ActivityItem item) {
  final run = item.run;
  final entries = <SheetEntry>[
    for (final s in run.steps) SheetEntry(s.kind, s.line, s.at, failed: s.failed, tainted: s.tainted),
    for (final n in item.notes) SheetEntry(n.kind, n.line, n.at),
    if (run.steps.isEmpty)
      for (final c in item.computer?.steps ?? const []) SheetEntry('computer', c.line, c.at),
  ];
  final sorted = [...entries]..sort((a, b) => _ms(a.at).compareTo(_ms(b.at)));
  if (!item.live || sorted.isEmpty || sorted.last.isNote) return sorted;
  final last = sorted.last;
  return [
    ...sorted.sublist(0, sorted.length - 1),
    SheetEntry(last.kind, last.line, last.at, current: true, failed: last.failed),
  ];
}

int _ms(String iso) {
  try {
    return parseServerTime(iso).millisecondsSinceEpoch;
  } on FormatException {
    return 0;
  }
}

class ActivitySheet extends ConsumerWidget {
  const ActivitySheet({super.key, required this.item, required this.scroll});

  final ActivityItem item;
  final ScrollController scroll;

  ActivityItem _latest(ActivityRuns runs) {
    for (final r in runs[item.run.threadId] ?? const <ActivityRun>[]) {
      if (r.runId == item.run.runId) {
        return ActivityItem(run: r, computer: item.computer, notes: item.notes);
      }
    }
    return item;
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final now = _latest(ref.watch(activityRunsProvider));
    final botId = now.run.botId.isNotEmpty ? now.run.botId : now.computer?.botId;
    final bot = botId == null ? null : ref.watch(liveProvider).bots[botId];
    final entries = sheetEntries(now);
    final raw = [for (final n in now.notes) ?n.raw];
    return Column(
      key: const Key('activity-sheet'),
      children: [
        Expanded(
          child: CustomScrollView(
            controller: scroll,
            slivers: [
              const SliverToBoxAdapter(child: _Handle()),
              SliverToBoxAdapter(child: _Header(item: now, bot: bot)),
              SliverList.builder(
                itemCount: entries.length,
                itemBuilder: (_, i) => _EntryTile(entry: entries[i], last: i == entries.length - 1),
              ),
              if (raw.isNotEmpty) SliverToBoxAdapter(child: _Technical(lines: raw)),
              const SliverToBoxAdapter(child: SizedBox(height: Tokens.space4)),
            ],
          ),
        ),
        _Buttons(botId: botId, computer: now.computer != null),
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
              color: Tokens.borderStrong, borderRadius: BorderRadius.circular(2)),
        ),
      );
}

class _Header extends StatelessWidget {
  const _Header({required this.item, this.bot});
  final ActivityItem item;
  final Bot? bot;

  @override
  Widget build(BuildContext context) {
    final name = bot?.name ?? 'The bot';
    final title = item.live ? '$name is working' : 'What $name did';
    final sub = item.live
        ? item.run.pillLine
        : item.doneLine;
    return Padding(
      padding: const EdgeInsets.fromLTRB(Tokens.space4, Tokens.space3, Tokens.space4, Tokens.space4),
      child: Row(
        children: [
          if (bot != null) LensbotAvatar(avatar: bot!.avatar, size: 40, star: bot!.isPrimary),
          if (bot != null) const SizedBox(width: Tokens.space3),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title,
                    style: const TextStyle(
                        color: Tokens.text, fontSize: Tokens.fsLead, fontWeight: FontWeight.w600)),
                const SizedBox(height: 2),
                Shimmer(
                  active: item.live,
                  child: Text(sub,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(color: Tokens.textSecondary, fontSize: Tokens.fsLabel)),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// One step on the rail: its icon, its words and its account-zone time.
class _EntryTile extends StatelessWidget {
  const _EntryTile({required this.entry, required this.last});
  final SheetEntry entry;
  final bool last;

  @override
  Widget build(BuildContext context) {
    final accent = AccentColors.of(context);
    final on = entry.current;
    final color = entry.failed ? Tokens.dangerText : (on ? accent.strong : Tokens.textSecondary);
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
                    color: on ? accent.tint : Tokens.raised,
                    shape: BoxShape.circle,
                    border: Border.all(color: on ? accent.accent : Tokens.border),
                  ),
                  alignment: Alignment.center,
                  child: on
                      ? ActivityIcon(kind: entry.kind, color: color, size: 16)
                      : Icon(activityIcon(entry.kind), size: 16, color: color),
                ),
                if (!last) Expanded(child: Container(width: 1.5, color: Tokens.border)),
              ],
            ),
          ),
          const SizedBox(width: Tokens.space3),
          Expanded(
            child: Padding(
              padding: const EdgeInsets.only(top: 6, bottom: Tokens.space4),
              child: entry.isNote
                  ? _NoteLine(entry: entry)
                  : Shimmer(
                      active: on,
                      child: Text(entry.line,
                          style: TextStyle(
                              color: on ? Tokens.text : Tokens.textSecondary,
                              fontSize: Tokens.fsBody,
                              height: 1.35)),
                    ),
            ),
          ),
          const SizedBox(width: Tokens.space3),
          Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Text(_clock(entry.at),
                style: const TextStyle(
                    color: Tokens.textFaint,
                    fontSize: Tokens.fsCaption,
                    fontFeatures: [FontFeature.tabularFigures()])),
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

/// A note (owner, 2026-11-04): the bot's own words between steps, a quiet
/// sentence on the rail, with the Web mark when the run had read a page.
class _NoteLine extends StatelessWidget {
  const _NoteLine({required this.entry});
  final SheetEntry entry;

  @override
  Widget build(BuildContext context) => Column(
        key: const Key('run-note'),
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(entry.line,
              style: const TextStyle(
                  color: Tokens.textSecondary,
                  fontSize: Tokens.fsBody,
                  fontStyle: FontStyle.italic,
                  height: 1.35)),
          if (entry.tainted) const WebMark(),
        ],
      );
}

/// The raw lines, closed until you open them.
class _Technical extends StatelessWidget {
  const _Technical({required this.lines});
  final List<String> lines;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.symmetric(horizontal: Tokens.space2),
        child: Theme(
          data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
          child: ExpansionTile(
            key: const Key('technical-details'),
            dense: true,
            tilePadding: const EdgeInsets.symmetric(horizontal: Tokens.space2),
            title: const Text('Technical details',
                style: TextStyle(color: Tokens.textFaint, fontSize: Tokens.fsCaption)),
            children: [
              Container(
                width: double.infinity,
                margin: const EdgeInsets.fromLTRB(Tokens.space2, 0, Tokens.space2, Tokens.space2),
                padding: const EdgeInsets.all(Tokens.space3),
                decoration: BoxDecoration(
                    color: Tokens.raised, borderRadius: BorderRadius.circular(Tokens.radiusSm)),
                child: SelectableText(lines.join('\n'),
                    style: const TextStyle(
                        fontFamily: 'monospace', fontSize: Tokens.fsCaption, color: Tokens.textSecondary)),
              ),
            ],
          ),
        ),
      );
}

class _Buttons extends StatelessWidget {
  const _Buttons({this.botId, this.computer = false});
  final String? botId;
  final bool computer;

  @override
  Widget build(BuildContext context) => SafeArea(
        top: false,
        child: Container(
          decoration: const BoxDecoration(border: Border(top: BorderSide(color: Tokens.border))),
          padding: const EdgeInsets.fromLTRB(Tokens.space4, Tokens.space3, Tokens.space4, Tokens.space3),
          child: Row(
            children: [
              Expanded(
                child: OutlinedButton(
                  key: const Key('activity-close'),
                  onPressed: () => Navigator.of(context).pop(),
                  child: const Text('Close'),
                ),
              ),
              if (computer && botId != null) ...[
                const SizedBox(width: Tokens.space3),
                Expanded(
                  child: FilledButton.icon(
                    key: const Key('activity-open-computer'),
                    onPressed: () => openComputerFromSheet(context, botId!),
                    icon: const Icon(Icons.desktop_windows_outlined, size: 18),
                    label: const Text(openComputerLabel),
                  ),
                ),
              ],
            ],
          ),
        ),
      );
}
