import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../api/api_error.dart';
import '../../api/models.dart';
import '../../api/providers.dart';
import '../../board/tasks/reschedule_sheet.dart';
import '../../board/tasks/task_dates.dart';
import '../../board/tasks/task_drawer.dart';
import '../../board/tasks/task_models.dart';
import '../../board/tasks/task_repo.dart';
import '../../theme/tokens.dart';
import 'card_base.dart';
import 'report_foot.dart';
import 'task_card_parts.dart';

const reminderDone = '✓ Done';
const reminderFailed = 'Marked failed';
const reminderSkipped = 'Skipped';
const reminderNoDate = 'Now has no date';
const taskGoneText = 'This task is gone.';

/// "Moved to Thu 29 Oct 10:00", or "Now has no date", for a new due.
String dueMovedWords(String? due) => due == null ? reminderNoDate : 'Moved to ${dueWords(due)}';

/// "Moved to Thu 29 Oct 10:00", or "Now has no date".
String movedWords(RescheduleChoice c) => dueMovedWords(c.wire);

/// The card's line for an answer the server kept on the Report, or null.
String? answerWords(String? answer, String? due) => switch (answer) {
      'done' => reminderDone,
      'failed' => reminderFailed,
      'skipped' => reminderSkipped,
      'rescheduled' => dueMovedWords(due),
      _ => null,
    };

/// Keeps the task's own time when the pick has none.
RescheduleChoice withOwnTime(TaskItem t, RescheduleChoice c) {
  if (c.day == null || c.clock != null) return c;
  return RescheduleChoice(c.day, readDue(t.dueDate)?.clock);
}

/// Under a task reminder's bubble (owner, 2026-10-26: "like Grok", with Done
/// · Failed · Reschedule · Skip kept): four small quiet chips, then one quiet
/// line of what happened, and the "🔔 Reminder" footer that opens the task.
/// The answer is kept on the Report on the server, so it stays folded after a
/// restart and on the web too; Skip changes nothing else.
class ReminderChips extends ConsumerStatefulWidget {
  const ReminderChips(
      {super.key, required this.message, required this.taskId, required this.tainted});
  final Message message;
  final String taskId;
  final bool tainted;

  @override
  ConsumerState<ReminderChips> createState() => _ReminderChipsState();
}

class _ReminderChipsState extends ConsumerState<ReminderChips> {
  String? _outcome;
  String? _problem;
  String? _saveProblem;
  bool _busy = false;

  /// Runs the task's change, then keeps the answer on the Report. A Skip is
  /// only its answer: it folds once the server kept it.
  Future<void> _run(Future<void> Function() action, String answer, String words,
      {String? due}) async {
    setState(() {
      _busy = true;
      _problem = null;
    });
    try {
      await action();
      if (answer != 'skipped' && mounted) setState(() => _outcome = words);
      ref.invalidate(taskListProvider);
    } on ApiException catch (e) {
      if (mounted) {
        setState(() => e.status == 404 ? _outcome = taskGoneText : _problem = e.message);
      }
      return;
    } catch (e) {
      if (mounted) setState(() => _problem = '$e');
      return;
    } finally {
      if (mounted) setState(() => _busy = false);
    }
    await _keep(answer, words, due);
  }

  Future<void> _keep(String answer, String words, String? due) async {
    final m = widget.message;
    try {
      await ref.read(apiClientProvider).put(
          '/api/threads/${m.threadId}/messages/${m.id}/reminder-answer',
          {'answer': answer, 'due': due});
      if (mounted) setState(() => _outcome = words);
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() => answer == 'skipped'
          ? _problem = e.message
          : _saveProblem = 'Not saved for your other screens: ${e.message}');
    }
  }

  Future<void> _reschedule(TaskItem t) async {
    final picked = await showRescheduleSheet(context, title: 'Reschedule “${t.title}”');
    if (picked == null || !mounted) return;
    final c = withOwnTime(t, picked);
    await _run(() => ref.read(taskRepoProvider).update(t.id, {'due_date': c.wire}).then((_) {}),
        'rescheduled', movedWords(c), due: c.wire);
  }

  String? _settled(TaskItem? t) => switch (t?.status) {
        'done' => reminderDone,
        'failed' => reminderFailed,
        _ => null,
      };

  Widget _chips(TaskItem task) {
    final repo = ref.read(taskRepoProvider);
    VoidCallback? on(VoidCallback f) => _busy ? null : f;
    return Wrap(
      key: const Key('reminder-chips'),
      spacing: Tokens.space1,
      runSpacing: Tokens.space1,
      children: [
        _Chip('Done', on(() => _run(() => repo.complete(task.id), 'done', reminderDone))),
        _Chip('Failed', on(() => _run(() => repo.fail(task.id), 'failed', reminderFailed))),
        _Chip('Reschedule', on(() => _reschedule(task))),
        _Chip('Skip', on(() => _run(() async {}, 'skipped', reminderSkipped))),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    final body = decodeBody(widget.message.body);
    final tasks = ref.watch(cardTasksProvider(cardQuery([widget.taskId])));
    final kept = answerWords(body?['answer'] as String?, body?['answer_due'] as String?);
    final list = tasks.valueOrNull;
    final task = (list == null || list.isEmpty) ? null : list.first;
    final gone = list != null && list.isEmpty;
    final said = _outcome ?? kept ?? _settled(task) ?? (gone ? taskGoneText : null);
    const danger = TextStyle(color: Tokens.dangerText, fontSize: Tokens.fsCaption);
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      if (said != null)
        Text(said,
            key: const Key('reminder-outcome'),
            style: const TextStyle(color: Tokens.textSecondary, fontSize: Tokens.fsCaption))
      else if (task != null)
        _chips(task),
      if (_problem != null && said == null) Text(_problem!, style: danger),
      if (_saveProblem != null) Text(_saveProblem!, style: danger),
      ReportFoot(label: reminderFoot, tainted: widget.tainted, links: [
        if (task != null)
          FootLink('Open task',
              semantics: 'Open task ${task.title}',
              onTap: () => openTaskDrawer(context, task.id)),
      ]),
    ]);
  }
}

/// One small quiet chip under a reminder.
class _Chip extends StatelessWidget {
  const _Chip(this.label, this.onPressed);
  final String label;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) => OutlinedButton(
        onPressed: onPressed,
        style: OutlinedButton.styleFrom(
          visualDensity: VisualDensity.compact,
          minimumSize: const Size(0, 32),
          padding: const EdgeInsets.symmetric(horizontal: Tokens.space3),
          foregroundColor: Tokens.textSecondary,
          side: const BorderSide(color: Tokens.border),
          shape: const StadiumBorder(),
          textStyle: const TextStyle(fontSize: Tokens.fsCaption),
        ),
        child: Text(label),
      );
}

