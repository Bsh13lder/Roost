import 'package:flutter/foundation.dart';
import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';

import '../api/models.dart' show Avatar;
import '../widgets/lensbot_png.dart';
import 'alert_pump.dart';
import 'alert_rules.dart';

/// The small icon: Roost's bot as a white silhouette (Android draws it from alpha alone).
const alertIcon = '@drawable/ic_stat_roost';

/// One Android channel per kind, so each can be tuned in the phone's own
/// settings too.
const _channels = {
  AlertKind.needsOk: ('roost_needs_ok', 'Needs your OK', Importance.high),
  AlertKind.reminder: ('roost_reminders', 'Task reminders', Importance.high),
  AlertKind.report: ('roost_reports', 'Reports', Importance.defaultImportance),
  AlertKind.reply: ('roost_replies', 'Replies', Importance.defaultImportance),
};

/// A bot's face on its notifications: this many pixels a side.
const alertFaceSize = 96;

/// How an alert looks on Android: its channel, and the bot's face (when one
/// was drawn) as the large icon in the bot's own colour.
AndroidNotificationDetails alertDetails(Alert alert, Uint8List? face) {
  final (id, name, importance) = _channels[alert.kind]!;
  return AndroidNotificationDetails(
    id,
    name,
    importance: importance,
    priority: importance == Importance.high ? Priority.high : Priority.defaultPriority,
    category: alert.kind == AlertKind.reply ? AndroidNotificationCategory.message : null,
    largeIcon: face == null ? null : ByteArrayAndroidBitmap(face),
    color: alert.avatar?.colour,
  );
}

/// Each bot's face, drawn once per look.
class AlertFaces {
  final Map<String, Uint8List> _drawn = {};

  /// The face PNG, or null when it can't be drawn (the alert shows anyway).
  Future<Uint8List?> of(Avatar? look) async {
    if (look == null) return null;
    final key = '${look.shape}|${look.color}';
    final kept = _drawn[key];
    if (kept != null) return kept;
    try {
      final png = await lensbotPng(colour: look.colour, shape: look.shape, size: alertFaceSize, fill: 0.86);
      _drawn[key] = png;
      return png;
    } catch (e) {
      debugPrint('a bot face could not be drawn for a notification: $e');
      return null;
    }
  }
}

/// The payload of an alert: the bot whose chat a tap opens.
String alertPayload(Alert alert) => 'chat:${alert.botId}';

/// The route a tapped alert opens, or null for anything else.
String? routeForPayload(String? payload) {
  if (payload == null || !payload.startsWith('chat:')) return null;
  final botId = payload.substring(5);
  return RegExp(r'^[A-Za-z0-9-]{1,64}$').hasMatch(botId) ? '/chat/$botId' : null;
}

FlutterLocalNotificationsPlugin? _plugin;

/// The one notifications plugin of this isolate, set up once.
Future<FlutterLocalNotificationsPlugin> alertsPlugin({
  void Function(NotificationResponse response)? onTap,
}) async {
  final existing = _plugin;
  if (existing != null) return existing;
  final plugin = FlutterLocalNotificationsPlugin();
  await plugin.initialize(
    settings: const InitializationSettings(android: AndroidInitializationSettings(alertIcon)),
    onDidReceiveNotificationResponse: onTap,
  );
  _plugin = plugin;
  return plugin;
}

/// Shows alerts as Android notifications and the status as the Stay
/// connected notification's line.
class DeviceAlertPresenter implements AlertPresenter {
  final AlertFaces _faces = AlertFaces();

  @override
  Future<void> show(Alert alert) async {
    final plugin = await alertsPlugin();
    final face = await _faces.of(alert.avatar);
    await plugin.show(
      id: alert.id,
      title: alert.title,
      body: alert.body,
      notificationDetails: NotificationDetails(android: alertDetails(alert, face)),
      payload: alertPayload(alert),
    );
  }

  @override
  Future<void> status(String line) async {
    await FlutterForegroundTask.updateService(notificationTitle: 'Roost', notificationText: line);
  }
}
