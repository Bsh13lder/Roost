import 'dart:convert';

import 'package:dio/dio.dart';

typedef FakeReply = ({int status, Object? body, Map<String, List<String>> headers});
typedef FakeHandler = FakeReply Function(RequestOptions options);

/// A dio adapter that answers from a function; no network is touched.
class FakeAdapter implements HttpClientAdapter {
  FakeAdapter(this.handler);

  final FakeHandler handler;
  final List<RequestOptions> requests = [];

  static FakeReply json(
    Object? body, {
    int status = 200,
    Map<String, List<String>> headers = const {},
  }) =>
      (status: status, body: body, headers: headers);

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<List<int>>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    requests.add(options);
    final r = handler(options);
    return ResponseBody.fromString(
      jsonEncode(r.body),
      r.status,
      headers: {
        Headers.contentTypeHeader: ['application/json'],
        ...r.headers,
      },
    );
  }

  @override
  void close({bool force = false}) {}
}

/// Like [FakeAdapter], but while [down] is true every request fails the
/// way a Mac that is asleep or off fails: the connection is refused.
class SwitchAdapter extends FakeAdapter {
  SwitchAdapter(super.handler, {this.down = false});

  bool down;

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<List<int>>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    if (down) {
      requests.add(options);
      throw DioException.connectionError(
          requestOptions: options, reason: 'Connection refused');
    }
    return super.fetch(options, requestStream, cancelFuture);
  }
}
