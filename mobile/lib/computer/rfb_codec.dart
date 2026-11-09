import 'dart:convert';
import 'dart:typed_data';

import 'zrle.dart';

/// RFB 3.8 messages the app sends (what `roost/desk/rfb.py` lets through)
/// and a parser for what the computer's Xvnc sends back. Pure bytes: no
/// network, no Flutter. Nothing here keeps or prints what was typed.
const rfbClientVersion = 'RFB 003.008\n';
const encodingRaw = 0;
const encodingCopyRect = 1;

const buttonLeft = 1;
const buttonMiddle = 2;
const buttonRight = 4;
const buttonWheelUp = 8;
const buttonWheelDown = 16;

Uint8List encodeVersion() => Uint8List.fromList(ascii.encode(rfbClientVersion));

/// Security type None, then ClientInit with the shared flag.
Uint8List encodeSecurityNone() => Uint8List.fromList([1]);
Uint8List encodeClientInit() => Uint8List.fromList([1]);

/// 32 bits per pixel, depth 24, little endian, true colour, R<<16 G<<8 B:
/// the stream then carries B, G, R, pad for each pixel.
Uint8List encodeSetPixelFormat() {
  final b = ByteData(20);
  b.setUint8(0, 0);
  b.setUint8(4, 32);
  b.setUint8(5, 24);
  b.setUint8(6, 0);
  b.setUint8(7, 1);
  b.setUint16(8, 255);
  b.setUint16(10, 255);
  b.setUint16(12, 255);
  b.setUint8(14, 16);
  b.setUint8(15, 8);
  b.setUint8(16, 0);
  return b.buffer.asUint8List();
}

Uint8List encodeSetEncodings(List<int> encodings) {
  final b = ByteData(4 + 4 * encodings.length);
  b.setUint8(0, 2);
  b.setUint16(2, encodings.length);
  for (var i = 0; i < encodings.length; i++) {
    b.setInt32(4 + 4 * i, encodings[i]);
  }
  return b.buffer.asUint8List();
}

Uint8List encodeUpdateRequest(
    {required bool incremental,
    required int x,
    required int y,
    required int w,
    required int h}) {
  final b = ByteData(10);
  b.setUint8(0, 3);
  b.setUint8(1, incremental ? 1 : 0);
  b.setUint16(2, x);
  b.setUint16(4, y);
  b.setUint16(6, w);
  b.setUint16(8, h);
  return b.buffer.asUint8List();
}

Uint8List encodeKey(int keysym, {required bool down}) {
  final b = ByteData(8);
  b.setUint8(0, 4);
  b.setUint8(1, down ? 1 : 0);
  b.setUint32(4, keysym);
  return b.buffer.asUint8List();
}

Uint8List encodePointer(int buttons, int x, int y) {
  final b = ByteData(6);
  b.setUint8(0, 5);
  b.setUint8(1, buttons);
  b.setUint16(2, x);
  b.setUint16(4, y);
  return b.buffer.asUint8List();
}

/// What the parser hands back, in stream order.
sealed class RfbEvent {
  const RfbEvent();
}

class RfbServerVersion extends RfbEvent {
  const RfbServerVersion(this.text);
  final String text;
}

class RfbSecurityTypes extends RfbEvent {
  const RfbSecurityTypes(this.types);
  final List<int> types;
}

class RfbSecurityResult extends RfbEvent {
  const RfbSecurityResult();
}

class RfbServerInit extends RfbEvent {
  const RfbServerInit(this.width, this.height, this.name);
  final int width, height;
  final String name;
}

/// A rectangle of RGBA pixels (already converted from the B,G,R,pad stream).
class RfbRawRect extends RfbEvent {
  const RfbRawRect(this.x, this.y, this.w, this.h, this.rgba);
  final int x, y, w, h;
  final Uint8List rgba;
}

class RfbCopyRect extends RfbEvent {
  const RfbCopyRect(this.x, this.y, this.w, this.h, this.srcX, this.srcY);
  final int x, y, w, h, srcX, srcY;
}

/// One FramebufferUpdate is complete: ask for the next, incrementally.
class RfbUpdateEnd extends RfbEvent {
  const RfbUpdateEnd();
}

class RfbProtocolFault implements Exception {
  const RfbProtocolFault(this.what);
  final String what;
  @override
  String toString() => what;
}

enum _Stage { version, security, result, init, message, rects }

/// Incremental server-to-client parser. Feed bytes with [add]; it returns the
/// events that are now whole, and waits (cheaply) for the rest of a big one.
class RfbParser {
  ZrleDecoder? _zrle;
  Uint8List _data = Uint8List(0);
  int _pos = 0;
  int _need = 0;
  final List<Uint8List> _pending = [];
  int _pendingLen = 0;
  _Stage _stage = _Stage.version;
  int _rectsLeft = 0;
  bool _emitEnd = false;

  List<RfbEvent> add(List<int> chunk) {
    final bytes = chunk is Uint8List ? chunk : Uint8List.fromList(chunk);
    _pending.add(bytes);
    _pendingLen += bytes.length;
    if ((_data.length - _pos) + _pendingLen < _need) return const [];
    _merge();
    final out = <RfbEvent>[];
    while (true) {
      final event = _next();
      if (event == null) break;
      out.add(event);
    }
    return out;
  }

