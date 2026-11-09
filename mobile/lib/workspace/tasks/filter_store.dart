import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'task_filter.dart';

const _filterKey = 'roost_task_filter';

/// Where the Tasks chips are kept between launches: on this phone only.
abstract interface class TaskFilterStore {
  Future<TaskFilter> load();
  Future<void> save(TaskFilter filter);
}

/// The phone's small key-value storage (the same one the notification
/// settings use). A storage problem only means the chips start empty.
class DeviceTaskFilterStore implements TaskFilterStore {
  const DeviceTaskFilterStore();

  @override
  Future<TaskFilter> load() async {
    try {
      final raw = await FlutterForegroundTask.getData<String>(key: _filterKey);
      return raw == null ? const TaskFilter() : TaskFilter.fromJson(jsonDecode(raw));
    } catch (e) {
      debugPrint('Task filter could not be read: $e');
      return const TaskFilter();
    }
  }

  @override
  Future<void> save(TaskFilter filter) async {
    try {
      await FlutterForegroundTask.saveData(
          key: _filterKey, value: jsonEncode(filter.toJson()));
    } catch (e) {
      debugPrint('Task filter could not be kept: $e');
    }
  }
}

/// Tests: a store in memory.
class MemoryTaskFilterStore implements TaskFilterStore {
  MemoryTaskFilterStore([this.saved = const TaskFilter()]);

  TaskFilter saved;

  @override
  Future<TaskFilter> load() async => saved;

  @override
  Future<void> save(TaskFilter filter) async => saved = filter;
}

final taskFilterStoreProvider =
    Provider<TaskFilterStore>((_) => const DeviceTaskFilterStore());

/// The chips that are on. Starts empty (All), then picks up what this phone
/// kept, unless you tapped a chip first.
class TaskFilterController extends Notifier<TaskFilter> {
  bool _touched = false;

  @override
  TaskFilter build() {
    _touched = false;
    _load();
    return const TaskFilter();
  }

  Future<void> _load() async {
    final kept = await ref.read(taskFilterStoreProvider).load();
    if (!_touched) state = kept;
  }

  void _set(TaskFilter next) {
    _touched = true;
    state = next;
    ref.read(taskFilterStoreProvider).save(next);
  }

  void toggleDate(DateFilter d) => _set(state.toggleDate(d));
  void toggleHigh() => _set(state.toggleHigh());
  void toggleDone() => _set(state.toggleDone());
  void toggleProject(String id) => _set(state.toggleProject(id));
  void clear() => _set(const TaskFilter());
}

final taskFilterProvider =
    NotifierProvider<TaskFilterController, TaskFilter>(TaskFilterController.new);
