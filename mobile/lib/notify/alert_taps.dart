import 'dart:io' show Platform;

import 'package:flutter/foundation.dart';

import 'local_alerts.dart';

/// A tapped alert opens its bot's chat: a tap while the app runs, and the tap
/// that started the app. Android only; elsewhere it does nothing.
Future<void> openTappedAlerts(void Function(String route) go) async {
  if (kIsWeb || !Platform.isAndroid) return;
  final plugin = await alertsPlugin(onTap: (response) {
    final route = routeForPayload(response.payload);
    if (route != null) go(route);
  });
  final launch = await plugin.getNotificationAppLaunchDetails();
  if (launch?.didNotificationLaunchApp ?? false) {
    final route = routeForPayload(launch!.notificationResponse?.payload);
    if (route != null) go(route);
  }
}
