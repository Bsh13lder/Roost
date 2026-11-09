import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../api/api_error.dart';
import '../../theme/tokens.dart';
import 'kanban_groups.dart';
import 'reschedule_sheet.dart';
import 'task_dates.dart';
import 'task_models.dart';
import 'task_repo.dart';

/// The row and drawer actions. Each change says what it did and offers Undo.
/// It holds the container, not a widget's ref, so an Undo still works after
/// the row that started it has left the list.
class TaskActions {
  TaskActions(BuildContext context)
      : _container = ProviderScope.containerOf(context),
        _messenger = ScaffoldMessenger.of(context),
        _context = context;

  final ProviderContainer _container;
  final ScaffoldMessengerState _messenger;
  final BuildContext _context;

  TaskRepo get _repo => _container.read(taskRepoProvider);

  void _refresh() {
    _container.invalidate(taskListProvider);
    _container.invalidate(taskCountsProvider);
    _container.invalidate(kanbanTasksProvider);
    _container.invalidate(monthTasksProvider);
  }

  void _say(String text, {VoidCallback? undo}) {
    _messenger
      ..clearSnackBars()
      ..showSnackBar(SnackBar(
        content: Text(text),
        persist: false, // Flutter keeps a bar with an action until tapped
        action: undo == null
            ? null
            : SnackBarAction(label: 'Undo', onPressed: undo),
      ));
  }

  Future<void> _guard(Future<void> Function() run) async {
    try {
      await run();
    } on ApiException catch (e) {
      _say(e.message);
    }
  }

  /// Finishes [t] with Undo; true when the server took it.
  Future<bool> done(TaskItem t) async {
    var ok = false;
    await _guard(() async {
      await _repo.complete(t.id);
      ok = true;
      _refresh();
      _say('Done: ${t.title}', undo: () => reopen(t));
    });
    return ok;
  }

  Future<void> reopen(TaskItem t) => _guard(() async {
        await _repo.reopen(t.id);
        _refresh();
      });

  Map<String, dynamic> _dueOf(TaskItem t) => {
        'id': t.id,
        'due_date': t.dueDate,
        'reminder_at': t.reminderAt,
        'pre_reminders': t.preReminders,
      };

  Future<void> reschedule(TaskItem t, RescheduleChoice c) => _guard(() async {
        await _repo.update(t.id, {'due_date': c.wire});
        _refresh();
        _say('Moved: ${t.title}', undo: () => _restore([_dueOf(t)]));
      });

  Future<void> _restore(List<Map<String, dynamic>> items) => _guard(() async {
        await _repo.restoreDues(items);
        _refresh();
      });

  Future<void> rescheduleAll(RescheduleChoice c) => _guard(() async {
        final moved = await _repo.moveOverdue(c.wire);
        _refresh();
        _say('Moved ${moved.length} overdue',
            undo: moved.isEmpty ? null : () => _restore(moved));
      });

  Future<void> moveToProject(TaskItem t, ProjectRef? p) => _guard(() async {
        await _repo.update(t.id, {'project_id': p?.id});
        _refresh();
        final back = t.projectId;
        _say(p == null ? 'Removed from its project' : 'Moved to ${p.name}',
            undo: () => _guard(() async {
                  await _repo.update(t.id, {'project_id': back});
                  _refresh();
                }));
      });

  /// A Kanban card moved to a column: the grouped field is set, and Undo
  /// puts the earlier value back.
  Future<void> moveCard(
      TaskItem t, KanbanGroup group, String key, String label) {
    return _guard(() async {
      var move = moveFor(group, key, t);
      if (move is NoMove) return;
      if (move is PickDayMove) {
        final c = await showRescheduleSheet(_context, title: 'Move to $label');
        if (c == null) return;
        move = DayMove(c.day);
      }
      await _perform(t, move);
      _refresh();
      _say('Moved to $label: ${t.title}', undo: () => _undoMove(t, group));
    });
  }

  Future<void> _perform(TaskItem t, KanbanMove move) async {
    switch (move) {
      case PatchMove(:final patch):
        await _repo.update(t.id, patch);
      case DayMove(:final day):
        await _repo.update(t.id, {'due_date': day == null ? null : isoDay(day)});
      case CompleteMove():
        await _repo.complete(t.id);
      case ReopenMove(:final then):
        await _repo.reopen(t.id);
        if (then != null) await _repo.update(t.id, then);
      case PickDayMove():
      case NoMove():
        break;
    }
  }

  Future<void> _undoMove(TaskItem before, KanbanGroup group) =>
      _guard(() async {
        switch (group) {
          case KanbanGroup.due:
            await _repo.update(before.id, {'due_date': before.dueDate});
          case KanbanGroup.status:
            if (before.isDone) {
              await _repo.complete(before.id);
            } else {
              try {
                await _repo.reopen(before.id);
              } on ApiException {
                // It was not finished, so there is nothing to reopen.
              }
              await _repo.update(before.id, {'status': before.status});
            }
          case KanbanGroup.project:
            await _repo.update(before.id, {'project_id': before.projectId});
          case KanbanGroup.priority:
            await _repo.update(before.id, {'priority': before.priority});
        }
        _refresh();
      });

  /// Delete asks first, then offers Undo, which restores the same task
  /// (id, steps and comments).
  Future<bool> delete(TaskItem t) async {
    final ok = await showDialog<bool>(
      context: _context,
      builder: (c) => AlertDialog(
        title: const Text('Delete this task?'),
        content: Text(t.title),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(c, false),
              child: const Text('Cancel')),
          TextButton(
              key: const Key('confirm-delete'),
              onPressed: () => Navigator.pop(c, true),
              child: const Text('Delete',
                  style: TextStyle(color: Tokens.danger))),
        ],
      ),
    );
    if (ok != true) return false;
    var removed = false;
    await _guard(() async {
      await _repo.remove(t.id);
      removed = true;
      _refresh();
      _say('Deleted: ${t.title}', undo: () => _bringBack(t.id));
    });
    return removed;
  }

  Future<void> _bringBack(String id) => _guard(() async {
        await _repo.restore(id);
        _refresh();
      });
}

/// A sheet listing the user's projects; null result means "cancelled", a
/// [_NoProject] result means unlink.
Future<({ProjectRef? project})?> pickProject(
  BuildContext context,
  List<ProjectRef> projects,
) {
  return showModalBottomSheet<({ProjectRef? project})>(
    context: context,
    showDragHandle: true,
    isScrollControlled: true,
    builder: (c) => SafeArea(
      child: ListView(
        shrinkWrap: true,
        children: [
          const Padding(
            padding: EdgeInsets.symmetric(horizontal: Tokens.space4),
            child: Text('Move to project',
                style: TextStyle(
                    fontSize: Tokens.fsHeading, fontWeight: FontWeight.w600)),
          ),
          ListTile(
            title: const Text('No project'),
            onTap: () => Navigator.pop(c, (project: null)),
          ),
          for (final p in projects)
            ListTile(
              key: Key('project-${p.id}'),
              title: Text(p.name),
              onTap: () => Navigator.pop(c, (project: p)),
            ),
        ],
      ),
    ),
  );
}
