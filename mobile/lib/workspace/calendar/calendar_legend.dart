import 'package:flutter/material.dart';

import '../../theme/accent.dart';
import '../../theme/tokens.dart';

const _mark = 10.0;

/// One quiet line under the grid that says what its marks mean. A bot's
/// Plan calendar adds Plan items and leaves out "By a bot".
class CalendarLegend extends StatelessWidget {
  const CalendarLegend({super.key, this.plan = false});

  final bool plan;

  @override
  Widget build(BuildContext context) {
    const faint = TextStyle(color: Tokens.textFaint, fontSize: Tokens.fsCaption);
    Widget item(Widget mark, String word) => Row(mainAxisSize: MainAxisSize.min, children: [
          mark,
          const SizedBox(width: 3),
          Text(word, style: faint),
        ]);
    Widget dot({required bool done}) => Container(
          width: 6,
          height: 6,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: done ? null : Tokens.textSecondary,
            border: done ? Border.all(color: Tokens.textFaint) : null,
          ),
        );
    return Padding(
      key: const Key('calendar-legend'),
      padding: const EdgeInsets.fromLTRB(Tokens.space4, Tokens.space2, Tokens.space4, 0),
      child: Wrap(spacing: Tokens.space3, runSpacing: Tokens.space1, children: [
        if (plan)
          item(
            Container(
              width: 6,
              height: 6,
              decoration: BoxDecoration(
                  color: AccentColors.of(context).strong, borderRadius: BorderRadius.circular(1)),
            ),
            'Plan',
          ),
        item(dot(done: false), 'Task'),
        item(dot(done: true), 'Done'),
        item(const Icon(Icons.notifications_none, size: _mark, color: Tokens.warn), 'Reminder'),
        item(const Icon(Icons.repeat, size: _mark, color: Tokens.textSecondary), 'Routine'),
        if (!plan)
          item(
          Container(
            width: _mark,
            height: _mark,
            alignment: Alignment.center,
            decoration: const BoxDecoration(color: Tokens.textSecondary, shape: BoxShape.circle),
            child: const Text('A', style: TextStyle(fontSize: 7, height: 1, color: Tokens.bg)),
          ),
          'By a bot',
        ),
      ]),
    );
  }
}
