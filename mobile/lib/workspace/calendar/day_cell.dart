import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../../board/common/widgets.dart';
import '../../board/tasks/task_models.dart';
import '../../theme/accent.dart';
import '../../theme/tokens.dart';
import '../tasks/todo_check.dart';
import 'day_marks.dart';

/// At most this many task dots in a day cell; the rest is "+N".
const maxCellDots = 3;
const _cellHeight = 58.0;
const _dot = 6.0;
const _icon = 11.0;
const _initial = 13.0;
const _tinyFont = 9.0;
const _moreFont = 10.0;

/// A bot as the calendar marks it: its name and avatar colour ("#RRGGBB").
@immutable
class BotTag {
  const BotTag({required this.name, required this.color});
  final String name;
  final String color;

  String get initial => name.isEmpty ? '?' : name.characters.first.toUpperCase();
}

/// A task dot's colour: red when late, urgent and high in their priority's
/// colour, otherwise the project's, else a calm grey.
Color dotTone(TaskItem t, DateTime today, Map<String, String?> projectColors) {
  if (isLate(t, today)) return Tokens.danger;
  if (t.priority == 'urgent' || t.priority == 'high') return priorityTone(t.priority);
  final hex = t.projectId == null ? null : projectColors[t.projectId];
  return hex == null ? Tokens.textSecondary : hexColor(hex);
}

String _plural(int n, String word) => '$n $word${n == 1 ? '' : 's'}';

/// "Fri 23 Oct: 2 tasks, 1 reminder, 1 routine", for a screen reader.
String dayCellLabel(DateTime d, DayMarks m) {
  final parts = [
    if (m.tasks.isNotEmpty) _plural(m.tasks.length, 'task'),
    if (m.reminders > 0) _plural(m.reminders, 'reminder'),
    if (m.routines > 0) _plural(m.routines, 'routine'),
    if (m.plans > 0) _plural(m.plans, 'plan item'),
  ];
  final words = DateFormat('EEE d MMM').format(d);
  return parts.isEmpty ? words : '$words: ${parts.join(', ')}';
}

/// One day in the month grid: the date, then markers only, never words:
/// task dots (+N), a bell, a repeat mark and the first bot's initial.
class DayCell extends StatelessWidget {
  const DayCell({
    super.key,
    required this.day,
    required this.marks,
    required this.today,
    required this.inMonth,
    required this.picked,
    required this.onTap,
    this.bots = const {},
    this.projectColors = const {},
  });

  final DateTime day;
  final DayMarks marks;
  final DateTime today;
  final bool inMonth;
  final bool picked;
  final VoidCallback onTap;
  final Map<String, BotTag> bots;
  final Map<String, String?> projectColors;

  String get _iso => '${day.year}-${day.month.toString().padLeft(2, '0')}-${day.day.toString().padLeft(2, '0')}';

  @override
  Widget build(BuildContext context) {
    final accent = AccentColors.of(context);
    final isToday = day == today;
    return Semantics(
      button: true,
      selected: picked,
      label: dayCellLabel(day, marks),
      excludeSemantics: true,
      child: InkWell(
        key: Key('day-${day.year}-${day.month}-${day.day}'),
        onTap: onTap,
        borderRadius: BorderRadius.circular(Tokens.radiusSm),
        child: Container(
          height: _cellHeight,
          margin: const EdgeInsets.all(1),
          decoration: BoxDecoration(
            color: picked ? accent.tint : null,
            borderRadius: BorderRadius.circular(Tokens.radiusSm),
            border: isToday ? Border.all(color: accent.strong, width: 1.5) : null,
          ),
          child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
            Text('${day.day}',
                style: TextStyle(
                  fontSize: Tokens.fsBody,
                  fontWeight: isToday ? FontWeight.w700 : FontWeight.w400,
                  color: isToday ? accent.strong : inMonth ? Tokens.text : Tokens.textFaint,
                )),
            const SizedBox(height: 3),
            SizedBox(height: 10, child: _dots(accent.strong)),
            const SizedBox(height: 2),
            SizedBox(height: _initial, child: _icons()),
          ]),
        ),
      ),
    );
  }

  Widget _dots(Color planTone) {
    final shown = marks.tasks.take(maxCellDots).toList();
    final plans = (maxCellDots - shown.length).clamp(0, marks.plans);
    final more = marks.tasks.length + marks.plans - shown.length - plans;
    return Row(mainAxisAlignment: MainAxisAlignment.center, children: [
      for (final t in shown) _taskDot(t),
      for (var i = 0; i < plans; i++) _planDot(i, planTone),
      if (more > 0)
        Text('+$more',
            key: Key('more-$_iso'),
            style: const TextStyle(fontSize: _moreFont, color: Tokens.textSecondary, height: 1)),
    ]);
  }

  Widget _taskDot(TaskItem t) {
    final tone = dotTone(t, today, projectColors);
    final done = !isOpenTask(t);
    return Container(
      key: Key('dot-${t.id}'),
      width: _dot,
      height: _dot,
      margin: const EdgeInsets.symmetric(horizontal: 1),
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: done ? null : tone,
        border: done ? Border.all(color: Tokens.textFaint, width: 1) : null,
      ),
    );
  }

  /// A Plan item: a small square in the accent, beside the task dots.
  Widget _planDot(int i, Color tone) => Container(
        key: Key('plan-$_iso-$i'),
        width: _dot,
        height: _dot,
        margin: const EdgeInsets.symmetric(horizontal: 1),
        decoration: BoxDecoration(color: tone, borderRadius: BorderRadius.circular(1)),
      );

  Widget _icons() {
    final bot = marks.botIds.map((id) => bots[id]).whereType<BotTag>().firstOrNull;
    return Row(mainAxisAlignment: MainAxisAlignment.center, children: [
      if (marks.reminders > 0)
        Icon(Icons.notifications_none, key: Key('bell-$_iso'), size: _icon, color: Tokens.warn),
      if (marks.routines > 0)
        Icon(Icons.repeat, key: Key('repeat-$_iso'), size: _icon, color: Tokens.textSecondary),
      if (bot != null) BotInitial(key: Key('bot-$_iso'), bot: bot),
    ]);
  }
}

/// A bot's initial in a small circle of its avatar colour.
class BotInitial extends StatelessWidget {
  const BotInitial({super.key, required this.bot, this.size = _initial});

  final BotTag bot;
  final double size;

  @override
  Widget build(BuildContext context) => Container(
        width: size,
        height: size,
        margin: const EdgeInsets.symmetric(horizontal: 1),
        alignment: Alignment.center,
        decoration: BoxDecoration(color: hexColor(bot.color), shape: BoxShape.circle),
        child: Text(bot.initial,
            style: TextStyle(
                fontSize: size * _tinyFont / _initial,
                height: 1,
                fontWeight: FontWeight.w700,
                color: Tokens.bg)),
      );
}
