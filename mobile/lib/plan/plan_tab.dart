import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api_error.dart';
import '../theme/tokens.dart';
import '../widgets/profile_kit.dart';
import 'plan_calendar.dart';
import 'plan_kanban.dart';
import 'plan_models.dart';
import 'plan_repo.dart';
import 'plan_text_editor.dart';

enum _View { kanban, agenda, text }

/// The Plan tab: the bot's own diary as a Kanban (Planned · On it · Done),
/// an agenda by day, or Edit as text.
class PlanTab extends ConsumerStatefulWidget {
  const PlanTab({super.key, required this.botId});

  final String botId;

  @override
  ConsumerState<PlanTab> createState() => _PlanTabState();
}

class _PlanTabState extends ConsumerState<PlanTab> {
  PlanData? _plan;
  String? _error;
  _View _view = _View.kanban;

  PlanRepo get _repo => ref.read(planRepoProvider(widget.botId));

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final plan = await _repo.read();
      if (mounted) setState(() => _plan = plan);
    } catch (e) {
      if (mounted) setState(() => _error = describe(e));
    }
  }

  Future<void> _move(PlanItem item, String status) async {
    final plan = _plan;
    if (plan == null || item.id == null) return;
    try {
      final next = await _repo.moveItem(item.id!, plan.revision, status);
      if (mounted) setState(() => _plan = next);
    } on ApiException catch (e) {
      final current = e.current;
      if (e.isConflict && current != null) {
        if (mounted) setState(() => _plan = PlanData.fromJson(current));
        _say('The Plan changed since you opened it. Showing the latest.');
      } else {
        _say(e.message);
      }
    }
  }

  void _say(String text) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(text)));
  }

  @override
  Widget build(BuildContext context) {
    final plan = _plan;
    if (plan == null) {
      return Center(
        child: _error == null
            ? const CircularProgressIndicator()
            : TextButton(
                onPressed: () {
                  setState(() => _error = null);
                  _load();
                },
                child: Text('$_error Try again')),
      );
    }
    return Column(children: [
      Padding(
        padding: const EdgeInsets.all(Tokens.space3),
        child: SegmentedButton<_View>(
          showSelectedIcon: false,
          segments: const [
            ButtonSegment(value: _View.kanban, label: Text('Kanban')),
            ButtonSegment(value: _View.agenda, label: Text('Calendar')),
            ButtonSegment(value: _View.text, label: Text('Edit as text')),
          ],
          selected: {_view},
          onSelectionChanged: (s) => setState(() => _view = s.first),
        ),
      ),
      if (plan.unreadable > 0)
        Quiet('${plan.unreadable} lines could not be read.', bad: true),
      Expanded(
        child: switch (_view) {
          _View.kanban => PlanKanban(items: plan.items, onMove: _move),
          _View.agenda => PlanCalendarPane(botId: widget.botId, items: plan.items),
          _View.text => PlanTextEditor(
              key: ValueKey(plan.revision),
              plan: plan,
              save: _repo.putText,
              onSaved: (p) => setState(() => _plan = p),
            ),
        },
      ),
    ]);
  }
}
