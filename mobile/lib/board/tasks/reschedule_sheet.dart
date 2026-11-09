import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../../theme/tokens.dart';
import 'task_dates.dart';

/// What the Reschedule sheet answers: an account-zone day (null: no date) and an
/// optional clock like "09:30".
class RescheduleChoice {
  const RescheduleChoice(this.day, [this.clock]);

  final DateTime? day;
  final String? clock;

  /// The text the server reads for `due_date` / `to`.
  String? get wire {
    final d = day;
    if (d == null) return null;
    return clock == null ? isoDay(d) : '${isoDay(d)}T$clock';
  }
}

/// Quick picks, a date and a time, on the account's calendar.
Future<RescheduleChoice?> showRescheduleSheet(
  BuildContext context, {
  String title = 'Reschedule',
}) {
  return showModalBottomSheet<RescheduleChoice>(
    context: context,
    isScrollControlled: true,
    showDragHandle: true,
    builder: (_) => _RescheduleBody(title: title),
  );
}

class _RescheduleBody extends StatefulWidget {
  const _RescheduleBody({required this.title});

  final String title;

  @override
  State<_RescheduleBody> createState() => _RescheduleBodyState();
}

class _RescheduleBodyState extends State<_RescheduleBody> {
  String? _clock;

  Future<void> _pickDate(DateTime today) async {
    final picked = await showDatePicker(
      context: context,
      initialDate: today,
      firstDate: today.subtract(const Duration(days: 365)),
      lastDate: today.add(const Duration(days: 365 * 5)),
    );
    if (picked != null && mounted) {
      Navigator.pop(context, RescheduleChoice(dayOnly(picked), _clock));
    }
  }

  Future<void> _pickTime() async {
    final t = await showTimePicker(
      context: context,
      initialTime: const TimeOfDay(hour: 9, minute: 0),
    );
    if (t == null || !mounted) return;
    setState(() => _clock =
        '${t.hour.toString().padLeft(2, '0')}:${t.minute.toString().padLeft(2, '0')}');
  }

  @override
  Widget build(BuildContext context) {
    final today = appToday();
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(
            Tokens.space4, 0, Tokens.space4, Tokens.space4),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(widget.title,
                style: const TextStyle(
                    fontSize: Tokens.fsHeading, fontWeight: FontWeight.w600)),
            const SizedBox(height: Tokens.space3),
            for (final p in reschedulePicks(today))
              ListTile(
                key: Key('pick-${p.label}'),
                dense: true,
                contentPadding: EdgeInsets.zero,
                title: Text(p.label),
                trailing: Text(
                  p.day == null ? '' : DateFormat('EEE d').format(p.day!),
                  style: const TextStyle(color: Tokens.textSecondary),
                ),
                onTap: () =>
                    Navigator.pop(context, RescheduleChoice(p.day, _clock)),
              ),
            const Divider(),
            ListTile(
              key: const Key('pick-date'),
              dense: true,
              contentPadding: EdgeInsets.zero,
              leading: const Icon(Icons.calendar_today_outlined, size: 20),
              title: const Text('Pick a date'),
              onTap: () => _pickDate(today),
            ),
            ListTile(
              key: const Key('pick-time'),
              dense: true,
              contentPadding: EdgeInsets.zero,
              leading: const Icon(Icons.schedule, size: 20),
              title: Text(_clock ?? 'Add a time'),
              trailing: _clock == null
                  ? null
                  : IconButton(
                      icon: const Icon(Icons.close, size: 18),
                      onPressed: () => setState(() => _clock = null),
                    ),
              onTap: _pickTime,
            ),
          ],
        ),
      ),
    );
  }
}

DateTime dayOnly(DateTime d) => DateTime.utc(d.year, d.month, d.day);
