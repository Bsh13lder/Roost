import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/api/providers.dart';
import 'package:roost_mobile/api/session_store.dart';
import 'package:roost_mobile/features/chat/chat_screen.dart';
import 'package:roost_mobile/media/attachments.dart';
import 'package:roost_mobile/media/media_source.dart';

import '../fake_adapter.dart';

Uint8List _jpeg(int n) => Uint8List.fromList([0xFF, 0xD8, 0xFF, n]);

class _FakeSource implements MediaSource {
  @override
  Future<List<Uint8List>> photos(int limit) async => [_jpeg(1), _jpeg(2)].take(limit).toList();

  @override
  Future<Uint8List?> camera() async => _jpeg(9);

  @override
  Future<List<Uint8List>> videoFrames() async => [for (var i = 0; i < 8; i++) _jpeg(20 + i)];
}

FakeAdapter _server(List<String> log, {int failUploads = 0}) {
  var uploads = 0;
  return FakeAdapter((o) {
    if (o.path == '/api/bots/b1/chat') return FakeAdapter.json({'id': 't1', 'bot_id': 'b1'});
    if (o.path == '/api/bots/b1') return FakeAdapter.json({'id': 'b1', 'name': 'Gela', 'computer': 'linux'});
    if (o.path == '/api/threads/t1/messages' && o.method == 'GET') return FakeAdapter.json(<Object>[]);
    if (o.path == '/api/threads/t1/media') {
      uploads += 1;
      final form = o.data as FormData;
      final video = form.fields.any((f) => f.key == 'video' && f.value == '1');
      log.add('upload${video ? ' video' : ''}');
      if (uploads <= failUploads) {
        return FakeAdapter.json({'detail': 'That picture is too big.'}, status: 413);
      }
      return FakeAdapter.json({'id': 'p$uploads', 'width': 10, 'height': 10});
    }
    if (o.path == '/api/threads/t1/messages' && o.method == 'POST') {
      log.add('send ${o.data}');
      return FakeAdapter.json({'message_id': 'm9', 'status': 'started'});
    }
    return FakeAdapter.json({});
  });
}

Future<ProviderContainer> _open(WidgetTester tester, FakeAdapter adapter) async {
  final container = ProviderContainer(overrides: [
    sessionStoreProvider.overrideWithValue(MemorySessionStore()),
    httpAdapterProvider.overrideWithValue(adapter),
    mediaSourceProvider.overrideWithValue(_FakeSource()),
  ]);
  addTearDown(container.dispose);
  await tester.pumpWidget(UncontrolledProviderScope(
    container: container,
    child: const MaterialApp(home: ChatScreen(botId: 'b1')),
  ));
  await tester.pumpAndSettle();
  return container;
}

Future<void> _attach(WidgetTester tester, String what) async {
  await tester.tap(find.byKey(const Key('composer-plus')));
  await tester.pumpAndSettle();
  await tester.tap(find.text(what));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('photos wait above the composer, one can be removed, and Send uploads then sends', (tester) async {
    final log = <String>[];
    await _open(tester, _server(log));
    await _attach(tester, 'Photo');
    expect(find.byKey(const Key('tray-item')), findsNWidgets(2));
    await tester.tap(find.byKey(const Key('tray-remove')).first);
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('tray-item')), findsOneWidget);

    await tester.enterText(find.byKey(const Key('composer')), 'What is this?');
    await tester.pump();
    await tester.tap(find.byKey(const Key('send')));
    await tester.pumpAndSettle();
    expect(log, [
      'upload',
      'send {text: What is this?, media_ids: [p1]}',
    ]);
    expect(find.byKey(const Key('tray-item')), findsNothing);
  });

  testWidgets('pictures alone can be sent with no words', (tester) async {
    final log = <String>[];
    await _open(tester, _server(log));
    await _attach(tester, 'Camera');
    await tester.tap(find.byKey(const Key('send')));
    await tester.pumpAndSettle();
    expect(log, ['upload', 'send {text: , media_ids: [p1]}']);
  });

  testWidgets('a video sends its 8 frames in order, marked as video', (tester) async {
    final log = <String>[];
    await _open(tester, _server(log));
    await _attach(tester, 'Video');
    expect(find.text('Video · 8 frames'), findsOneWidget);
    await tester.tap(find.byKey(const Key('send')));
    await tester.pumpAndSettle();
    expect(log.where((l) => l == 'upload video'), hasLength(8));
    expect(log.last, 'send {text: , media_ids: [p1, p2, p3, p4, p5, p6, p7, p8]}');
  });

  testWidgets('a failed upload keeps the pictures and words and says why', (tester) async {
    final log = <String>[];
    await _open(tester, _server(log, failUploads: 1));
    await _attach(tester, 'Camera');
    await tester.enterText(find.byKey(const Key('composer')), 'Read it');
    await tester.pump();
    await tester.tap(find.byKey(const Key('send')));
    await tester.pumpAndSettle();
    expect(find.text('That picture is too big.'), findsOneWidget);
    expect(find.byKey(const Key('tray-item')), findsOneWidget);
    expect(find.text('Read it'), findsOneWidget);
    expect(log.where((l) => l.startsWith('send')), isEmpty);

    await tester.tap(find.byKey(const Key('send')));   // retry
    await tester.pumpAndSettle();
    expect(log.last, 'send {text: Read it, media_ids: [p2]}');
  });

  test('a video takes every slot, so photos and a video are not mixed past 8', () {
    final tray = TrayState.empty().withPhotos([_jpeg(1)]);
    expect(tray.room, mediaMax - 1);
    expect(tray.withVideo([for (var i = 0; i < 8; i++) _jpeg(i)]).error, isNotNull);
  });
}
