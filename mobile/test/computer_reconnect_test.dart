import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/api/providers.dart';
import 'package:roost_mobile/api/session_store.dart';
import 'package:roost_mobile/computer/computer_screen.dart';
import 'package:roost_mobile/computer/live_screen.dart';
import 'package:roost_mobile/computer/remote_view.dart';
import 'package:roost_mobile/live/live_connection.dart';

import 'fake_adapter.dart';
import 'fake_socket.dart';

// Owner, 2026-10-29: "when I watch the computer screen from the phone it drops
// and an all-black screen appears". A dropped screen socket now comes back by
// itself, and the last picture stays up while it does.

/// One FramebufferUpdate with a single 8x4 Raw rectangle.
Uint8List _fullFrame() {
  final b = ByteData(4 + 12 + 8 * 4 * 4)
    ..setUint8(0, 0)
    ..setUint16(2, 1)
    ..setUint16(8, 8)
    ..setUint16(10, 4)
    ..setInt32(12, 0);
  return b.buffer.asUint8List();
}

Future<List<FakeSocket>> _open(WidgetTester tester) async {
  final sockets = <FakeSocket>[];
  final container = ProviderContainer(overrides: [
    sessionStoreProvider.overrideWithValue(MemorySessionStore()),
    httpAdapterProvider.overrideWithValue(FakeAdapter((o) {
      if (o.path == '/api/bots/b1/control') return FakeAdapter.json({'held': false});
      if (o.path == '/api/bots/b1/teach') return FakeAdapter.json({'teaching': false});
      if (o.path == '/api/stuck') return FakeAdapter.json([]);
      return FakeAdapter.json({});
    })),
    socketOpenerProvider.overrideWithValue((uri, headers) {
      final socket = FakeSocket();
      sockets.add(socket);
      return socket;
    }),
  ]);
  addTearDown(container.dispose);
  await tester.pumpWidget(UncontrolledProviderScope(
    container: container,
    child: const MaterialApp(home: ComputerScreen(botId: 'b1')),
  ));
  for (var i = 0; i < 5; i++) {
    await tester.pump(const Duration(milliseconds: 50));
  }
  return sockets;
}

Future<void> _goLive(WidgetTester tester, FakeSocket socket) async {
  socket
    ..handshake()
    ..incoming.add(_fullFrame());
  for (var i = 0; i < 5; i++) {
    await tester.pump(const Duration(milliseconds: 50));
  }
}

Future<void> _drop(WidgetTester tester, FakeSocket socket, int code) async {
  socket.closeCode = code;
  await socket.incoming.close();
  await tester.pump();
  await tester.pump();
}

void main() {
  testWidgets('a dropped screen reconnects and keeps the last picture up',
      (tester) async {
    final sockets = await _open(tester);
    await _goLive(tester, sockets.single);
    expect(find.byType(RemoteView), findsOneWidget);

    await _drop(tester, sockets.single, 4503);
    expect(find.byType(RemoteView), findsOneWidget); // not a black page
    expect(find.text('Reconnecting…'), findsOneWidget);
    expect(find.text('Retry'), findsNothing);

    await tester.pump(liveScreenRetries.first);
    expect(sockets, hasLength(2));
    await _goLive(tester, sockets.last);
    expect(find.byType(RemoteView), findsOneWidget);
    expect(find.text('Reconnecting…'), findsNothing);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('after the retries run out it says why, with Retry',
      (tester) async {
    final sockets = await _open(tester);
    await _goLive(tester, sockets.single);
    await _drop(tester, sockets.last, 4503);
    for (final wait in liveScreenRetries) {
      await tester.pump(wait);
      await _drop(tester, sockets.last, 4503);
    }
    expect(sockets, hasLength(1 + liveScreenRetries.length));
    expect(find.text('Retry'), findsOneWidget);
    expect(find.textContaining('4503'), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('a sleeping computer is not retried', (tester) async {
    final sockets = await _open(tester);
    await _goLive(tester, sockets.single);
    await _drop(tester, sockets.single, closeAsleepCode);
    await tester.pump(liveScreenRetries.first);
    expect(sockets, hasLength(1));
    expect(find.text('Open it'), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
  });
}

const closeAsleepCode = 4410;
