import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/api/providers.dart';
import 'package:roost_mobile/api/session_store.dart';
import 'package:roost_mobile/features/settings/notifications_screen.dart';
import 'package:roost_mobile/notify/alert_rules.dart';
import 'package:roost_mobile/notify/notify_prefs.dart';
import 'package:roost_mobile/notify/notify_providers.dart';
import 'package:roost_mobile/notify/notify_store.dart';
import 'package:roost_mobile/notify/stay_connected.dart';

import '../fake_adapter.dart';

class FakeControl implements StayConnectedControl {
  bool allowed = true;
  bool starts = true;
  bool battery = false;
  int started = 0, stopped = 0, batteryOpened = 0;
  final sent = <Object>[];

  @override
  Future<bool> askNotifications() async => allowed;
  @override
  Future<bool> batteryFree() async => battery;
  @override
  Future<void> openBatterySettings() async => batteryOpened++;
  @override
  void send(Object message) => sent.add(message);
  @override
  Future<bool> start() async {
    started++;
    return starts;
  }

  @override
  Future<void> stop() async => stopped++;
}

final bots = FakeAdapter((o) => FakeAdapter.json([
      {'id': 'b1', 'name': 'Chief', 'notify': true},
    ]));

Future<(ProviderContainer, FakeControl, MemoryNotifyStore)> pumpScreen(WidgetTester tester,
    {NotifyPrefs prefs = const NotifyPrefs(), FakeControl? control}) async {
  await tester.binding.setSurfaceSize(const Size(390, 1400));
  final fake = control ?? FakeControl();
  final store = MemoryNotifyStore(prefs);
  final container = ProviderContainer(overrides: [
    sessionStoreProvider.overrideWithValue(MemorySessionStore()),
    httpAdapterProvider.overrideWithValue(bots),
    notifyStoreProvider.overrideWithValue(store),
    stayConnectedProvider.overrideWithValue(fake),
  ]);
  addTearDown(container.dispose);
  await tester.pumpWidget(UncontrolledProviderScope(
    container: container,
    child: const MaterialApp(home: NotificationsScreen()),
  ));
  await tester.pumpAndSettle();
  return (container, fake, store);
}

void main() {
  testWidgets('Stay connected asks for notifications, then starts the service', (tester) async {
    final (_, control, store) = await pumpScreen(tester);
    expect(find.text('Stay connected'), findsOneWidget);
    await tester.tap(find.byKey(const Key('stay-connected')));
    await tester.pumpAndSettle();
    expect(control.started, 1);
    expect(store.prefs.stayConnected, isTrue);
    expect(find.byKey(const Key('battery-free')), findsOneWidget);
  });

  testWidgets('notifications refused: it stays off and says why', (tester) async {
    final (_, control, store) = await pumpScreen(tester, control: FakeControl()..allowed = false);
    await tester.tap(find.byKey(const Key('stay-connected')));
    await tester.pumpAndSettle();
    expect(control.started, 0);
    expect(store.prefs.stayConnected, isFalse);
    expect(find.text(notificationsDeniedText), findsOneWidget);
  });

  testWidgets('turning it off stops the service', (tester) async {
    final (_, control, store) = await pumpScreen(tester, prefs: const NotifyPrefs(stayConnected: true));
    await tester.tap(find.byKey(const Key('stay-connected')));
    await tester.pumpAndSettle();
    expect(control.stopped, 1);
    expect(store.prefs.stayConnected, isFalse);
  });

  testWidgets('each kind has its switch, saved and sent to the service', (tester) async {
    final (_, control, store) = await pumpScreen(tester, prefs: const NotifyPrefs(stayConnected: true));
    await tester.tap(find.byKey(const Key('alert-replies')));
    await tester.pumpAndSettle();
    expect(store.prefs.replies, isFalse);
    expect(control.sent, contains(prefsChangedMessage));
  });

  testWidgets('quiet hours show their Madrid times once on', (tester) async {
    final (_, _, store) = await pumpScreen(tester, prefs: const NotifyPrefs(stayConnected: true));
    expect(find.text('23:00'), findsNothing);
    await tester.tap(find.byKey(const Key('quiet-on')));
    await tester.pumpAndSettle();
    expect(store.prefs.quietOn, isTrue);
    expect(find.text('23:00'), findsOneWidget);
    expect(find.text('07:00'), findsOneWidget);
  });

  testWidgets('battery: a button opens the setting while Roost may be stopped', (tester) async {
    final (_, control, _) = await pumpScreen(tester, prefs: const NotifyPrefs(stayConnected: true));
    await tester.tap(find.byKey(const Key('battery-free')));
    await tester.pumpAndSettle();
    expect(control.batteryOpened, 1);
  });

  testWidgets("each bot's own switch is still there", (tester) async {
    await pumpScreen(tester);
    expect(find.byKey(const Key('notify-b1')), findsOneWidget);
  });

  test('the service hears where you are: the open chat, or away', () async {
    final control = FakeControl();
    final c = ProviderContainer(overrides: [
      notifyStoreProvider.overrideWithValue(MemoryNotifyStore()),
      stayConnectedProvider.overrideWithValue(control),
    ]);
    addTearDown(c.dispose);
    c.read(stayConnectedSyncProvider);
    c.read(openChatProvider.notifier).state = 'b1';
    await Future<void>.delayed(Duration.zero);
    c.read(appVisibleProvider.notifier).state = false;
    await Future<void>.delayed(Duration.zero);
    expect(control.sent, [
      focusMessage(const AppFocus(visible: true)),
      focusMessage(const AppFocus(visible: true, openChatBotId: 'b1')),
      focusMessage(AppFocus.away),
    ]);
  });

  test('opening the app starts the service again when it is meant to be on', () async {
    final control = FakeControl();
    final c = ProviderContainer(overrides: [
      notifyStoreProvider.overrideWithValue(MemoryNotifyStore(const NotifyPrefs(stayConnected: true))),
      stayConnectedProvider.overrideWithValue(control),
    ]);
    addTearDown(c.dispose);
    c.read(stayConnectedSyncProvider);
    await c.read(notifyPrefsProvider.future);
    await Future<void>.delayed(Duration.zero);
    expect(control.started, 1);
  });

  test('a service that starts after the app hears the open chat again (no alerts for the chat you read)', () async {
    final control = FakeControl();
    final c = ProviderContainer(overrides: [
      notifyStoreProvider.overrideWithValue(MemoryNotifyStore(const NotifyPrefs(stayConnected: true))),
      stayConnectedProvider.overrideWithValue(control),
    ]);
    addTearDown(c.dispose);
    c.read(openChatProvider.notifier).state = 'b1';
    c.read(stayConnectedSyncProvider);
    await c.read(notifyPrefsProvider.future);
    await Future<void>.delayed(Duration.zero);
    expect(control.started, 1);
    expect(control.sent.last, focusMessage(const AppFocus(visible: true, openChatBotId: 'b1')));
    expect(control.sent.length, 2);
  });
}
