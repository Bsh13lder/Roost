import 'dart:convert';

import 'package:flutter_foreground_task/flutter_foreground_task.dart';

import 'notify_prefs.dart';

const _prefsKey = 'roost_notify_prefs';

/// Where the notification settings live: one small JSON on the phone that the
/// app writes and the Stay connected service reads.
abstract interface class NotifyStore {
  Future<NotifyPrefs> load();
  Future<void> save(NotifyPrefs prefs);
}

/// The plugin's shared storage, readable from the service's own isolate.
class DeviceNotifyStore implements NotifyStore {
  const DeviceNotifyStore();

  @override
  Future<NotifyPrefs> load() async {
    final raw = await FlutterForegroundTask.getData<String>(key: _prefsKey);
    if (raw == null) return const NotifyPrefs();
    try {
      return NotifyPrefs.fromJson(jsonDecode(raw));
    } on FormatException {
      return const NotifyPrefs();
    }
  }

  @override
  Future<void> save(NotifyPrefs prefs) =>
      FlutterForegroundTask.saveData(key: _prefsKey, value: jsonEncode(prefs.toJson()));
}

/// Tests: a store in memory.
class MemoryNotifyStore implements NotifyStore {
  MemoryNotifyStore([this.prefs = const NotifyPrefs()]);

  NotifyPrefs prefs;

  @override
  Future<NotifyPrefs> load() async => prefs;

  @override
  Future<void> save(NotifyPrefs next) async => prefs = next;
}
