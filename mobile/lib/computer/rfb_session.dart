import 'dart:async';
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import 'rfb_codec.dart';
import 'rfb_framebuffer.dart';
import 'zrle.dart' show encodingZrle;

/// Close codes of `WS /api/bots/{id}/live` (`LIVE_CLOSE_*` in roost/constants.py).
const closeGivenBack = 4000;
const closeNotHeld = 4409;
const closeAsleep = 4410;

/// ZRLE shrinks a full-screen change about 13 times (a real Xvnc's screen,
/// 2026-10-29: 301 KB, not 4 MB; decoded to the same pixels as Raw).
const zrleEnabled = true;

enum SessionState { connecting, live, closed }

/// One RFB conversation over the live socket. It does the handshake the
/// gateway's filter expects, keeps the framebuffer current, and sends pointer
/// and key events only while [controlling]. It never logs or keeps typing.
class RfbSession extends ChangeNotifier {
  RfbSession(this._channel, {required this.controlling}) {
    _sub = _channel.stream.listen(_onData,
        onDone: _onDone, onError: (_) => _end(), cancelOnError: true);
  }

  final WebSocketChannel _channel;
  final bool controlling;
  final RfbParser _parser = RfbParser();
  StreamSubscription<dynamic>? _sub;
  RfbFramebuffer? _fb;
  bool _building = false;
  bool _dirty = false;
  bool _disposed = false;

  SessionState state = SessionState.connecting;
  ui.Image? image;
  ui.Size screenSize = ui.Size.zero;
  int? closeCode;

  bool get canSend => state == SessionState.live && controlling;

  void _send(Uint8List bytes) {
    if (state == SessionState.closed) return;
    _channel.sink.add(bytes);
  }

  void _onData(dynamic data) {
    if (data is! List<int>) return; // a text frame is not RFB
    try {
      for (final event in _parser.add(data)) {
        _handle(event);
      }
    } on RfbProtocolFault {
      _end();
    }
  }

  void _handle(RfbEvent event) {
    switch (event) {
      case RfbServerVersion():
        _send(encodeVersion());
      case RfbSecurityTypes():
        _send(encodeSecurityNone());
      case RfbSecurityResult():
        _send(encodeClientInit());
      case RfbServerInit():
        _fb = RfbFramebuffer(event.width, event.height);
        screenSize = ui.Size(event.width.toDouble(), event.height.toDouble());
        _send(encodeSetPixelFormat());
        _send(encodeSetEncodings([
          if (zrleEnabled) encodingZrle,
          encodingCopyRect,
          encodingRaw,
        ]));
        _request(incremental: false);
        state = SessionState.live;
        notifyListeners();
      case RfbRawRect() || RfbCopyRect():
        _fb?.apply(event);
      case RfbUpdateEnd():
        _request(incremental: true);
        _rebuild();
    }
  }

  void _request({required bool incremental}) {
    final fb = _fb;
    if (fb == null) return;
    _send(encodeUpdateRequest(
        incremental: incremental, x: 0, y: 0, w: fb.width, h: fb.height));
  }

  void _rebuild() {
    if (_building) {
      _dirty = true;
      return;
    }
    final fb = _fb;
    if (fb == null) return;
    _building = true;
    ui.decodeImageFromPixels(fb.rgba, fb.width, fb.height,
        ui.PixelFormat.rgba8888, (next) {
      _building = false;
      if (_disposed) {
        next.dispose();
        return;
      }
      image?.dispose();
      image = next;
      notifyListeners();
      if (_dirty) {
        _dirty = false;
        _rebuild();
      }
    });
  }

  /// A pointer position (remote pixels) with the buttons held.
  void pointer(int buttons, int x, int y) {
    if (!canSend) return;
    _send(encodePointer(buttons, x, y));
  }

  void key(int keysym, {required bool down}) {
    if (!canSend) return;
    _send(encodeKey(keysym, down: down));
  }

  /// A full press of one key.
  void tap(int keysym) {
    key(keysym, down: true);
    key(keysym, down: false);
  }

  void _onDone() {
    closeCode = _channel.closeCode;
    _end();
  }

  void _end() {
    if (state == SessionState.closed) return;
    closeCode ??= _channel.closeCode;
    state = SessionState.closed;
    if (!_disposed) notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    _sub?.cancel();
    _channel.sink.close();
    image?.dispose();
    image = null;
    super.dispose();
  }
}
