import 'dart:typed_data';
import 'dart:ui';

import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/api/models.dart';
import 'package:roost_mobile/notify/alert_rules.dart';
import 'package:roost_mobile/notify/local_alerts.dart';

void main() {
  test("a tap opens the alert's bot chat, and nothing else", () {
    const alert = Alert(key: 'card:c1', kind: AlertKind.needsOk, botId: 'b-1', title: 't', body: 'b');
    expect(routeForPayload(alertPayload(alert)), '/chat/b-1');
    expect(routeForPayload(null), isNull);
    expect(routeForPayload('chat:'), isNull);
    expect(routeForPayload('chat:../settings'), isNull);
    expect(routeForPayload('https://evil.example'), isNull);
  });

  test("an alert carries its bot's face as the large icon, in the bot's colour", () {
    const alert = Alert(
        key: 'msg:m1', kind: AlertKind.reply, botId: 'b-1', title: 'Gela', body: 'hi',
        avatar: Avatar(shape: 'cheeky', color: '#8b5cf6'));
    final face = Uint8List.fromList([1, 2, 3]);
    final details = alertDetails(alert, face);
    expect(details.largeIcon, isA<ByteArrayAndroidBitmap>());
    expect(details.color, const Color(0xFF8B5CF6));
    expect(details.icon, isNull); // the plugin's small icon: ic_stat_roost
  });

  test('without a face the alert still shows, with no large icon', () {
    const alert = Alert(key: 'msg:m2', kind: AlertKind.report, botId: 'b-1', title: 't', body: 'b');
    expect(alertDetails(alert, null).largeIcon, isNull);
  });
}
