import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../profile/format.dart';
import '../theme/tokens.dart';
import '../widgets/profile_kit.dart';
import 'routines_repo.dart';
import 'watch_fields.dart';

/// Opens the editor; `routine` null creates one for `botId`. True when saved.
Future<bool> showRoutineEditor(BuildContext context,
    {required String botId, Json? routine}) async {
  final saved = await showModalBottomSheet<bool>(
    context: context,
    isScrollControlled: true,
    builder: (_) => RoutineEditor(botId: botId, routine: routine),
  );
  return saved == true;
}

/// Name, instructions and account-zone weekdays with times, or a cron line (no
/// more often than every 15 minutes; the server checks and previews it).
/// With "Only run when the page changes" on, the page's address, the part and
/// the minutes replace the schedule.
class RoutineEditor extends ConsumerStatefulWidget {
  const RoutineEditor({super.key, required this.botId, this.routine});

  final String botId;
  final Json? routine;

  @override
  ConsumerState<RoutineEditor> createState() => _RoutineEditorState();
}

class _RoutineEditorState extends ConsumerState<RoutineEditor> {
  late final _name =
      TextEditingController(text: widget.routine?['name'] as String? ?? '');
  late final _instructions = TextEditingController(
      text: widget.routine?['instructions'] as String? ?? '');
  late final _cron = TextEditingController(text: _initial['expr'] as String? ?? '');
  late bool _isCron = _initial['kind'] == 'cron';
  late final Set<int> _days = {
    for (final d in (_initial['days'] as List? ?? const [1, 2, 3, 4, 5])) (d as num).toInt(),
  };
  late final List<String> _times = [
    for (final t in (_initial['times'] as List? ?? const ['09:00'])) '$t',
  ];
  late final Map<String, dynamic>? _watch =
      (widget.routine?['watch'] as Map?)?.cast<String, dynamic>();
  late bool _watchOn = _watch != null;
  late final _watchUrl = TextEditingController(text: _watch?['url'] as String? ?? '');
  late final _watchPart = TextEditingController(text: _watch?['part'] as String? ?? '');
  late final _watchEvery =
      TextEditingController(text: '${_watch?['every_min'] ?? watchDefaultMinutes}');
  String _preview = '';
  bool _busy = false;

  Json get _initial =>
      (widget.routine?['schedule'] as Map?)?.cast<String, dynamic>() ?? {};

  @override
  void dispose() {
    _name.dispose();
    _instructions.dispose();
    _cron.dispose();
    _watchUrl.dispose();
    _watchPart.dispose();
    _watchEvery.dispose();
    super.dispose();
  }

  Json get _schedule => _isCron
      ? {'kind': 'cron', 'expr': _cron.text.trim()}
      : {'kind': 'times', 'days': (_days.toList()..sort()), 'times': _times};

  Future<void> _addTime() async {
    final t = await showTimePicker(
        context: context, initialTime: const TimeOfDay(hour: 9, minute: 0));
    if (t == null) return;
    final s =
        '${t.hour.toString().padLeft(2, '0')}:${t.minute.toString().padLeft(2, '0')}';
    if (!_times.contains(s)) setState(() => _times.add(s));
  }

  Future<void> _check() async {
    try {
      final p = await ref.read(routinesRepoProvider).preview(_schedule);
      final next = [
        for (final n in (p['next'] as List? ?? const []).take(3))
          appShort('$n'),
      ];
      setState(() => _preview = '${p['words'] ?? ''}\nNext: ${next.join(' · ')}');
    } catch (e) {
      setState(() => _preview = describe(e));
    }
  }

  Future<void> _save() async {
    final watch = watchBody(
        on: _watchOn, url: _watchUrl.text, part: _watchPart.text, every: _watchEvery.text);
    final draft = {
      'name': _name.text.trim(),
      'instructions': _instructions.text.trim(),
      'schedule': _schedule,
      if (watch != null || _watch != null) 'watch': watch,
    };
    setState(() => _busy = true);
    final repo = ref.read(routinesRepoProvider);
    final id = widget.routine?['id'] as String?;
    final ok = await attempt(context,
        () => id == null ? repo.create(widget.botId, draft) : repo.change(id, draft));
    if (!mounted) return;
    setState(() => _busy = false);
    if (ok) Navigator.of(context).pop(true);
  }

  Future<void> _delete() async {
    if (!await confirm(context, 'Delete this routine?', 'Delete')) return;
    if (!mounted) return;
    final id = widget.routine!['id'] as String;
    final ok =
        await attempt(context, () => ref.read(routinesRepoProvider).delete(id));
    if (ok && mounted) Navigator.of(context).pop(true);
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(
          bottom: MediaQuery.of(context).viewInsets.bottom),
      child: SafeArea(
        child: ListView(
          shrinkWrap: true,
          padding: const EdgeInsets.all(Tokens.space4),
          children: [
            TextField(
                key: const Key('routine-name'),
                controller: _name,
                decoration: const InputDecoration(labelText: 'Name')),
            const SizedBox(height: Tokens.space3),
            TextField(
                key: const Key('routine-instructions'),
                controller: _instructions,
                minLines: 3,
                maxLines: 8,
                decoration: const InputDecoration(labelText: 'Instructions')),
            const SizedBox(height: Tokens.space3),
            WatchFields(
                on: _watchOn,
                onChanged: (on) => setState(() => _watchOn = on),
                url: _watchUrl,
                part: _watchPart,
                every: _watchEvery),
            const SizedBox(height: Tokens.space3),
            if (!_watchOn) ..._scheduleFields(),
            Row(children: [
              if (widget.routine != null)
                TextButton(
                    onPressed: _delete,
                    child: const Text('Delete',
                        style: TextStyle(color: Tokens.dangerText))),
              const Spacer(),
              FilledButton(
                  key: const Key('routine-save'),
                  onPressed: _busy ? null : _save,
                  child: const Text('Save')),
            ]),
          ],
        ),
      ),
    );
  }

  List<Widget> _scheduleFields() => [
        SegmentedButton<bool>(
          showSelectedIcon: false,
          segments: const [
            ButtonSegment(value: false, label: Text('Days and times')),
            ButtonSegment(value: true, label: Text('Cron line')),
          ],
          selected: {_isCron},
          onSelectionChanged: (s) => setState(() => _isCron = s.first),
        ),
        const SizedBox(height: Tokens.space3),
        if (_isCron)
          TextField(
              controller: _cron,
              decoration: InputDecoration(
                  labelText: 'Cron', hintText: '0 9 * * 1-5'))
        else
          _daysAndTimes(),
        TextButton(onPressed: _check, child: const Text('Check the times')),
        if (_preview.isNotEmpty) Quiet(_preview),
      ];

  Widget _daysAndTimes() {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Wrap(spacing: Tokens.space2, children: [
        for (var d = 1; d <= 7; d++)
          FilterChip(
            label: Text(weekdayNames[d - 1]),
            selected: _days.contains(d),
            onSelected: (on) =>
                setState(() => on ? _days.add(d) : _days.remove(d)),
          ),
      ]),
      Wrap(spacing: Tokens.space2, children: [
        for (final t in _times)
          InputChip(
              label: Text(t),
              onDeleted: _times.length > 1
                  ? () => setState(() => _times.remove(t))
                  : null),
        ActionChip(label: const Text('Add a time'), onPressed: _addTime),
      ]),
    ]);
  }
}
