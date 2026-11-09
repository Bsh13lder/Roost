/// One published build of the phone app, as `GET /api/mobile/latest` gives it
/// (the gateway reads it from `latest.json`, written by
/// `scripts/publish_mobile.sh`).
library;

final _apkName = RegExp(r'^roost-[0-9.]+\+[0-9]+\.apk$');
final _sha256 = RegExp(r'^[0-9a-f]{64}$');
final _version = RegExp(r'^[0-9]+\.[0-9]+\.[0-9]+$');

/// The build number after the `+` in a version like `1.0.1+2`; 0 when there
/// is none, so any published build counts as newer.
int buildNumberOf(String version) {
  final plus = version.indexOf('+');
  if (plus < 0) return 0;
  return int.tryParse(version.substring(plus + 1)) ?? 0;
}

class Release {
  const Release({
    required this.version,
    required this.build,
    required this.file,
    required this.sha256,
    this.notes = '',
  });

  final String version;
  final int build;
  final String file;
  final String sha256;
  final String notes;

  bool isNewerThan(int ownBuild) => build > ownBuild;

  /// The release, or null when the answer is not one (never trusted as-is:
  /// the file name and hash are checked before they are used).
  static Release? fromJson(Object? json) {
    if (json is! Map) return null;
    final version = json['version'];
    final build = json['build'];
    final file = json['file'];
    final sha = json['sha256'];
    final notes = json['notes'];
    if (version is! String || !_version.hasMatch(version)) return null;
    if (build is! int || build < 1) return null;
    if (file is! String || !_apkName.hasMatch(file)) return null;
    if (sha is! String || !_sha256.hasMatch(sha)) return null;
    return Release(
      version: version,
      build: build,
      file: file,
      sha256: sha,
      notes: notes is String ? notes : '',
    );
  }
}
