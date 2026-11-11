import 'dart:async';
import 'dart:io' show Platform;

import 'package:flutter/foundation.dart';
import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:web_socket_channel/io.dart';

import '../api/session_store.dart';
import '../util/app_time.dart';
import 'alert_pump.dart';
import 'alert_rules.dart';
import 'local_alerts.dart';
import 'notify_prefs.dart';
import 'notify_store.dart';

/// The Stay connected notification's id, and how often the service rereads
/// your settings (they are also sent the moment you change them).
const stayConnectedServiceId = 4180;
const prefsRefresh = Duration(minutes: 1);

/// Messages the app sends to the running service.
Map<String, Object?> focusMessage(AppFocus focus) => {'focus': focus.toJson()};
const prefsChangedMessage = {'prefs': 'changed'};

/// The service's entry point: a top-level function Android starts again after
/// a reboot or an app update while Stay connected is on.
@pragma('vm:entry-point')
void startStayConnected() => FlutterForegroundTask.setTaskHandler(StayConnectedHandler());

class StayConnectedHandler extends TaskHandler {
  final NotifyStore _store = const DeviceNotifyStore();
  NotifyPrefs _prefs = const NotifyPrefs(stayConnected: true);
  AlertPump? _pump;

  /// Where you are, kept even before the pump exists (a focus message can come while it starts).
  AppFocus _focus = AppFocus.away;

  @override
  Future<void> onStart(DateTime timestamp, TaskStarter starter) async {
    await _reload();
    _pump = AlertPump(
      session: SecureSessionStore(),
      open: (uri, headers) => IOWebSocketChannel.connect(uri, headers: headers),
      presenter: DeviceAlertPresenter(),
      prefs: () => _prefs,
    )
      ..focus = _focus
      ..start();
  }

  @override
  void onRepeatEvent(DateTime timestamp) => unawaited(_reload());

  @override
  void onReceiveData(Object data) {
    if (data is! Map) return;
    if (data.containsKey('focus')) {
      _focus = AppFocus.fromJson(data['focus']);
      _pump?.focus = _focus;
    }
    if (data.containsKey('prefs')) unawaited(_reload());
  }

  /// Your settings, and the kept account zone quiet hours are read in (the
  /// service runs apart from the app, so it reads the kept copy).
  Future<void> _reload() async {
    _prefs = await _store.load();
    setAppZone(await SecureSessionStore().readTimezone());
  }

  @override
  void onNotificationPressed() => FlutterForegroundTask.launchApp('/');

  @override
  Future<void> onDestroy(DateTime timestamp, bool isTimeout) async => _pump?.stop();
}

/// What Settings asks of the phone; faked in tests.
abstract interface class StayConnectedControl {
  Future<bool> start();
  Future<void> stop();
  Future<bool> askNotifications();
  Future<bool> batteryFree();
  Future<void> openBatterySettings();
  void send(Object message);
}

/// The manifest's meta-data that names the white notification icon (`@drawable/ic_stat_roost`).
const stayConnectedIconMeta = 'app.roost.roost_mobile.NOTIFICATION_ICON';

class DeviceStayConnected implements StayConnectedControl {
  const DeviceStayConnected();

  static bool get _android => !kIsWeb && Platform.isAndroid;

  static void _init() => FlutterForegroundTask.init(
        androidNotificationOptions: AndroidNotificationOptions(
          channelId: 'roost_connected',
          channelName: 'Stay connected',
          channelDescription: 'Shown while Roost keeps a link to your Mac for alerts.',
          channelImportance: NotificationChannelImportance.MIN,
          priority: NotificationPriority.MIN,
          onlyAlertOnce: true,
        ),
        iosNotificationOptions: const IOSNotificationOptions(showNotification: false),
        foregroundTaskOptions: ForegroundTaskOptions(
          eventAction: ForegroundTaskEventAction.repeat(prefsRefresh.inMilliseconds),
          autoRunOnBoot: true,
          autoRunOnMyPackageReplaced: true,
          allowWakeLock: true,
          allowWifiLock: true,
        ),
      );

  @override
  Future<bool> start() async {
    if (!_android) return false;
    _init();
    if (await FlutterForegroundTask.isRunningService) {
      return (await FlutterForegroundTask.restartService()) is ServiceRequestSuccess;
    }
    final result = await FlutterForegroundTask.startService(
      serviceId: stayConnectedServiceId,
      serviceTypes: const [ForegroundServiceTypes.remoteMessaging],
      notificationTitle: 'Roost',
      notificationText: reconnectingLine,
      notificationInitialRoute: '/',
      notificationIcon: const NotificationIcon(metaDataName: stayConnectedIconMeta),
      callback: startStayConnected,
    );
    return result is ServiceRequestSuccess;
  }

  @override
  Future<void> stop() async {
    if (_android && await FlutterForegroundTask.isRunningService) await FlutterForegroundTask.stopService();
  }

  @override
  Future<bool> askNotifications() async {
    if (!_android) return false;
    var permission = await FlutterForegroundTask.checkNotificationPermission();
    if (permission != NotificationPermission.granted) {
      permission = await FlutterForegroundTask.requestNotificationPermission();
    }
    return permission == NotificationPermission.granted;
  }

  @override
  Future<bool> batteryFree() async => !_android || await FlutterForegroundTask.isIgnoringBatteryOptimizations;

  @override
  Future<void> openBatterySettings() async {
    if (_android) await FlutterForegroundTask.requestIgnoreBatteryOptimization();
  }

  @override
  void send(Object message) {
    if (_android) FlutterForegroundTask.sendDataToTask(message);
  }
}
