import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'alert_rules.dart';
import 'notify_prefs.dart';
import 'notify_store.dart';
import 'stay_connected.dart';

/// Overridden in tests with a [MemoryNotifyStore] and a fake control.
final notifyStoreProvider = Provider<NotifyStore>((ref) => const DeviceNotifyStore());
final stayConnectedProvider = Provider<StayConnectedControl>((ref) => const DeviceStayConnected());

const notificationsDeniedText =
    'Roost may not show notifications yet. Allow them in Android settings, then try again.';
const serviceRefusedText = "Android didn't start Stay connected. Try again.";

/// Your notification settings, saved on the phone. Every change reaches the
/// running service at once.
class NotifyPrefsController extends AsyncNotifier<NotifyPrefs> {
  @override
  Future<NotifyPrefs> build() async {
    try {
      return await ref.read(notifyStoreProvider).load();
    } catch (_) {
      return const NotifyPrefs(); // no shared storage (tests, a fresh phone): the defaults
    }
  }

  Future<void> change(NotifyPrefs next) async {
    await ref.read(notifyStoreProvider).save(next);
    state = AsyncData(next);
    ref.read(stayConnectedProvider).send(prefsChangedMessage);
  }

  /// Turns Stay connected on (asking for notifications first) or off. The
  /// sentence to show when it could not be turned on, else null.
  Future<String?> setStayConnected(bool on) async {
    final current = state.valueOrNull ?? const NotifyPrefs();
    final control = ref.read(stayConnectedProvider);
    if (!on) {
      await control.stop();
      await change(current.copyWith(stayConnected: false));
      return null;
    }
    if (!await control.askNotifications()) return notificationsDeniedText;
    await change(current.copyWith(stayConnected: true));
    if (await control.start()) return null;
    await change(current.copyWith(stayConnected: false));
    return serviceRefusedText;
  }
}

final notifyPrefsProvider =
    AsyncNotifierProvider<NotifyPrefsController, NotifyPrefs>(NotifyPrefsController.new);

/// The bot whose chat is open on screen, and whether the app is in front.
final openChatProvider = StateProvider<String?>((ref) => null);
final appVisibleProvider = StateProvider<bool>((ref) => true);

/// What the app shows, for the service: it never alerts about what you see.
final appFocusProvider = Provider<AppFocus>((ref) {
  if (!ref.watch(appVisibleProvider)) return AppFocus.away;
  return AppFocus(visible: true, openChatBotId: ref.watch(openChatProvider));
});

/// Keeps the service told where you are, and starts it again after the app
/// opens if it is meant to be on (an update or a force stop ended it).
final stayConnectedSyncProvider = Provider<void>((ref) {
  final control = ref.read(stayConnectedProvider);
  ref.listen<AppFocus>(appFocusProvider, (_, focus) => control.send(focusMessage(focus)), fireImmediately: true);
  ref.listen<AsyncValue<NotifyPrefs>>(notifyPrefsProvider, (was, now) {
    final first = was?.valueOrNull == null;
    if (first && (now.valueOrNull?.stayConnected ?? false)) {
      // A service that starts after the app missed the first focus message: tell it again, or it thinks you
      // are away and alerts about the chat you are reading (owner, 2026-11-10: "noisy when I am in the chat").
      unawaited(control.start().then((on) {
        if (on) control.send(focusMessage(ref.read(appFocusProvider)));
      }));
    }
  }, fireImmediately: true);
});
