import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../util/app_time.dart';
import 'api_client.dart';
import 'api_error.dart';
import 'reachability.dart';
import 'session_store.dart';

/// Overridden in tests with a [MemorySessionStore].
final sessionStoreProvider =
    Provider<SessionStore>((ref) => SecureSessionStore());

/// Overridden in tests with a fake adapter; null uses the real network.
final httpAdapterProvider = Provider<HttpClientAdapter?>((ref) => null);

class AuthState {
  const AuthState({
    this.ready = false,
    this.baseUrl = defaultGatewayUrl,
    this.token,
  });

  final bool ready;
  final String baseUrl;
  final String? token;

  bool get signedIn => token != null;

  AuthState copyWith({bool? ready, String? baseUrl, String? token}) =>
      AuthState(
        ready: ready ?? this.ready,
        baseUrl: baseUrl ?? this.baseUrl,
        token: token ?? this.token,
      );
}

class AuthController extends Notifier<AuthState> {
  @override
  AuthState build() {
    _load();
    return const AuthState();
  }

  Future<void> _load() async {
    final store = ref.read(sessionStoreProvider);
    final url = await store.readBaseUrl();
    final token = await store.readToken();
    // The kept zone shows the right clock before Roost answers, or offline.
    setAppZone(await store.readTimezone());
    state = AuthState(
      ready: true,
      baseUrl: url ?? defaultGatewayUrl,
      token: token,
    );
  }

  /// The password goes to the gateway and nowhere else.
  Future<void> signIn(String baseUrl, String username, String password) async {
    final url = normaliseUrl(baseUrl);
    state = AuthState(ready: true, baseUrl: url);
    await ref.read(apiClientProvider).login(username, password);
    if (state.token == null) {
      throw const ApiException('Roost did not start a session. Try again.');
    }
    final store = ref.read(sessionStoreProvider);
    await store.writeBaseUrl(url);
    await store.writeToken(state.token);
  }

  void setToken(String token) => state = state.copyWith(token: token);

  Future<void> signOut() async {
    try {
      await ref.read(apiClientProvider).post('/api/auth/logout');
    } on ApiException {
      // Signing out locally matters more than telling the gateway.
    }
    // The offline tasks belong to this sign-in (O2).
    await ref.read(sessionStoreProvider).writeOfflineTasks(null);
    await expire();
  }

  /// A new gateway address (already checked): sign out of the old one and
  /// keep the new one, so the sign-in screen opens with it filled in.
  Future<void> changeGateway(String url) async {
    await signOut();
    await ref.read(sessionStoreProvider).writeBaseUrl(url);
    state = AuthState(ready: true, baseUrl: url);
  }

  /// The session is gone (401 or Sign out): back to the sign-in screen.
  Future<void> expire() async {
    await ref.read(sessionStoreProvider).writeToken(null);
    state = AuthState(ready: true, baseUrl: state.baseUrl);
  }
}

String normaliseUrl(String raw) {
  var url = raw.trim();
  if (url.isEmpty) return defaultGatewayUrl;
  if (!url.contains('://')) url = 'http://$url';
  while (url.endsWith('/')) {
    url = url.substring(0, url.length - 1);
  }
  return url;
}

final authProvider =
    NotifierProvider<AuthController, AuthState>(AuthController.new);

final apiClientProvider = Provider<ApiClient>((ref) {
  return ApiClient(
    connection: () {
      final s = ref.read(authProvider);
      return Connection(baseUrl: s.baseUrl, token: s.token);
    },
    onUnauthorized: () => ref.read(authProvider.notifier).expire(),
    onSession: (token) => ref.read(authProvider.notifier).setToken(token),
    onUnreachable: () => ref.read(offlineProvider.notifier).markUnreachable(),
    onAnswered: () => ref.read(offlineProvider.notifier).markAnswered(),
    adapter: ref.watch(httpAdapterProvider),
  );
});
