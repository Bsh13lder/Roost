import 'dart:io';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/api/api_client.dart';
import 'package:roost_mobile/api/api_error.dart';
import 'package:roost_mobile/live/live_connection.dart';

import 'fake_adapter.dart';

ApiClient clientFor(
  FakeAdapter adapter, {
  String? token,
  void Function()? onUnauthorized,
  void Function(String)? onSession,
}) =>
    ApiClient(
      connection: () =>
          Connection(baseUrl: 'http://127.0.0.1:18800', token: token),
      onUnauthorized: onUnauthorized ?? () {},
      onSession: onSession,
      adapter: adapter,
    );

void main() {
  test('sends Origin and the session cookie on every request', () async {
    final adapter = FakeAdapter((_) => FakeAdapter.json([]));
    await clientFor(adapter, token: 'abc').get('/api/bots');
    final h = adapter.requests.single.headers;
    expect(h['Origin'], 'http://127.0.0.1:18800');
    expect(h['Cookie'], 'roost_session=abc');
    expect(adapter.requests.single.uri.toString(),
        'http://127.0.0.1:18800/api/bots');
  });

  test('login captures the session cookie from Set-Cookie', () async {
    String? got;
    final adapter = FakeAdapter((_) => FakeAdapter.json(
          {'id': '1', 'username': 'me'},
          headers: {
            'set-cookie': ['roost_session=tok123; HttpOnly; Path=/'],
          },
        ));
    await clientFor(adapter, onSession: (t) => got = t).login('me', 'pw');
    expect(got, 'tok123');
  });

  test('401 on a signed-in request calls onUnauthorized', () async {
    var expired = false;
    final adapter =
        FakeAdapter((_) => FakeAdapter.json({'detail': 'x'}, status: 401));
    final client =
        clientFor(adapter, token: 't', onUnauthorized: () => expired = true);
    await expectLater(client.get('/api/bots'),
        throwsA(isA<ApiException>().having((e) => e.status, 'status', 401)));
    expect(expired, isTrue);
  });

  test('401 on login is a wrong password, not an expired session', () async {
    var expired = false;
    final adapter =
        FakeAdapter((_) => FakeAdapter.json({'detail': 'x'}, status: 401));
    final client = clientFor(adapter, onUnauthorized: () => expired = true);
    await expectLater(
        client.login('me', 'bad'),
        throwsA(isA<ApiException>().having(
            (e) => e.message, 'message', 'Wrong username or password.')));
    expect(expired, isFalse);
  });

  test('server errors become friendly messages', () async {
    final adapter = FakeAdapter((_) => FakeAdapter.json({}, status: 500));
    await expectLater(
        clientFor(adapter).get('/x'),
        throwsA(isA<ApiException>()
            .having((e) => e.message, 'message', contains('Try again'))));
  });

  test('429 on login says too many login attempts', () async {
    final adapter =
        FakeAdapter((_) => FakeAdapter.json({'detail': 'x'}, status: 429));
    await expectLater(
        clientFor(adapter).login('me', 'pw'),
        throwsA(isA<ApiException>()
            .having((e) => e.message, 'message', contains('Too many login'))));
  });

  test('a refused connection reports the gateway unreachable', () async {
    var unreachable = 0;
    var answered = 0;
    final adapter = SwitchAdapter((_) => FakeAdapter.json([]), down: true);
    final client = ApiClient(
      connection: () => const Connection(baseUrl: 'http://127.0.0.1:18800'),
      onUnauthorized: () {},
      onUnreachable: () => unreachable++,
      onAnswered: () => answered++,
      adapter: adapter,
    );
    await expectLater(client.get('/api/bots'), throwsA(isA<ApiException>()));
    expect((unreachable, answered), (1, 0));

    adapter.down = false;
    await client.get('/api/bots');
    expect((unreachable, answered), (1, 1));
  });

  test('an error the gateway sent back (401, 404, 500) is an answer', () async {
    for (final status in [401, 404, 500]) {
      var unreachable = 0;
      var answered = 0;
      final client = ApiClient(
        connection: () => const Connection(baseUrl: 'http://127.0.0.1:18800'),
        onUnauthorized: () {},
        onUnreachable: () => unreachable++,
        onAnswered: () => answered++,
        adapter: FakeAdapter((_) => FakeAdapter.json({}, status: status)),
      );
      await expectLater(client.get('/x'), throwsA(isA<ApiException>()));
      expect((unreachable, answered), (0, 1), reason: '$status');
    }
  });

  test('isUnreachable: refused, timed out or no such host, never a reply', () {
    final o = RequestOptions(path: '/x');
    expect(isUnreachable(DioException.connectionError(
        requestOptions: o, reason: 'refused')), isTrue);
    expect(isUnreachable(DioException.connectionTimeout(
        requestOptions: o, timeout: const Duration(seconds: 1))), isTrue);
    expect(isUnreachable(DioException(
        requestOptions: o, error: const SocketException('no host'))), isTrue);
    expect(isUnreachable(DioException.badResponse(
        statusCode: 404,
        requestOptions: o,
        response: Response(requestOptions: o, statusCode: 404))), isFalse);
    expect(isUnreachable(DioException.receiveTimeout(
        requestOptions: o, timeout: const Duration(seconds: 1))), isFalse);
  });

  test('the events socket waits longer after each miss, up to 30 s', () {
    expect(reconnectDelay(0), const Duration(seconds: 1));
    expect(reconnectDelay(3), const Duration(seconds: 8));
    expect(reconnectDelay(40), const Duration(seconds: 30));
  });
}
