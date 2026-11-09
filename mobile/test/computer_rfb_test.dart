import 'dart:convert';
import 'dart:typed_data';
import 'dart:ui';

import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/computer/keysyms.dart';
import 'package:roost_mobile/computer/rfb_codec.dart';
import 'package:roost_mobile/computer/rfb_framebuffer.dart';
import 'package:roost_mobile/computer/touch_interpreter.dart';
import 'package:roost_mobile/computer/view_math.dart';

Uint8List bytes(List<int> l) => Uint8List.fromList(l);

Uint8List serverInit(int w, int h, String name) {
  final n = utf8.encode(name);
  final b = ByteData(24 + n.length);
  b.setUint16(0, w);
  b.setUint16(2, h);
  b.setUint8(4, 32);
  b.setUint8(5, 24);
  b.setUint32(20, n.length);
  final out = b.buffer.asUint8List();
  out.setRange(24, 24 + n.length, n);
  return out;
}

Uint8List rawUpdate(int x, int y, int w, int h, List<int> bgrx) {
  final head = ByteData(16)
    ..setUint8(0, 0)
    ..setUint16(2, 1)
    ..setUint16(4, x)
    ..setUint16(6, y)
    ..setUint16(8, w)
    ..setUint16(10, h)
    ..setInt32(12, encodingRaw);
  return bytes([...head.buffer.asUint8List(), ...bgrx]);
}

