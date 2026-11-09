// ignore_for_file: depend_on_referenced_packages
import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/computer/rfb_codec.dart';
import 'package:roost_mobile/computer/rfb_session.dart';
import 'package:roost_mobile/computer/zrle.dart';

import 'fake_socket.dart';

Uint8List serverInit() {
  final b = ByteData(24 + 1)
    ..setUint16(0, 8)
    ..setUint16(2, 4)
    ..setUint32(20, 1);
  return b.buffer.asUint8List()..[24] = 120;
}

Future<void> settle() => Future<void>.delayed(Duration.zero);

void main() {
  test('the handshake is answered in the order the gateway expects', () async {
    final socket = FakeSocket();
    final session = RfbSession(socket, controlling: false);
    socket.incoming.add(Uint8List.fromList(ascii.encode('RFB 003.008\n')));
    await settle();
    expect(utf8.decode(socket.sent[0]), 'RFB 003.008\n');
    socket.incoming.add(Uint8List.fromList([1, 1]));
    await settle();
    expect(socket.sent[1], [1]);
    socket.incoming.add(Uint8List.fromList([0, 0, 0, 0]));
    await settle();
    expect(socket.sent[2], [1]); // ClientInit
    socket.incoming.add(serverInit());
    await settle();
    expect(session.state, SessionState.live);
    expect(session.screenSize.width, 8);
    expect(socket.sent[3][0], 0); // SetPixelFormat
    expect(socket.sent[4][0], 2); // SetEncodings
    // ZRLE first (tried on a real Xvnc, 2026-10-29: a full screen 301 KB, not 4 MB), then CopyRect, Raw.
    expect(socket.sent[4], encodeSetEncodings([encodingZrle, encodingCopyRect, encodingRaw]));
    expect(socket.sent[5][0], 3); // FramebufferUpdateRequest
    session.dispose();
  });

  test('watching never sends input; controlling does', () async {
    for (final controlling in [false, true]) {
      final socket = FakeSocket();
      final session = RfbSession(socket, controlling: controlling);
      socket.incoming.add(Uint8List.fromList([
        ...ascii.encode('RFB 003.008\n'), 1, 1, 0, 0, 0, 0, ...serverInit(),
      ]));
      await settle();
      final before = socket.sent.length;
      session.pointer(buttonLeft, 1, 1);
      session.tap(0x61);
      expect(socket.sent.length - before, controlling ? 3 : 0);
      session.dispose();
    }
  });

  test('the close code is kept for the screen to read', () async {
    final socket = FakeSocket()..closeCode = closeGivenBack;
    final session = RfbSession(socket, controlling: true);
    await socket.incoming.close();
    await settle();
    expect(session.state, SessionState.closed);
    expect(session.closeCode, closeGivenBack);
    session.dispose();
  });
}
