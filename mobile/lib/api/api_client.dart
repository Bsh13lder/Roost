import 'dart:io' show HttpClient, SocketException;
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:dio/io.dart';

import 'api_error.dart';
import 'session_store.dart';

/// What the client needs to know about the current sign-in.
class Connection {
  const Connection({required this.baseUrl, this.token});

  final String baseUrl;
  final String? token;
}

/// Shown when no answer came back at all.
const unreachableMessage =
    "Can't reach Roost. Check that it is running and the gateway address is "
    'right. On a phone plugged in by USB, run: '
    'adb reverse tcp:18800 tcp:18800';

typedef ConnectionReader = Connection Function();

/// Kept-alive sockets die quietly when the phone sleeps or its VPN reconnects,
/// so an idle one is let go soon.
const idleSocketTimeout = Duration(seconds: 5);

HttpClientAdapter _networkAdapter() => IOHttpClientAdapter(
    createHttpClient: () => HttpClient()..idleTimeout = idleSocketTimeout);

/// True when no answer came back at all: the connection was refused or timed
/// out, or the host could not be found. A slow reply (receive timeout) or any
/// status the gateway sent is not this.
bool isUnreachable(DioException e) {
  if (e.response != null) return false;
  return switch (e.type) {
    DioExceptionType.connectionError ||
    DioExceptionType.connectionTimeout => true,
    DioExceptionType.unknown => e.error is SocketException,
    _ => false,
  };
}

/// The one HTTP client. Every request carries `Origin: <gateway URL>` (the
/// gateway refuses a mutating request without an allowed Origin) and the
/// session cookie. A 401 on a signed-in request calls [onUnauthorized].
class ApiClient {
  ApiClient({
    required ConnectionReader connection,
    required this.onUnauthorized,
    this.onSession,
    this.onUnreachable,
    this.onAnswered,
    HttpClientAdapter? adapter,
  })  : _connection = connection,
        dio = Dio(BaseOptions(
          connectTimeout: const Duration(seconds: 10),
          receiveTimeout: const Duration(seconds: 30),
        )) {
    _ownsAdapter = adapter == null;
    dio.httpClientAdapter = adapter ?? _networkAdapter();
    dio.interceptors.add(InterceptorsWrapper(
      onRequest: _addHeaders,
      onResponse: _captureSession,
      onError: _noteReach,
    ));
  }

  final Dio dio;
  final ConnectionReader _connection;
  late final bool _ownsAdapter;
  final void Function() onUnauthorized;

  /// Called with the cookie value a response sets.
  final void Function(String token)? onSession;

  /// No answer at all came back (see [isUnreachable]).
  final void Function()? onUnreachable;

  /// The gateway answered, whatever the status.
  final void Function()? onAnswered;

  void _addHeaders(RequestOptions options, RequestInterceptorHandler h) {
    final c = _connection();
    options.baseUrl = c.baseUrl;
    options.headers['Origin'] = c.baseUrl;
    final token = c.token;
    if (token != null) {
      options.headers['Cookie'] = '$sessionCookieName=$token';
    }
    h.next(options);
  }

  void _captureSession(Response<dynamic> r, ResponseInterceptorHandler h) {
    final cookies = r.headers['set-cookie'] ?? const <String>[];
    for (final line in cookies) {
      final match = RegExp('$sessionCookieName=([^;]*)').firstMatch(line);
      if (match != null && match.group(1)!.isNotEmpty) {
        onSession?.call(match.group(1)!);
      }
    }
    onAnswered?.call();
    h.next(r);
  }

  void _noteReach(DioException e, ErrorInterceptorHandler h) {
    if (isUnreachable(e)) {
      _freshSockets();
      onUnreachable?.call();
    } else if (e.response != null) {
      onAnswered?.call();
    }
    h.next(e);
  }

  /// After no answer, the next request starts from new sockets: a pooled one
  /// from before the phone slept would only fail again.
  void _freshSockets() {
    if (!_ownsAdapter) return;
    final old = dio.httpClientAdapter;
    dio.httpClientAdapter = _networkAdapter();
    old.close(force: true);
  }

  Future<dynamic> get(String path) => _send('GET', path);

