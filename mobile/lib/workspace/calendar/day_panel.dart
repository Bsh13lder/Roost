import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../../board/tasks/task_actions.dart';
import '../../board/tasks/task_drawer.dart';
import '../../board/tasks/task_models.dart';
import '../../board/tasks/task_row_parts.dart';
import '../../routines/occurrences.dart';
import '../../theme/accent.dart';
import '../../theme/tokens.dart';
import 'day_cell.dart';
import 'day_marks.dart';
import 'day_notes_api.dart';

const panelClockWidth = 56.0;
const _gap = SizedBox(width: Tokens.space2);

/// The chosen day under the grid: its notes, then Tasks · Reminders ·
/// Routines, each row an account-zone time, the title, and the bot and project in
/// a quiet line. An empty section is left out. A task opens its drawer.
class DayPanel extends StatelessWidget {
  const DayPanel({
    super.key,
    required this.day,
    required this.today,
    required this.plan,
    required this.notes,
    required this.onAddNote,
    this.bots = const {},
    this.projectNames = const {},
    this.onOpenTask,
    this.top = const [],
  });

  final DateTime day;
  final DateTime today;
  final DayPlan plan;
  final List<DayNote> notes;
  /// Null hides the day-note button (a bot's Plan calendar has no notes).
  final VoidCallback? onAddNote;
  final Map<String, BotTag> bots;
  final Map<String, String> projectNames;

  /// Given: called with a task's id instead of opening the drawer.
  final ValueChanged<String>? onOpenTask;

  /// Rows shown first, after the day's notes (a bot's Plan items).
  final List<Widget> top;

  @override
  Widget build(BuildContext context) {
    final dayNotes = [for (final n in notes) if (n.day == day) n];
    void open(TaskItem t) =>
        onOpenTask == null ? openTaskDrawer(context, t.id) : onOpenTask!(t.id);
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      _head(context),
      for (final n in dayNotes) _note(n),
      ...top,
      if (plan.tasks.isNotEmpty) ...[
        SectionHead('Tasks', plan.tasks.length, key: const Key('panel-tasks')),
        for (final r in plan.tasks)
          _PanelRow(
            key: Key('ptask-${r.task.id}'),
            time: r.time,
            late: r.late,
            task: r.task,
            meta: _meta(r.task),
            leading: _check(context, r.task),
            onTap: () => open(r.task),
          ),
      ],
      if (plan.reminders.isNotEmpty) ...[
        SectionHead('Reminders', plan.reminders.length, key: const Key('panel-reminders')),
        for (final r in plan.reminders)
          _PanelRow(
            key: Key('premind-${r.task.id}'),
            time: r.time,
            task: r.task,
            meta: _meta(r.task),
            leading: const Padding(
              padding: EdgeInsets.symmetric(horizontal: Tokens.space1),
              child: Icon(Icons.notifications_none, size: Tokens.checkSize - 4, color: Tokens.warn),
            ),
            onTap: () => open(r.task),
          ),
      ],
      if (plan.routines.isNotEmpty) ...[
        SectionHead('Routines', plan.routines.length, key: const Key('panel-routines')),
        for (final r in plan.routines) RoutineLine(entry: r, clockWidth: panelClockWidth),
      ],
      if (plan.isEmpty && dayNotes.isEmpty && top.isEmpty)
        const Padding(
          padding: EdgeInsets.all(Tokens.space4),
          child: Text('Nothing on this day.', style: TextStyle(color: Tokens.textSecondary)),
        ),
      const SizedBox(height: Tokens.space4),
    ]);
  }

  /// "Gela · Club": the bot that made it and its project, when known.
  String _meta(TaskItem t) => [
        if (t.createdByBot != null) ?bots[t.createdByBot]?.name,
        if (t.projectId != null) ?projectNames[t.projectId],
      ].join(' · ');

  Widget _check(BuildContext context, TaskItem t) => RoundCheck(
        done: t.isDone,
        onTap: () {
          final a = TaskActions(context);
          t.isDone ? a.reopen(t) : a.done(t);
        },
      );

  Widget _head(BuildContext context) {
    final words = DateFormat('EEE d MMM yyyy').format(day);
    return Padding(
      padding: const EdgeInsets.fromLTRB(Tokens.space4, Tokens.space3, Tokens.space2, 0),
      child: Row(children: [
        Expanded(
          child: Text(day == today ? 'TODAY · $words' : words,
              key: const Key('agenda-head'),
              style: TextStyle(
                  color: AccentColors.of(context).strong,
                  fontWeight: FontWeight.w700,
                  fontSize: Tokens.fsBody)),
        ),
        if (onAddNote != null)
          IconButton(
          key: const Key('add-day-note'),
          tooltip: 'Add a day note',
          icon: const Icon(Icons.bookmark_add_outlined, color: Tokens.textSecondary),
          onPressed: onAddNote,
        ),
      ]),
    );
  }

  Widget _note(DayNote n) => ListTile(
        key: Key('day-note-${n.id}'),
        dense: true,
        leading: const Icon(Icons.bookmark_outline, size: 18, color: Tokens.textSecondary),
        title: Text(n.text),
        subtitle: n.botName == null ? null : Text(n.botName!),
      );
}

class SectionHead extends StatelessWidget {
  const SectionHead(this.title, this.count, {super.key});

  final String title;
  final int count;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.fromLTRB(Tokens.space4, Tokens.space3, Tokens.space4, Tokens.space1),
        child: Text('$title · $count',
            style: const TextStyle(
                color: Tokens.textSecondary, fontSize: Tokens.fsCaption, fontWeight: FontWeight.w700)),
      );
}

class _PanelRow extends StatelessWidget {
  const _PanelRow({
    super.key,
    required this.time,
    required this.task,
    required this.meta,
    required this.leading,
    required this.onTap,
    this.late = false,
  });

  final String time;
  final TaskItem task;
  final String meta;
  final Widget leading;
  final VoidCallback onTap;
  final bool late;

  @override
  Widget build(BuildContext context) {
    final t = task;
    const faint = TextStyle(color: Tokens.textFaint, fontSize: Tokens.fsCaption);
    return InkWell(
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: Tokens.space4, vertical: 2),
        child: Row(children: [
          SizedBox(
            width: panelClockWidth,
            child: Text(time, style: late ? faint.copyWith(color: Tokens.danger) : faint),
          ),
          leading,
          _gap,
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(t.title,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    color: t.isDone ? Tokens.textFaint : Tokens.text,
                    decoration: t.isDone ? TextDecoration.lineThrough : null,
                  )),
              if (meta.isNotEmpty) Text(meta, maxLines: 1, overflow: TextOverflow.ellipsis, style: faint),
            ]),
          ),
        ]),
      ),
    );
  }
}