void main() {
  group('client messages', () {
    test('version, security and init bytes', () {
      expect(utf8.decode(encodeVersion()), 'RFB 003.008\n');
      expect(encodeSecurityNone(), [1]);
      expect(encodeClientInit(), [1]);
    });

    test('SetPixelFormat asks for 32 bpp little endian BGRX', () {
      final m = encodeSetPixelFormat();
      expect(m.length, 20);
      expect(m[0], 0);
      expect(m.sublist(4, 8), [32, 24, 0, 1]);
      expect(m.sublist(8, 14), [0, 255, 0, 255, 0, 255]);
      expect(m.sublist(14, 17), [16, 8, 0]);
    });

    test('SetEncodings lists CopyRect then Raw', () {
      expect(encodeSetEncodings([encodingCopyRect, encodingRaw]),
          [2, 0, 0, 2, 0, 0, 0, 1, 0, 0, 0, 0]);
    });

    test('update request, key and pointer', () {
      expect(
          encodeUpdateRequest(incremental: true, x: 0, y: 0, w: 1280, h: 800),
          [3, 1, 0, 0, 0, 0, 5, 0, 3, 32]);
      expect(encodeKey(0xFF0D, down: true), [4, 1, 0, 0, 0, 0, 0xFF, 0x0D]);
      expect(encodePointer(buttonLeft, 300, 20), [5, 1, 1, 44, 0, 20]);
    });
  });

  group('server parser', () {
    test('handshake in order, split across chunks', () {
      final p = RfbParser();
      expect(p.add(ascii.encode('RFB 003')).length, 0);
      final v = p.add(ascii.encode('.008\n'));
      expect(v.single, isA<RfbServerVersion>());
      expect((p.add([1, 1]).single as RfbSecurityTypes).types, [1]);
      expect(p.add([0, 0, 0, 0]).single, isA<RfbSecurityResult>());
      final init = p.add(serverInit(1280, 800, 'Fake')).single as RfbServerInit;
      expect((init.width, init.height, init.name), (1280, 800, 'Fake'));
    });

    RfbParser ready() {
      final p = RfbParser();
      p.add([...ascii.encode('RFB 003.008\n'), 1, 1, 0, 0, 0, 0]);
      p.add(serverInit(4, 4, 'x'));
      return p;
    }

    test('a raw rectangle becomes RGBA and ends the update', () {
      final p = ready();
      final events = p.add(rawUpdate(1, 2, 1, 1, [10, 20, 30, 0]));
      final rect = events.first as RfbRawRect;
      expect(rect.rgba, [30, 20, 10, 255]);
      expect((rect.x, rect.y), (1, 2));
      expect(events.last, isA<RfbUpdateEnd>());
    });

    test('a rectangle that arrives in pieces waits for all of it', () {
      final p = ready();
      final all = rawUpdate(0, 0, 2, 1, [1, 2, 3, 0, 4, 5, 6, 0]);
      expect(p.add(all.sublist(0, 10)), isEmpty);
      expect(p.add(all.sublist(10, 20)), isEmpty);
      expect(p.add(all.sublist(20)).length, 2);
    });

    test('CopyRect, Bell and server cut text are read', () {
      final p = ready();
      final copy = ByteData(20)
        ..setUint8(0, 0)
        ..setUint16(2, 1)
        ..setUint16(4, 0)
        ..setUint16(6, 0)
        ..setUint16(8, 2)
        ..setUint16(10, 2)
        ..setInt32(12, encodingCopyRect)
        ..setUint16(16, 2)
        ..setUint16(18, 2);
      final events = p.add([
        2, // bell
        3, 0, 0, 0, 0, 0, 0, 2, 104, 105, // cut text "hi"
        ...copy.buffer.asUint8List(),
      ]);
      final c = events.first as RfbCopyRect;
      expect((c.srcX, c.srcY, c.w), (2, 2, 2));
      expect(events.last, isA<RfbUpdateEnd>());
    });

    test('an unknown message or encoding is a fault', () {
      final p = ready();
      expect(() => p.add([99]), throwsA(isA<RfbProtocolFault>()));
      final q = ready();
      final bad = rawUpdate(0, 0, 1, 1, [0, 0, 0, 0]);
      ByteData.sublistView(bad).setInt32(12, 16); // ZRLE, not asked for
      expect(() => q.add(bad), throwsA(isA<RfbProtocolFault>()));
    });
  });

  group('framebuffer', () {
    test('raw pixels land at their place and CopyRect moves them', () {
      final fb = RfbFramebuffer(4, 4);
      fb.apply(RfbRawRect(0, 0, 1, 1, bytes([9, 8, 7, 255])));
      expect(fb.rgba.sublist(0, 4), [9, 8, 7, 255]);
      fb.apply(const RfbCopyRect(3, 3, 1, 1, 0, 0));
      expect(fb.rgba.sublist((3 * 4 + 3) * 4), [9, 8, 7, 255]);
    });

    test('a rectangle outside the screen is ignored', () {
      final fb = RfbFramebuffer(2, 2);
      fb.apply(RfbRawRect(1, 1, 2, 2, Uint8List(16)..fillRange(0, 16, 5)));
      expect(fb.rgba.every((b) => b == 0), isTrue);
    });
  });

  group('keys', () {
    test('keysyms for letters, Enter and other scripts', () {
      expect(keysymForRune('a'.runes.first), 0x61);
      expect(keysymForRune(10), keyReturn);
      expect(keysymForRune('é'.runes.first), 0xE9);
      expect(keysymForRune('€'.runes.first), 0x01000000 + 0x20AC);
    });

    test('a text edit is backspaces then new characters', () {
      final d = diffToKeys('​', 'a');
      expect(d.backspaces, 1);
      expect(d.keysyms, [0x61]);
      final gone = diffToKeys('​', '');
      expect(gone.backspaces, 1);
      expect(gone.keysyms, isEmpty);
    });
  });

  group('view', () {
    const viewport = Size(400, 400);
    const screen = Size(1280, 800);

    test('letterboxing maps a tap to a screen pixel', () {
      const v = ScreenView();
      final box = ScreenView.fit(viewport, screen);
      expect(box.height, closeTo(250, 0.01));
      expect(v.toScreen(const Offset(200, 200), viewport, screen),
          const Offset(640, 400));
      expect(v.toScreen(const Offset(200, 10), viewport, screen), isNull);
    });

    test('zoom keeps the focal point and never leaves the viewport', () {
      final z = const ScreenView().zoomAbout(2, const Offset(200, 200), viewport);
      expect(z.zoomed, isTrue);
      expect(z.toScreen(const Offset(200, 200), viewport, screen),
          const Offset(640, 400));
      final panned = z.panBy(const Offset(9999, 9999), viewport);
      expect(panned.offset, Offset.zero);
    });
  });

  group('touch', () {
    test('tap, two-finger scroll and two-finger tap', () {
      final log = <String>[];
      final t = TouchInterpreter(_Log(log), zoomed: () => false);
      t.down(1, const Offset(10, 10), Duration.zero);
      t.up(1, const Offset(10, 10), const Duration(milliseconds: 50));
      expect(log, ['tap']);

      log.clear();
      t.down(1, const Offset(100, 200), Duration.zero);
      t.down(2, const Offset(140, 200), Duration.zero);
      for (var y = 190.0; y >= 20; y -= 10) {
        t.move(1, Offset(100, y));
        t.move(2, Offset(140, y));
      }
      t.up(1, const Offset(100, 20), const Duration(seconds: 1));
      t.up(2, const Offset(140, 20), const Duration(seconds: 1));
      expect(log, everyElement(startsWith("scroll+")));
      expect(log, isNotEmpty);

      log.clear();
      t.down(1, const Offset(100, 200), Duration.zero);
      t.down(2, const Offset(140, 200), Duration.zero);
      t.up(2, const Offset(140, 200), const Duration(milliseconds: 100));
      t.up(1, const Offset(100, 200), const Duration(milliseconds: 110));
      expect(log, ['right']);
      t.dispose();
    });

    test('a spreading pinch zooms, and a moving finger drags', () {
      final log = <String>[];
      final t = TouchInterpreter(_Log(log), zoomed: () => false);
      t.down(1, const Offset(100, 200), Duration.zero);
      t.down(2, const Offset(140, 200), Duration.zero);
      t.move(2, const Offset(240, 200));
      t.move(2, const Offset(300, 200));
      expect(log.first, 'pinch');
      t.up(1, const Offset(100, 200), Duration.zero);
      t.up(2, const Offset(300, 200), Duration.zero);

      log.clear();
      t.down(5, const Offset(0, 0), Duration.zero);
      t.move(5, const Offset(30, 0));
      t.up(5, const Offset(30, 0), Duration.zero);
      expect(log, ['dragStart', 'dragMove', 'dragEnd']);
      t.dispose();
    });
  });
}

class _Log implements TouchActions {
  _Log(this.log);
  final List<String> log;
  @override
  void tap(Offset at) => log.add('tap');
  @override
  void rightClick(Offset at) => log.add('right');
  @override
  void dragStart(Offset at) => log.add('dragStart');
  @override
  void dragMove(Offset at) => log.add('dragMove');
  @override
  void dragEnd(Offset at) => log.add('dragEnd');
  @override
  void scroll(Offset at, int ticks) =>
      log.add(ticks > 0 ? 'scroll+' : 'scroll-');
  @override
  void pinch(double factor, Offset focal) => log.add('pinch');
  @override
  void pan(Offset delta) => log.add('pan');
}
