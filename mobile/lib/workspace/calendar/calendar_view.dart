import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../../api/api_error.dart';
import '../../board/common/widgets.dart';
import '../../board/tasks/task_dates.dart';
import '../../board/tasks/task_models.dart';
import '../../board/tasks/task_repo.dart';
import '../../live/live_connection.dart';
import '../../routines/occurrences.dart';
import '../../theme/tokens.dart';
import '../show_toggles.dart';
import '../workspace_state.dart';
import '../tasks/work_projects.dart';
import 'calendar_legend.dart';
import 'calendar_state.dart';
import 'day_cell.dart';
import 'day_marks.dart';
import 'day_notes_api.dart';
import 'day_panel.dart';
import 'month_grid_view.dart';

const _swipeSpeed = 200.0;

/// The Workspace calendar (clean, 2026-10-26): a month grid of markers only
/// (task dots, a bell, a repeat mark, a bot's initial; swipe or arrows for
/// months, the handle folds it to one week), a one-line legend, and the
/// chosen day's Tasks · Reminders · Routines below. Show hides routines,
/// done tasks or the tasks a bot made, remembered on this phone.
class WorkCalendarView extends ConsumerStatefulWidget {
  const WorkCalendarView({super.key});

  @override
  ConsumerState<WorkCalendarView> createState() => _WorkCalendarViewState();
}

class _WorkCalendarViewState extends ConsumerState<WorkCalendarView> {
  bool _collapsed = false;

  void _shift(int by) {
    final month = shiftMonthBy(ref.read(workMonthProvider), by);
    ref.read(workMonthProvider.notifier).state = month;
    final today = appToday();
    final first = DateTime.parse('$month-01T00:00:00Z');
    ref.read(workDayProvider.notifier).state =
        isoDay(today).startsWith(month) ? today : first;
  }

  void _today() {
    final today = appToday();
    ref.read(workMonthProvider.notifier).state = isoDay(today).substring(0, 7);
    ref.read(workDayProvider.notifier).state = today;
  }

  Future<void> _addNote(DateTime day) async {
    final text = await _askNote(context);
    if (text == null || text.trim().isEmpty) return;
    try {
      await ref.read(dayNotesApiProvider).add(isoDay(day), text.trim());
      ref.invalidate(monthDayNotesProvider);
    } on ApiException catch (e) {
      if (mounted) snack(context, e.message);
    }
  }

  @override
  Widget build(BuildContext context) {
    final month = ref.watch(workMonthProvider);
    final day = ref.watch(workDayProvider);
    final typed = ref.watch(workspaceQueryProvider);
    final tasksAsync = ref.watch(monthTasksProvider(month));
    final all = tasksAsync.value ?? const <TaskItem>[];
    final show = ref.watch(screenTogglesProvider(screenCalendar));
    final tasks = calendarTasks(all, show, typed);
    final notes = ref.watch(monthDayNotesProvider(month)).value ?? const <DayNote>[];
    final routines = show.routines
        ? ref.watch(routineDaysProvider(monthSpan(month))).value ?? const <String, List<RoutineDayEntry>>{}
        : const <String, List<RoutineDayEntry>>{};
    final bots = {
      for (final b in ref.watch(liveProvider).bots.values) b.id: BotTag(name: b.name, color: b.avatar.color),
    };
    final projects = ref.watch(workProjectsProvider).value ?? const <ProjectInfo>[];
    final today = appToday();
    final marks = buildDayMarks(tasks: tasks, routines: routines, today: today);
    return ListView(children: [
      _header(month),
      Padding(
        padding: const EdgeInsets.symmetric(horizontal: Tokens.space3),
        child: GestureDetector(
          onHorizontalDragEnd: (d) {
            final v = d.primaryVelocity ?? 0;
            if (v.abs() > _swipeSpeed) _shift(v < 0 ? 1 : -1);
          },
          child: MonthGridView(
            month: month,
            today: today,
            selected: day,
            marks: marks,
            bots: bots,
            projectColors: {for (final p in projects) p.id: p.color},
            collapsed: _collapsed,
            onPick: (d) => ref.read(workDayProvider.notifier).state = d,
          ),
        ),
      ),
      const CalendarLegend(),
      _handle(),
      const Divider(height: 1, color: Tokens.border),
      if (tasksAsync.hasError) BoardNote(errorText(tasksAsync.error!), error: true),
      DayPanel(
        day: day,
        today: today,
        plan: dayPlan(day, tasks, routines, today),
        notes: notes,
        bots: bots,
        projectNames: {for (final p in projects) p.id: p.name},
        onAddNote: () => _addNote(day),
      ),
    ]);
  }

  Widget _header(String month) => Padding(
        padding: const EdgeInsets.fromLTRB(
            Tokens.space4, 0, Tokens.space2, Tokens.space2),
        child: Row(children: [
          Expanded(
            child: Text(
              DateFormat('MMMM yyyy').format(DateTime.parse('$month-01')),
              style: const TextStyle(
                  fontSize: Tokens.fsHeading, fontWeight: FontWeight.w700),
            ),
          ),
          IconButton(
              key: const Key('month-prev'),
              tooltip: 'Previous month',
              icon: const Icon(Icons.chevron_left),
              onPressed: () => _shift(-1)),
          IconButton(
              key: const Key('month-next'),
              tooltip: 'Next month',
              icon: const Icon(Icons.chevron_right),
              onPressed: () => _shift(1)),
          IconButton(
              key: const Key('month-today'),
              tooltip: 'Today',
              icon: const Icon(Icons.today_outlined),
              onPressed: _today),
          const ShowMenuButton(screen: screenCalendar, options: ShowToggle.values),
        ]),
      );

  Widget _handle() => GestureDetector(
        key: const Key('grid-handle'),
        behavior: HitTestBehavior.opaque,
        onTap: () => setState(() => _collapsed = !_collapsed),
        onVerticalDragEnd: (d) {
          final v = d.primaryVelocity ?? 0;
          if (v != 0) setState(() => _collapsed = v < 0);
        },
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: Tokens.space3),
          child: Center(
            child: Container(
              width: 40,
              height: 4,
              decoration: BoxDecoration(
                color: Tokens.borderStrong,
                borderRadius: BorderRadius.circular(2),
              ),
            ),
          ),
        ),
      );
}

Future<String?> _askNote(BuildContext context) {
  final text = TextEditingController();
  return showDialog<String>(
    context: context,
    builder: (c) => AlertDialog(
      title: const Text('Day note'),
      content: TextField(
        key: const Key('day-note-text'),
        controller: text,
        autofocus: true,
        maxLines: 3,
        decoration: const InputDecoration(hintText: 'A note for this day'),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(c), child: const Text('Cancel')),
        TextButton(
            key: const Key('day-note-save'),
            onPressed: () => Navigator.pop(c, text.text),
            child: const Text('Add')),
      ],
    ),
  ).whenComplete(text.dispose);
}

/// The month's tasks the calendar shows: Show's choices and the typed words.
List<TaskItem> calendarTasks(List<TaskItem> all, ScreenToggles show, String typed) => [
      for (final t in all)
        if ((show.done || !t.isDone) &&
            (show.botMade || t.createdByBot == null) &&
            matchesQuery(t.title, typed))
          t,
    ];

/// A month as the routines' span: its first to its last account-zone day.
RoutineSpan monthSpan(String month, {String? botId}) {
  final first = DateTime.parse('$month-01');
  final last = DateTime.utc(first.year, first.month + 1, 0);
  return (from: isoDay(first), to: isoDay(last), botId: botId);
}
