import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../board/tasks/task_models.dart';
import '../../board/tasks/task_repo.dart';
import '../show_toggles.dart';
import '../workspace_state.dart';
import 'filter_store.dart';
import 'task_filter.dart';

/// Every open task, soonest due first (the server's `GET /api/tasks` with
/// no view: open tasks sorted by due, then priority). One list feeds every
/// chip, so a tap filters at once with no new request.
const openTasksQuery = 'sort=due';

/// The done tasks, newest first; asked for only while Done is on.
const doneTasksQuery = 'view=done';

const _none = AsyncValue<List<TaskItem>>.data(<TaskItem>[]);

/// The open list alone, for the chips' counts.
final openTasksProvider = Provider.autoDispose<List<TaskItem>>(
    (ref) => ref.watch(taskListProvider(openTasksQuery)).valueOrNull ?? const []);

/// What the Tasks list shows: the chips and the typed words applied to the
/// open list (and the done list when Done is on), less the tasks a bot made
/// while Show › Made by bots is off. A reload keeps the old rows on screen
/// until the new ones arrive.
final shownTasksProvider =
    Provider.autoDispose<AsyncValue<List<TaskItem>>>((ref) {
  final filter = ref.watch(taskFilterProvider);
  final typed = ref.watch(workspaceQueryProvider);
  final botMade = ref.watch(screenTogglesProvider(screenTasks)).botMade;
  final open = ref.watch(taskListProvider(openTasksQuery));
  final done = filter.done ? ref.watch(taskListProvider(doneTasksQuery)) : _none;
  if (open.hasValue && done.hasValue) {
    final shown = applyFilter(filter,
        open: open.requireValue, done: done.requireValue, typed: typed);
    return AsyncValue.data(keepMade(shown, show: botMade));
  }
  final failed = open.hasError ? open : done;
  if (failed.hasError) {
    return AsyncValue.error(failed.error!, failed.stackTrace ?? StackTrace.empty);
  }
  return const AsyncValue.loading();
});

/// Reloads both lists (pull to refresh, Try again).
void reloadTaskLists(WidgetRef ref) {
  ref.invalidate(taskListProvider(openTasksQuery));
  ref.invalidate(taskListProvider(doneTasksQuery));
  ref.invalidate(taskCountsProvider);
}

/// The sections folded on this phone for now ("overdue", "2026-10-27").
final foldedSectionsProvider = StateProvider<Set<String>>((_) => const {});

/// [tasks] less the ones a bot made, unless they [show].
List<TaskItem> keepMade(List<TaskItem> tasks, {required bool show}) =>
    show ? tasks : [for (final t in tasks) if (t.createdByBot == null) t];
