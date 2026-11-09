import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// Only MIT, BSD, Apache-2.0 (or equivalent) packages, checked on pub.dev
/// before they are added here (docs/plans/2026-10-22-roost-mobile-flutter.md §2).
const allowedPackages = {
  'flutter', 'flutter_test', 'flutter_lints', 'cupertino_icons', // Flutter SDK, BSD-3
  'flutter_riverpod', // MIT
  'go_router', // BSD-3
  'record', // BSD-3 (voice: the composer's mic)
  'just_audio', // MIT, with Apache-2.0 parts (voice: replies read aloud)
  'wakelock_plus', // BSD-3 (a call keeps the screen on)
  'audio_session', // MIT (a call's Speaker switch; already just_audio's)
  'dio', // MIT
  'web_socket_channel', // BSD-3
  'flutter_secure_storage', // BSD-3
  'flutter_markdown_plus', // BSD-3
  'intl', // BSD-3
  'timezone', // BSD-2
  'share_plus', // BSD-3 (Share as Template)
  'image_picker', // BSD-3 (bot picture upload)
  'crypto', // BSD-3, the Dart team (sha256 of a downloaded update)
  'webview_flutter',// BSD-3 (M3)
  'flutter_foreground_task', // MIT (Stay connected: the notifications service)
  'flutter_local_notifications', // BSD-3 (its Linux part pulls dbus, MPL-2.0)
};

List<String> declaredPackages(String pubspec) {
  final names = <String>[];
  var inDeps = false;
  for (final line in pubspec.split('\n')) {
    if (RegExp(r'^(dependencies|dev_dependencies|dependency_overrides):')
        .hasMatch(line)) {
      inDeps = true;
      continue;
    }
    if (RegExp(r'^\S').hasMatch(line)) inDeps = false;
    final match = RegExp(r'^  ([a-z0-9_]+):').firstMatch(line);
    if (inDeps && match != null) names.add(match.group(1)!);
  }
  return names;
}

void main() {
  test('every dependency is on the licence allowlist', () {
    final declared = declaredPackages(File('pubspec.yaml').readAsStringSync());
    expect(declared, isNotEmpty);
    final refused = declared.where((n) => !allowedPackages.contains(n));
    expect(refused, isEmpty, reason: 'Not on the licence allowlist: $refused');
  });

  test('the gate catches an unknown package', () {
    const bad =
        'dependencies:\n  flutter:\n    sdk: flutter\n  gpl_thing: ^1.0.0\n';
    expect(declaredPackages(bad), ['flutter', 'gpl_thing']);
  });
}