  /// [receiveTimeout] for a route that works a while before answering.
  Future<dynamic> post(String path, [Object? body, Duration? receiveTimeout]) =>
      _send('POST', path, body, receiveTimeout);

  Future<dynamic> put(String path, [Object? body]) => _send('PUT', path, body);

  Future<dynamic> patch(String path, [Object? body]) =>
      _send('PATCH', path, body);

  Future<dynamic> delete(String path, [Object? body]) =>
      _send('DELETE', path, body);

  Future<dynamic> _send(String method, String path,
      [Object? body, Duration? receiveTimeout]) async {
    try {
      final r = await dio.request<dynamic>(
        path,
        data: body,
        options: Options(method: method, receiveTimeout: receiveTimeout),
      );
      return r.data;
    } on DioException catch (e) {
      throw _map(e, signedIn: true);
    }
  }

  /// A body of raw bytes (a picture), with its own content type.
  Future<dynamic> postBytes(
      String path, Uint8List bytes, String contentType,
      {Duration? receiveTimeout}) async {
    try {
      final r = await dio.request<dynamic>(
        path,
        data: Stream.fromIterable([bytes]),
        options: Options(
          method: 'POST',
          contentType: contentType,
          receiveTimeout: receiveTimeout,
          headers: {Headers.contentLengthHeader: bytes.length},
        ),
      );
      return r.data;
    } on DioException catch (e) {
      throw _map(e, signedIn: true);
    }
  }

  /// The raw bytes of a GET (a spoken part, a voice sample), with the session
  /// cookie, so a player never needs it.
  Future<Uint8List> getBytes(String path, {Duration? receiveTimeout}) async {
    try {
      final r = await dio.request<List<int>>(
        path,
        options: Options(
          method: 'GET',
          responseType: ResponseType.bytes,
          receiveTimeout: receiveTimeout,
        ),
      );
      final data = r.data ?? const <int>[];
      return data is Uint8List ? data : Uint8List.fromList(data);
    } on DioException catch (e) {
      throw _map(e, signedIn: true);
    }
  }

  /// Saves the body of a GET to [savePath] (the session cookie goes along),
  /// reporting (received, total) as it arrives; total is -1 when unknown.
  Future<void> download(String path, String savePath,
      {void Function(int received, int total)? onProgress}) async {
    try {
      await dio.download(path, savePath, onReceiveProgress: onProgress);
    } on DioException catch (e) {
      throw _map(e, signedIn: true);
    }
  }

  /// A 401 here is a wrong password, not an expired session.
  Future<dynamic> login(String username, String password) async {
    try {
      final r = await dio.request<dynamic>(
        '/api/auth/login',
        data: {'username': username, 'password': password},
        options: Options(method: 'POST'),
      );
      return r.data;
    } on DioException catch (e) {
      if (e.response?.statusCode == 401) {
        throw const ApiException('Wrong username or password.', status: 401);
      }
      if (e.response?.statusCode == 429) {
        throw const ApiException(
            'Too many login attempts. Wait a few minutes and try again.',
            status: 429);
      }
      throw _map(e, signedIn: false);
    }
  }

  ApiException _map(DioException e, {required bool signedIn}) {
    final status = e.response?.statusCode;
    if (status == 401) {
      if (signedIn) onUnauthorized();
      return const ApiException('Please sign in again.', status: 401);
    }
    if (status == 403) {
      return ApiException(
          'The gateway refused this app (${_connection().baseUrl}).',
          status: 403);
    }
    if (status == 404) {
      return const ApiException("That wasn't found.", status: 404);
    }
    if (status == 429) {
      return const ApiException('Too many tries. Wait a moment.', status: 429);
    }
    if (status != null && status >= 500) {
      return ApiException('Roost had a problem. Try again.', status: status);
    }
    final detail = _detail(e.response?.data);
    if (status == 409) {
      return ApiException(detail ?? 'This changed somewhere else.',
          status: 409, body: e.response?.data);
    }
    if (detail != null) return ApiException(detail, status: status);
    if (status != null) {
      return ApiException('Roost refused that (error $status).',
          status: status);
    }
    return const ApiException(unreachableMessage);
  }

  String? _detail(Object? data) {
    if (data is Map && data['detail'] is String) {
      return data['detail'] as String;
    }
    return null;
  }
}
