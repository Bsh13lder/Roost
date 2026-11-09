import 'dart:io' show Platform;

import 'package:audio_session/audio_session.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:wakelock_plus/wakelock_plus.dart';

/// The phone's own switches a call touches, behind providers so a test can
/// see them asked for without a platform. Each is best effort: a build
/// without the plugin changes nothing.

/// Keep the screen on while the call is up (`wakelock_plus`, BSD-3): a
/// locked screen would silence a backgrounded app's mic mid-"Thinking…".
typedef KeepScreenOn = Future<void> Function(bool on);

/// The loudspeaker (`audio_session`, MIT), Android only; on by default.
typedef Speakerphone = Future<void> Function(bool on);

final keepScreenOnProvider = Provider<KeepScreenOn>((ref) => _keepScreenOn);

final speakerphoneProvider = Provider<Speakerphone>((ref) => _speakerphone);

Future<void> _keepScreenOn(bool on) async {
  try {
    await WakelockPlus.toggle(enable: on);
  } catch (_) {
    // No wakelock here: the call still works.
  }
}

Future<void> _speakerphone(bool on) async {
  if (kIsWeb || !Platform.isAndroid) return;
  try {
    await AndroidAudioManager().setSpeakerphoneOn(on);
  } catch (_) {
    // Left to the phone's own routing.
  }
}
