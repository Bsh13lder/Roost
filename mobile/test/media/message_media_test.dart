import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/api/models.dart';
import 'package:roost_mobile/api/providers.dart';
import 'package:roost_mobile/api/session_store.dart';
import 'package:roost_mobile/features/chat/message_view.dart';
import 'package:roost_mobile/media/media_ref.dart';


// A 1x1 transparent PNG.
final _png = Uint8List.fromList(const [
  0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52, 0x00, 0x00, 0x00,
  0x01, 0x00, 0x00, 0x00, 0x01, 0x08, 0x06, 0x00, 0x00, 0x00, 0x1F, 0x15, 0xC4, 0x89, 0x00, 0x00, 0x00, 0x0A, 0x49,
  0x44, 0x41, 0x54, 0x78, 0x9C, 0x63, 0x00, 0x01, 0x00, 0x00, 0x05, 0x00, 0x01, 0x0D, 0x0A, 0x2D, 0xB4, 0x00, 0x00,
  0x00, 0x00, 0x49, 0x45, 0x4E, 0x44, 0xAE, 0x42, 0x60, 0x82,
]);

Map<String, Object?> _json(List<Map<String, Object?>> media, {String role = 'user'}) => {
      'id': 'm1',
      'thread_id': 't1',
      'role': role,
      'body': 'Look at this',
      'seq': 4,
      'created_at': '2026-11-05T12:00:00+00:00',
      'kind': 'text',
      'media': media,
    };

Map<String, Object?> _ref(String id, {String? group, String source = 'you'}) =>
    {'id': id, 'width': 640, 'height': 480, 'source': source, 'group': group};

Future<_BytesAdapter> _pump(WidgetTester tester, Message m) async {
  final bytesAdapter = _BytesAdapter(_png);
  final container = ProviderContainer(overrides: [
    sessionStoreProvider.overrideWithValue(MemorySessionStore()),
    httpAdapterProvider.overrideWithValue(bytesAdapter),
  ]);
  addTearDown(container.dispose);
  await tester.pumpWidget(UncontrolledProviderScope(
    container: container,
    child: MaterialApp(
        home: Scaffold(body: SingleChildScrollView(child: MessageView(message: m, text: m.body)))),
  ));
  await tester.pumpAndSettle();
  return bytesAdapter;
}

void main() {
  test('a message reads its pictures', () {
    final m = Message.fromJson(_json([_ref('a'), _ref('v1', group: 'video')]));
    expect(m.media.map((r) => (r.id, r.video, r.fromBot)), [('a', false, false), ('v1', true, false)]);
    expect(Message.fromJson({'id': 'x'}).media, isEmpty);
  });

  test('pictures fold into photos and one video strip', () {
    final groups = mediaGroups([_r('a'), _r('v1', true), _r('v2', true), _r('b')]);
    expect(groups.map((g) => '${g.video}:${g.items.map((r) => r.id).join(',')}'),
        ['false:a', 'true:v1,v2', 'false:b']);
  });

  testWidgets('your message shows its pictures as thumbnails', (tester) async {
    await _pump(tester, Message.fromJson(_json([_ref('a'), _ref('b')])));
    expect(find.byKey(const Key('media-a')), findsOneWidget);
    expect(find.byKey(const Key('media-b')), findsOneWidget);
    expect(find.text('Look at this'), findsOneWidget);
  });

  testWidgets('a video shows as one strip with its frame count', (tester) async {
    final frames = [for (var i = 0; i < 8; i++) _ref('v$i', group: 'video')];
    await _pump(tester, Message.fromJson(_json(frames)));
    expect(find.text('Video · 8 frames'), findsOneWidget);
  });

  testWidgets('a bot picture shows in the bot reply and opens the viewer', (tester) async {
    await _pump(tester, Message.fromJson(_json([_ref('s1', source: 'bot')], role: 'bot')));
    expect(find.byKey(const Key('media-s1')), findsOneWidget);
    await tester.tap(find.byKey(const Key('media-s1')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('media-viewer')), findsOneWidget);
  });
}

MediaRef _r(String id, [bool video = false]) =>
    MediaRef(id: id, width: 1, height: 1, fromBot: false, video: video);

/// Answers every request with the same picture bytes.
class _BytesAdapter implements HttpClientAdapter {
  _BytesAdapter(this.bytes);
  final Uint8List bytes;
  final List<RequestOptions> requests = [];

  @override
  Future<ResponseBody> fetch(RequestOptions options, Stream<List<int>>? requestStream,
      Future<void>? cancelFuture) async {
    requests.add(options);
    return ResponseBody.fromBytes(bytes, 200, headers: {
      Headers.contentTypeHeader: ['image/png'],
    });
  }

  @override
  void close({bool force = false}) {}
}
