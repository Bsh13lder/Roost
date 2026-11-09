import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../board/tasks/quick_draft.dart';
import '../../board/tasks/quick_help.dart';
import '../../board/tasks/quick_insert.dart';
import '../../board/tasks/remind_picks.dart';
import '../../board/tasks/remind_sheet.dart';
import '../../board/tasks/reschedule_sheet.dart';
import '../../board/tasks/task_dates.dart';
import '../../board/tasks/task_models.dart';
import '../../board/tasks/task_repo.dart';
import 'picker_sheets.dart';
import 'quick_pickers.dart';

/// The bar's picker buttons: each writes the same words typing would into
/// the line (Date, Project, Priority, Repeat), so the server reads them and
/// draws the same chip. Remind me is the one field set beside the line.
mixin BarPicks<T extends ConsumerStatefulWidget> on ConsumerState<T> {
  TextEditingController get text;
  QuickReading? get reading;
  QuickDraft get draft;
  set draft(QuickDraft value);
  set wantsProjects(bool value);

  /// Asks the server to read the line again.
  void reread();

  /// Puts [value] in the line (caret at the end) and reads it.
  void setLine(String value, [int? caret]);

  String? get remindLabel {
    final wire = draft.remindWire;
    return wire == null ? null : 'Remind ${wireWords(wire)}';
  }

  List<String> _words(String kind) => reading?.matches[kind] ?? const [];

  void _put(String words, String kind) =>
      setLine(insertWords(text.text, words, _words(kind)));

  Future<void> _pickDate() async {
    final c = await showRescheduleSheet(context, title: 'Due');
    if (c == null || !mounted) return;
    _put(c.day == null ? '' : dayWords(c.day!, c.clock), 'date');
  }

  Future<void> _pickProject() async {
    wantsProjects = true;
    final projects = await ref.read(taskProjectsProvider.future);
    if (!mounted) return;
    final name = await showProjectSheet(context, [for (final p in projects) p.name]);
    if (name != null && mounted) _put('/$name', 'project');
  }

  Future<void> _pickChoice(String title, List<QuickChoice> choices, String kind) async {
    final c = await showChoiceSheet(context, title, choices);
    if (c != null && mounted) _put(c.words, kind);
  }

  Future<void> _pickRemind(DateTime? day) async {
    final due = reading?.json['due_date'] as String? ?? (day == null ? null : isoDay(day));
    final c = await showRemindSheet(context, dueDate: due, hasReminder: draft.remindWire != null);
    if (c == null || !mounted) return;
    setState(() => draft = draft.withRemind(c.wire));
  }

  Widget pickerRow(DateTime? day) {
    final r = reading;
    return QuickPickerRow(
      onHelp: () => showQuickHelp(context),
      picks: [
        QuickPick('date', 'Date', Icons.event_outlined, _pickDate,
            on: r?.json['due_date'] != null || day != null),
        QuickPick('project', 'Project', Icons.folder_outlined, _pickProject,
            on: r?.projectName != null),
        QuickPick('priority', 'Priority', Icons.flag_outlined,
            () => _pickChoice('Priority', priorityChoices, 'priority'),
            on: r?.priority != null),
        QuickPick('repeat', 'Repeat', Icons.repeat, () => _pickChoice('Repeat', repeatChoices, 'repeat'),
            on: r?.json['recurring'] != null),
        QuickPick('remind', 'Remind me', Icons.notifications_none, () => _pickRemind(day),
            on: draft.remindWire != null),
      ],
    );
  }
}
