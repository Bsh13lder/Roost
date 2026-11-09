import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../api/api_client.dart';
import '../../api/providers.dart';
import '../../live/live_connection.dart';
import 'paste_list.dart';
import 'quick_draft.dart';
import 'task_dates.dart';
import 'task_models.dart';

Map<String, dynamic> _map(Object? o) => (o as Map).cast<String, dynamic>();

/// Every call the Tasks screens make; the server does the thinking.
class TaskRepo {
  const TaskRepo(this._api);

  final ApiClient _api;

  /// Any list the server can answer: the Kanban's `view=board`, or the
  /// Calendar's `from` and `to` (at most 62 days).
  Future<List<TaskItem>> query(Map<String, String> params) async {
    final data =
        await _api.get('/api/tasks?${Uri(queryParameters: params).query}');
    return [for (final j in (data as List)) TaskItem.fromJson(_map(j))];
  }

  Future<TaskCounts> counts() async =>
      TaskCounts.fromJson(_map(await _api.get('/api/tasks/counts')));

  Future<List<ProjectRef>> projects() async {
    final data = await _api.get('/api/projects');
    return [for (final j in (data as List)) ProjectRef.fromJson(_map(j))];
  }

  Future<Map<String, dynamic>> detail(String id) async =>
      _map(await _api.get('/api/tasks/$id'));

  Future<QuickReading> parse(String text) => parseDraft(QuickDraft(text: text));

  /// Reads a quick line with its `skip`, `keep` and `default_due`.
  Future<QuickReading> parseDraft(QuickDraft draft) async => QuickReading(
      _map(await _api.post('/api/tasks/parse', draft.parseBody())));

  /// Reads a pasted list, one task per line (`POST /api/tasks/parse-many`);
  /// it changes nothing.
  Future<PastedList> parseMany(String text) async => PastedList.fromJson(
      _map(await _api.post('/api/tasks/parse-many', {'text': text})));

  Future<TaskItem> create(Map<String, dynamic> body) async =>
      TaskItem.fromJson(_map(await _api.post('/api/tasks', body)));

  Future<TaskItem> update(String id, Map<String, dynamic> patch) async =>
      TaskItem.fromJson(_map(await _api.patch('/api/tasks/$id', patch)));

  /// A line typed with no connection (offline tasks, O4): the server reads
  /// it as of its typed time and makes it once per client id.
  Future<TaskItem> createOffline(Map<String, dynamic> body) async =>
      TaskItem.fromJson(_map(await _api.post('/api/tasks/offline', body)));

  Future<void> complete(String id) => _api.post('/api/tasks/$id/complete');

  Future<void> reopen(String id) => _api.post('/api/tasks/$id/reopen');

  /// Closes an open task as failed (a reminder card's Failed).
  Future<void> fail(String id) => _api.post('/api/tasks/$id/fail');

  Future<void> remove(String id) => _api.delete('/api/tasks/$id');

  /// Delete's exact Undo: the same task, id, steps and comments come back.
  Future<void> restore(String id) => _api.post('/api/tasks/$id/restore');

  /// Every open overdue task gets [to]; the answer holds the old values.
  Future<List<Map<String, dynamic>>> moveOverdue(String? to) async {
    final r = _map(await _api.post('/api/tasks/move-overdue', {'to': to}));
    return [for (final m in (r['moved'] as List)) _map(m)];
  }

  Future<void> restoreDues(List<Map<String, dynamic>> items) =>
      _api.post('/api/tasks/restore-dues', {'items': items});

  Future<void> addStep(String id, String title) =>
      _api.post('/api/tasks/$id/steps', {'title': title});

  Future<void> patchStep(String id, String stepId, Map<String, dynamic> p) =>
      _api.patch('/api/tasks/$id/steps/$stepId', p);

  Future<void> moveStep(String id, String stepId, int position) =>
      _api.post('/api/tasks/$id/steps/$stepId/move', {'position': position});

  Future<void> deleteStep(String id, String stepId) =>
      _api.delete('/api/tasks/$id/steps/$stepId');

  /// A step's own budget in the task's currency, as typed (the server reads
  /// it); null clears it.
  Future<void> setStepBudget(String id, String stepId, String? budget) =>
      _api.patch('/api/tasks/$id/steps/$stepId', {'budget': budget});

  /// An expense filed under the task or one of its steps. With no [day] the
  /// server takes the account's today; it also reads words like "yesterday".
  Future<void> addExpense(String id,
          {required String amount, String? stepId, String? note, String? day}) =>
      _api.post('/api/money/expenses', {
        'amount': amount,
        'task_id': id,
        'step_id': ?stepId,
        'note': ?note,
        'spent_at': ?day,
      });

  Future<List<TaskComment>> comments(String id) async {
    final data = await _api.get('/api/tasks/$id/comments');
    return [for (final j in (data as List)) TaskComment.fromJson(_map(j))];
  }

  Future<void> addComment(String id, String body, {String? stepId}) =>
      _api.post('/api/tasks/$id/comments',
          {'body': body, 'step_id': ?stepId});

  Future<void> editComment(String commentId, String body) =>
      _api.patch('/api/comments/$commentId', {'body': body});

  Future<void> deleteComment(String commentId) =>
      _api.delete('/api/comments/$commentId');
}

final taskRepoProvider =
    Provider<TaskRepo>((ref) => TaskRepo(ref.watch(apiClientProvider)));

/// Reloads its provider when the gateway says a task changed anywhere.
void reloadOnTasksChanged(Ref ref) {
  final sub = ref
      .read(frameBusProvider)
      .stream
      .where((f) => f['type'] == 'tasks_changed')
      .listen((_) => ref.invalidateSelf());
  ref.onDispose(sub.cancel);
}

/// Any task list by its query string (`view=today&project_id=p1`).
final taskListProvider =
    FutureProvider.autoDispose.family<List<TaskItem>, String>((ref, query) {
  reloadOnTasksChanged(ref);
  return ref.watch(taskRepoProvider).query(Uri.splitQueryString(query));
});

final taskCountsProvider = FutureProvider.autoDispose<TaskCounts>((ref) {
  reloadOnTasksChanged(ref);
  return ref.watch(taskRepoProvider).counts();
});

final taskProjectsProvider = FutureProvider.autoDispose<List<ProjectRef>>(
    (ref) => ref.watch(taskRepoProvider).projects());

final taskDetailProvider = FutureProvider.autoDispose
    .family<Map<String, dynamic>, String>((ref, id) {
  reloadOnTasksChanged(ref);
  return ref.watch(taskRepoProvider).detail(id);
});

final taskCommentsProvider = FutureProvider.autoDispose
    .family<List<TaskComment>, String>((ref, id) {
  reloadOnTasksChanged(ref);
  return ref.watch(taskRepoProvider).comments(id);
});

final kanbanTasksProvider = FutureProvider.autoDispose<List<TaskItem>>((ref) {
  reloadOnTasksChanged(ref);
  return ref.watch(taskRepoProvider).query({'view': 'board', 'sort': 'due'});
});

/// The tasks due in one month ("2026-10"), first day to last.
final monthTasksProvider =
    FutureProvider.autoDispose.family<List<TaskItem>, String>((ref, month) {
  reloadOnTasksChanged(ref);
  final first = DateTime.parse('$month-01');
  final last = DateTime(first.year, first.month + 1, 0);
  return ref
      .watch(taskRepoProvider)
      .query({'from': isoDay(first), 'to': isoDay(last)});
});
