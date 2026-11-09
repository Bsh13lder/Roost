import 'package:flutter/material.dart';

import '../../theme/tokens.dart';
import 'day_cell.dart';
import 'day_marks.dart';
import 'month_grid.dart';

const _weekdays = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

/// The month as a Monday-first grid of [DayCell]s: markers only (task dots,
/// a bell, a repeat mark, a bot's initial), today ringed in the accent, the
/// chosen day tinted. When [collapsed], only the chosen day's week shows.
class MonthGridView extends StatelessWidget {
  const MonthGridView({
    super.key,
    required this.month,
    required this.today,
    required this.selected,
    required this.marks,
    required this.onPick,
    this.bots = const {},
    this.projectColors = const {},
    this.collapsed = false,
  });

  final String month;
  final DateTime today;
  final DateTime selected;
  final Map<DateTime, DayMarks> marks;
  final ValueChanged<DateTime> onPick;
  final Map<String, BotTag> bots;
  final Map<String, String?> projectColors;
  final bool collapsed;

  @override
  Widget build(BuildContext context) {
    final days = monthGrid(month);
    final weeks = [
      for (var i = 0; i < days.length; i += 7) days.sublist(i, i + 7),
    ];
    final shown = collapsed ? weeks.where((w) => w.contains(selected)).toList() : weeks;
    final shownMonth = DateTime.parse('$month-01').month;
    return Container(
      key: const Key('month-grid'),
      decoration: BoxDecoration(
        color: Tokens.panel,
        borderRadius: BorderRadius.circular(Tokens.radiusMd),
        border: Border.all(color: Tokens.border),
      ),
      padding: const EdgeInsets.symmetric(vertical: Tokens.space2, horizontal: 2),
      child: Column(children: [
        Row(children: [
          for (final w in _weekdays)
            Expanded(
              child: Center(
                child: Text(w, style: const TextStyle(color: Tokens.textFaint, fontSize: Tokens.fsCaption)),
              ),
            ),
        ]),
        for (final week in shown.isEmpty ? [weeks.first] : shown)
          Row(children: [
            for (final d in week)
              Expanded(
                child: DayCell(
                  day: d,
                  marks: marks[d] ?? const DayMarks(),
                  today: today,
                  inMonth: d.month == shownMonth,
                  picked: d == selected,
                  bots: bots,
                  projectColors: projectColors,
                  onTap: () => onPick(d),
                ),
              ),
          ]),
      ]),
    );
  }
}
