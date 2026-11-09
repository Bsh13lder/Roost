import 'package:flutter/material.dart';

import '../../theme/tokens.dart';
import 'remind_picks.dart';
import 'reschedule_sheet.dart';
import 'task_dates.dart';

/// A day with no time picked reminds you at nine (the account's clock).
const defaultRemindClock = '09:00';

/// What Remind me answers: a reminder time (the account's wall time), or none.
class RemindChoice {
  const RemindChoice(this.wire);

  /// Null turns the reminder off.
  final String? wire;
}

/// Remind me: quick picks before a timed due, a day and time, or Off.
Future<RemindChoice?> showRemindSheet(BuildContext context, {String? dueDate, bool hasReminder = false}) {
  return showModalBottomSheet<RemindChoice>(
    context: context,
    isScrollControlled: true,
    showDragHandle: true,
    builder: (_) => _RemindBody(dueDate: dueDate, hasReminder: hasReminder),
  );
}

class _RemindBody extends StatelessWidget {
  const _RemindBody({required this.dueDate, required this.hasReminder});

  final String? dueDate;
  final bool hasReminder;

  Future<void> _pickDayAndTime(BuildContext context) async {
    final navigator = Navigator.of(context);
    final picked = await showRescheduleSheet(context, title: 'Remind me on');
    final day = picked?.day;
    if (day == null) return;
    navigator.pop(RemindChoice('${isoDay(day)}T${picked!.clock ?? defaultRemindClock}'));
  }

  @override
  Widget build(BuildContext context) {
    final picks = remindPicks(dueDate);
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(Tokens.space4, 0, Tokens.space4, Tokens.space4),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('Remind me', style: TextStyle(fontSize: Tokens.fsHeading, fontWeight: FontWeight.w600)),
            const SizedBox(height: Tokens.space1),
            const Text('Your phone tells you, with Stay connected on.',
                style: TextStyle(fontSize: Tokens.fsCaption, color: Tokens.textSecondary)),
            const SizedBox(height: Tokens.space3),
            for (final p in picks)
              ListTile(
                key: Key('remind-${p.label}'),
                dense: true,
                contentPadding: EdgeInsets.zero,
                leading: const Icon(Icons.notifications_none, size: 20),
                title: Text(p.label),
                trailing: Text(wireWords(p.wire), style: const TextStyle(color: Tokens.textSecondary)),
                onTap: () => Navigator.pop(context, RemindChoice(p.wire)),
              ),
            if (picks.isNotEmpty) const Divider(),
            ListTile(
              key: const Key('remind-pick'),
              dense: true,
              contentPadding: EdgeInsets.zero,
              leading: const Icon(Icons.calendar_today_outlined, size: 20),
              title: const Text('Pick a day and time'),
              onTap: () => _pickDayAndTime(context),
            ),
            if (hasReminder)
              ListTile(
                key: const Key('remind-off'),
                dense: true,
                contentPadding: EdgeInsets.zero,
                leading: const Icon(Icons.notifications_off_outlined, size: 20),
                title: const Text('No reminder'),
                onTap: () => Navigator.pop(context, const RemindChoice(null)),
              ),
          ],
        ),
      ),
    );
  }
}
