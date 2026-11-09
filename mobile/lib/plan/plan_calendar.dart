import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../board/tasks/task_dates.dart';
import '../board/tasks/task_models.dart';
import '../board/tasks/task_repo.dart';
import '../routines/occurrences.dart';
import '../theme/accent.dart';
import '../theme/tokens.dart';
import '../workspace/calendar/calendar_legend.dart';
import '../workspace/calendar/calendar_state.dart' show shiftMonthBy;
import '../workspace/calendar/calendar_view.dart' show monthSpan;
import '../workspace/calendar/day_marks.dart';
import '../workspace/calendar/day_panel.dart';
import '../workspace/calendar/month_grid_view.dart';
import '../workspace/show_toggles.dart';
import 'plan_models.dart';

const _swipeSpeed = 200.0;
const noDateWords = 'No date';

/// The tasks a bot made, out of a month's tasks.
List<TaskItem> botTasks(List<TaskItem> all, String botId) => [
      for (final t in all)
        if (t.createdByBot == botId) t,
    ];

/// How many Plan items sit on each day ("2026-10-23" -> n); dropped ones
/// and, unless [done], finished ones are left out.
Map<String, int> planCounts(List<PlanItem> items, {required bool done}) {
  final out = <String, int>{};
  for (final i in items) {
    final date = i.date;
    if (date == null || i.status == 'dropped' || (!done && i.status == 'done')) continue;
    out[date] = (out[date] ?? 0) + 1;
  }
  return Map.unmodifiable(out);
}

/// A bot's Plan calendar (owner, 2026-10-27: "calendar view"): the same
/// clean month grid as the Workspace's, for this bot only. Its Plan items
/// are accent squares, its tasks dots, its reminders a bell and its
/// routines a repeat mark; the chosen day lists Plan · Tasks · Reminders ·
/// Routines. Show (Routines · Done) is remembered for every Plan.
class PlanCalendarPane extends ConsumerStatefulWidget {
  const PlanCalendarPane({super.key, required this.botId, required this.items});

  final String botId;
  final List<PlanItem> items;

  @override
  ConsumerState<PlanCalendarPane> createState() => _PlanCalendarPaneState();
}

class _PlanCalendarPaneState extends ConsumerState<PlanCalendarPane> {
  late String _month = isoDay(appToday()).substring(0, 7);
  late DateTime _day = appToday();
  bool _collapsed = false;

  void _shift(int by) {
    final month = shiftMonthBy(_month, by);
    final today = appToday();
    setState(() {
      _month = month;
      _day = isoDay(today).startsWith(month) ? today : DateTime.parse('$month-01T00:00:00Z');
    });
  }

  @override
  Widget build(BuildContext context) {
    final show = ref.watch(screenTogglesProvider(screenPlan));
    final all = ref.watch(monthTasksProvider(_month)).value ?? const <TaskItem>[];
    final tasks = [
      for (final t in botTasks(all, widget.botId))
        if (show.done || !t.isDone) t,
    ];
    final routines = show.routines
        ? ref.watch(routineDaysProvider(monthSpan(_month, botId: widget.botId))).value ??
            const <String, List<RoutineDayEntry>>{}
        : const <String, List<RoutineDayEntry>>{};
    final today = appToday();
    final marks = addPlanMarks(
      buildDayMarks(tasks: tasks, routines: routines, today: today),
      planCounts(widget.items, done: show.done),
    );
    final shown = [
      for (final i in widget.items)
        if (i.status != 'dropped' && (show.done || i.status != 'done')) i,
    ];
    final onDay = [
      for (final i in shown)
        if (i.date == isoDay(_day)) i,
    ]..sort((a, b) => (a.time ?? '').compareTo(b.time ?? ''));
    final undated = [
      for (final i in shown)
        if (i.date == null) i,
    ];
    return ListView(children: [
      _header(),
      Padding(
        padding: const EdgeInsets.symmetric(horizontal: Tokens.space3),
        child: GestureDetector(
          onHorizontalDragEnd: (d) {
            final v = d.primaryVelocity ?? 0;
            if (v.abs() > _swipeSpeed) _shift(v < 0 ? 1 : -1);
          },
          child: MonthGridView(
            month: _month,
            today: today,
            selected: _day,
            marks: marks,
            collapsed: _collapsed,
            onPick: (d) => setState(() => _day = d),
          ),
        ),
      ),
      const CalendarLegend(plan: true),
      _handle(),
      const Divider(height: 1, color: Tokens.border),
      DayPanel(
        day: _day,
        today: today,
        plan: dayPlan(_day, tasks, routines, today),
        notes: const [],
        onAddNote: null,
        top: [
          if (onDay.isNotEmpty) ...[
            SectionHead('Plan', onDay.length, key: const Key('panel-plan')),
            for (final i in onDay) PlanItemRow(item: i),
          ],
        ],
      ),
      if (undated.isNotEmpty) ...[
        SectionHead(noDateWords, undated.length, key: const Key('panel-undated')),
        for (final i in undated) PlanItemRow(item: i),
        const SizedBox(height: Tokens.space4),
      ],
    ]);
  }

  Widget _header() => Padding(
        padding: const EdgeInsets.fromLTRB(Tokens.space4, 0, Tokens.space2, Tokens.space2),
        child: Row(children: [
          Expanded(
            child: Text(DateFormat('MMMM yyyy').format(DateTime.parse('$_month-01')),
                style: const TextStyle(fontSize: Tokens.fsHeading, fontWeight: FontWeight.w700)),
          ),
          IconButton(
              key: const Key('plan-month-prev'),
              tooltip: 'Previous month',
              icon: const Icon(Icons.chevron_left),
              onPressed: () => _shift(-1)),
          IconButton(
              key: const Key('plan-month-next'),
              tooltip: 'Next month',
              icon: const Icon(Icons.chevron_right),
              onPressed: () => _shift(1)),
          const ShowMenuButton(screen: screenPlan, options: [ShowToggle.routines, ShowToggle.done]),
        ]),
      );

  Widget _handle() => GestureDetector(
        key: const Key('plan-grid-handle'),
        behavior: HitTestBehavior.opaque,
        onTap: () => setState(() => _collapsed = !_collapsed),
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: Tokens.space2),
          child: Center(
            child: Container(
              width: 40,
              height: 4,
              decoration: BoxDecoration(color: Tokens.borderStrong, borderRadius: BorderRadius.circular(2)),
            ),
          ),
        ),
      );
}

/// One Plan item in the day panel: its time, a status mark and its words.
class PlanItemRow extends StatelessWidget {
  const PlanItemRow({super.key, required this.item});

  final PlanItem item;

  @override
  Widget build(BuildContext context) {
    final done = item.status == 'done';
    const faint = TextStyle(color: Tokens.textFaint, fontSize: Tokens.fsCaption);
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: Tokens.space4, vertical: 2),
      child: Row(children: [
        SizedBox(width: panelClockWidth, child: Text(item.time ?? allDayWords, style: faint)),
        Icon(done ? Icons.check_circle : Icons.radio_button_unchecked,
            size: Tokens.checkSize - 4,
            color: item.status == 'on_it' ? AccentColors.of(context).strong : Tokens.textSecondary),
        const SizedBox(width: Tokens.space2),
        Expanded(
          child: Text(item.text,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                color: done ? Tokens.textFaint : Tokens.text,
                decoration: done ? TextDecoration.lineThrough : null,
              )),
        ),
      ]),
    );
  }
}
