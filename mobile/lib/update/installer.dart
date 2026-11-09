import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

/// Hands a downloaded APK to Android's own installer. The Android side is a
/// small method channel in `MainActivity.kt` (no plugin): it gives the cache
/// folder for updates, says whether Roost may install apps, opens that
/// setting, and starts the install prompt through a FileProvider.
abstract class UpdateInstaller {
  /// The folder downloads go to (inside the app's own cache).
  Future<String> cacheDir();

  /// Whether "Install unknown apps" is on for Roost.
  Future<bool> canInstall();

  /// Opens Android's "Install unknown apps" screen for Roost.
  Future<void> openInstallSettings();

  /// Shows Android's install prompt for the APK at [path].
  Future<void> install(String path);
}

const installerChannelName = 'roost/installer';

class ChannelInstaller implements UpdateInstaller {
  const ChannelInstaller([this._channel = const MethodChannel(installerChannelName)]);

  final MethodChannel _channel;

  @override
  Future<String> cacheDir() async {
    final dir = await _channel.invokeMethod<String>('cacheDir');
    if (dir == null || dir.isEmpty) {
      throw PlatformException(code: 'no-cache', message: 'No cache folder.');
    }
    return dir;
  }

  @override
  Future<bool> canInstall() async =>
      await _channel.invokeMethod<bool>('canInstall') ?? false;

  @override
  Future<void> openInstallSettings() =>
      _channel.invokeMethod<void>('openInstallSettings');

  @override
  Future<void> install(String path) =>
      _channel.invokeMethod<void>('install', {'path': path});
}

/// Overridden in tests with a fake.
final installerProvider =
    Provider<UpdateInstaller>((ref) => const ChannelInstaller());
