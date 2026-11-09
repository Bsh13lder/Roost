// ignore_for_file: depend_on_referenced_packages
import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:stream_channel/stream_channel.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

/// A socket with no network: what the app sends lands in [sent], and
/// [closed] says whether the app closed it.
class FakeSocket extends StreamChannelMixin<dynamic>
    implements WebSocketChannel {
  final incoming = StreamController<dynamic>();
  final sent = <Uint8List>[];
  final sentText = <String>[];
  bool closed = false;
  late final WebSocketSink _sink = _FakeSink(this);
  @override
  Stream<dynamic> get stream => incoming.stream;
  @override
  WebSocketSink get sink => _sink;
  @override
  int? closeCode;
  @override
  String? closeReason;
  @override
  String? get protocol => null;
  @override
  Future<void> get ready => Future.value();

  /// Plays the server's side of the handshake up to ServerInit (8x4 screen).
  void handshake() {
    incoming
      ..add(Uint8List.fromList(ascii.encode('RFB 003.008\n')))
      ..add(Uint8List.fromList([1, 1]))
      ..add(Uint8List.fromList([0, 0, 0, 0]))
      ..add(fakeServerInit());
  }
}

/// ServerInit for an 8x4 screen with a one-letter name.
Uint8List fakeServerInit() {
  final b = ByteData(24 + 1)
    ..setUint16(0, 8)
    ..setUint16(2, 4)
    ..setUint32(20, 1);
  return b.buffer.asUint8List()..[24] = 120;
}

class _FakeSink implements WebSocketSink {
  _FakeSink(this.owner);
  final FakeSocket owner;
  @override
  void add(dynamic data) =>
      data is String ? owner.sentText.add(data) : owner.sent.add(data as Uint8List);
  @override
  void addError(Object error, [StackTrace? stackTrace]) {}
  @override
  Future<void> addStream(Stream<dynamic> stream) async {}
  @override
  Future<void> close([int? closeCode, String? closeReason]) async {
    owner.closed = true;
  }

  @override
  Future<void> get done => Future.value();
}