  void _merge() {
    final rest = _data.length - _pos;
    final all = Uint8List(rest + _pendingLen);
    all.setRange(0, rest, _data, _pos);
    var at = rest;
    for (final p in _pending) {
      all.setRange(at, at + p.length, p);
      at += p.length;
    }
    _data = all;
    _pos = 0;
    _pending.clear();
    _pendingLen = 0;
  }

  int get _have => _data.length - _pos;

  bool _want(int n) {
    if (_have >= n) {
      _need = 0;
      return true;
    }
    _need = n;
    return false;
  }

  ByteData get _view => ByteData.sublistView(_data, _pos);

  RfbEvent? _next() {
    if (_emitEnd) {
      _emitEnd = false;
      return const RfbUpdateEnd();
    }
    switch (_stage) {
      case _Stage.version:
        if (!_want(12)) return null;
        final text =
            ascii.decode(_data.sublist(_pos, _pos + 12), allowInvalid: true);
        _pos += 12;
        if (!text.startsWith('RFB ')) {
          throw const RfbProtocolFault('Not an RFB server');
        }
        _stage = _Stage.security;
        return RfbServerVersion(text);
      case _Stage.security:
        if (!_want(1)) return null;
        final count = _data[_pos];
        if (count == 0) throw const RfbProtocolFault('Connection refused');
        if (!_want(1 + count)) return null;
        final types = _data.sublist(_pos + 1, _pos + 1 + count).toList();
        _pos += 1 + count;
        _stage = _Stage.result;
        return RfbSecurityTypes(types);
      case _Stage.result:
        if (!_want(4)) return null;
        final ok = _view.getUint32(0) == 0;
        _pos += 4;
        if (!ok) throw const RfbProtocolFault('Security refused');
        _stage = _Stage.init;
        return const RfbSecurityResult();
      case _Stage.init:
        if (!_want(24)) return null;
        final nameLen = _view.getUint32(20);
        if (nameLen > 4096) throw const RfbProtocolFault('Name too long');
        if (!_want(24 + nameLen)) return null;
        final v = _view;
        final event = RfbServerInit(
          v.getUint16(0),
          v.getUint16(2),
          utf8.decode(_data.sublist(_pos + 24, _pos + 24 + nameLen),
              allowMalformed: true),
        );
        _pos += 24 + nameLen;
        _stage = _Stage.message;
        return event;
      case _Stage.message:
        return _message();
      case _Stage.rects:
        return _rect();
    }
  }

  RfbEvent? _message() {
    if (!_want(1)) return null;
    switch (_data[_pos]) {
      case 0:
        if (!_want(4)) return null;
        _rectsLeft = _view.getUint16(2);
        _pos += 4;
        if (_rectsLeft == 0) return const RfbUpdateEnd();
        _stage = _Stage.rects;
        return _rect();
      case 2: // Bell
        _pos += 1;
        return _message();
      case 3: // ServerCutText: read and dropped, never shown or kept
        if (!_want(8)) return null;
        final len = _view.getUint32(4);
        if (len > 1 << 20) throw const RfbProtocolFault('Clipboard too long');
        if (!_want(8 + len)) return null;
        _pos += 8 + len;
        return _message();
      default:
        throw RfbProtocolFault('Unknown message ${_data[_pos]}');
    }
  }

  RfbEvent? _rect() {
    if (!_want(12)) return null;
    final v = _view;
    final x = v.getUint16(0), y = v.getUint16(2);
    final w = v.getUint16(4), h = v.getUint16(6);
    final encoding = v.getInt32(8);
    final RfbEvent event;
    if (encoding == encodingRaw) {
      final size = w * h * 4;
      if (!_want(12 + size)) return null;
      final rgba = Uint8List(size);
      final base = _pos + 12;
      for (var i = 0; i < size; i += 4) {
        rgba[i] = _data[base + i + 2];
        rgba[i + 1] = _data[base + i + 1];
        rgba[i + 2] = _data[base + i];
        rgba[i + 3] = 255;
      }
      _pos += 12 + size;
      event = RfbRawRect(x, y, w, h, rgba);
    } else if (encoding == encodingCopyRect) {
      if (!_want(16)) return null;
      event = RfbCopyRect(x, y, w, h, _view.getUint16(12), _view.getUint16(14));
      _pos += 16;
    } else if (encoding == encodingZrle) {
      if (!_want(16)) return null;
      final len = v.getUint32(12);
      if (len > 1 << 26) throw const RfbProtocolFault('ZRLE too long');
      if (!_want(16 + len)) return null;
      final packed = Uint8List.sublistView(_data, _pos + 16, _pos + 16 + len);
      event = RfbRawRect(x, y, w, h, (_zrle ??= ZrleDecoder()).decode(packed, w, h));
      _pos += 16 + len;
    } else {
      throw RfbProtocolFault('Unsupported encoding $encoding');
    }
    _rectsLeft -= 1;
    if (_rectsLeft == 0) {
      _stage = _Stage.message;
      _emitEnd = true;
    }
    return event;
  }
}
