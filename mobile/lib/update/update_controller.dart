import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:flutter/services.dart' show PlatformException;
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api_error.dart';
import '../api/providers.dart';
import '../app_version.dart';
import 'installer.dart';
import 'release.dart';

const damagedDownloadMessage =
    'The download was damaged, so it was not installed. Try again.';
const installPermissionMessage =
    'To install updates, turn on "Allow from this source" for Roost, then '
    'come back and tap Install again.';
const installFailedMessage =
    "Android couldn't start the install. Try again.";
const downloadFailedMessage =
    'The download stopped. Check the connection and try again.';

/// The app's own build number (overridden in tests).
final ownBuildProvider = Provider<int>((ref) => buildNumberOf(appVersion));

class UpdateState {
  const UpdateState({
    this.available,
    this.checking = false,
    this.upToDate = false,
    this.progress,
    this.error,
    this.note,
  });

  /// A newer build than this app, or null.
  final Release? available;
  final bool checking;

  /// A check finished and found nothing newer.
  final bool upToDate;

  /// 0..1 while downloading (null when not, or when the size is unknown: -1).
  final double? progress;
  final String? error;

  /// A calm one-line explanation (the install permission).
  final String? note;

  bool get downloading => progress != null;
}

class UpdateController extends Notifier<UpdateState> {
  @override
  UpdateState build() => const UpdateState();

  /// Asks the gateway for the newest build. Quiet when nothing is published;
  /// [quiet] also hides any other error (the check on start).
  Future<void> check({bool quiet = false}) async {
    if (state.checking || state.downloading) return;
    state = UpdateState(available: state.available, checking: true);
    try {
      final data = await ref.read(apiClientProvider).get('/api/mobile/latest');
      final release = Release.fromJson(data);
      final newer = release != null &&
          release.isNewerThan(ref.read(ownBuildProvider));
      state = UpdateState(
          available: newer ? release : null, upToDate: !newer);
    } on ApiException catch (e) {
      final none = e.status == 404;
      state = UpdateState(
        available: state.available,
        upToDate: none,
        error: none || quiet ? null : e.message,
      );
    }
  }

  /// Downloads the APK, checks its sha256 and hands it to Android.
  Future<void> install() async {
    final release = state.available;
    if (release == null || state.downloading) return;
    final installer = ref.read(installerProvider);
    try {
      if (!await installer.canInstall()) {
        state = UpdateState(available: release, note: installPermissionMessage);
        await installer.openInstallSettings();
        return;
      }
      final path = '${await installer.cacheDir()}/${release.file}';
      if (!await _download(release, path)) return;
      state = UpdateState(available: release);
      await installer.install(path);
    } on PlatformException {
      state = UpdateState(available: release, error: installFailedMessage);
    }
  }

  Future<bool> _download(Release release, String path) async {
    state = UpdateState(available: release, progress: 0);
    final file = File(path);
    try {
      await ref.read(apiClientProvider).download(
          '/api/mobile/apk/${release.file}', path,
          onProgress: (got, total) => state = UpdateState(
              available: release, progress: total > 0 ? got / total : 0));
      final digest = sha256.convert(await file.readAsBytes()).toString();
      if (digest == release.sha256) return true;
      await file.delete();
      state = UpdateState(available: release, error: damagedDownloadMessage);
    } on ApiException catch (e) {
      state = UpdateState(
          available: release,
          error: e.status == null ? downloadFailedMessage : e.message);
    } on FileSystemException {
      state = UpdateState(available: release, error: downloadFailedMessage);
    }
    return false;
  }
}

final updateProvider =
    NotifierProvider<UpdateController, UpdateState>(UpdateController.new);
