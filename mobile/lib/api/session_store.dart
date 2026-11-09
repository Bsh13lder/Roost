import 'package:flutter_secure_storage/flutter_secure_storage.dart';

const defaultGatewayUrl = 'http://127.0.0.1:18800';
const sessionCookieName = 'roost_session';

/// Where the gateway URL, the session cookie value and the phone's own
/// preferences (the accent colour) are kept, the offline tasks (the kept
/// open list and the changes waiting to sync, as one JSON text) and the
/// account's time zone (its IANA name, so screens with no connection still
/// show the right clock). The password is never stored.
abstract class SessionStore {
  Future<String?> readBaseUrl();
  Future<String?> readToken();
  Future<void> writeBaseUrl(String url);
  Future<void> writeToken(String? token);
  Future<String?> readAccent();
  Future<void> writeAccent(String id);
  Future<String?> readOfflineTasks();

  /// Null removes it (Sign out).
  Future<void> writeOfflineTasks(String? json);

  Future<String?> readTimezone();
  Future<void> writeTimezone(String zone);
}

class SecureSessionStore implements SessionStore {
  SecureSessionStore([FlutterSecureStorage? storage])
      : _storage = storage ?? const FlutterSecureStorage();

  final FlutterSecureStorage _storage;

  static const _urlKey = 'gateway_url';
  static const _tokenKey = 'session_token';
  static const _accentKey = 'accent';
  static const _offlineTasksKey = 'offline_tasks';
  static const _timezoneKey = 'timezone';

  @override
  Future<String?> readBaseUrl() => _storage.read(key: _urlKey);

  @override
  Future<String?> readToken() => _storage.read(key: _tokenKey);

  @override
  Future<void> writeBaseUrl(String url) =>
      _storage.write(key: _urlKey, value: url);

  @override
  Future<void> writeToken(String? token) => token == null
      ? _storage.delete(key: _tokenKey)
      : _storage.write(key: _tokenKey, value: token);

  @override
  Future<String?> readAccent() => _storage.read(key: _accentKey);

  @override
  Future<void> writeAccent(String id) =>
      _storage.write(key: _accentKey, value: id);

  @override
  Future<String?> readOfflineTasks() => _storage.read(key: _offlineTasksKey);

  @override
  Future<void> writeOfflineTasks(String? json) => json == null
      ? _storage.delete(key: _offlineTasksKey)
      : _storage.write(key: _offlineTasksKey, value: json);

  @override
  Future<String?> readTimezone() => _storage.read(key: _timezoneKey);

  @override
  Future<void> writeTimezone(String zone) =>
      _storage.write(key: _timezoneKey, value: zone);
}

class MemorySessionStore implements SessionStore {
  String? url;
  String? token;
  String? accent;
  String? offlineTasks;
  String? timezone;

  @override
  Future<String?> readBaseUrl() async => url;
  @override
  Future<String?> readToken() async => token;
  @override
  Future<void> writeBaseUrl(String value) async => url = value;
  @override
  Future<void> writeToken(String? value) async => token = value;
  @override
  Future<String?> readAccent() async => accent;
  @override
  Future<void> writeAccent(String id) async => accent = id;
  @override
  Future<String?> readOfflineTasks() async => offlineTasks;
  @override
  Future<void> writeOfflineTasks(String? json) async => offlineTasks = json;
  @override
  Future<String?> readTimezone() async => timezone;
  @override
  Future<void> writeTimezone(String zone) async => timezone = zone;
}
