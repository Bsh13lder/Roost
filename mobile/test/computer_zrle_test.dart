import 'dart:io' show RawZLibFilter;
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/computer/rfb_codec.dart';
import 'package:roost_mobile/computer/zrle.dart';

/// Compresses in one zlib stream across calls, like a real server.
class _Deflater {
  final _z = RawZLibFilter.deflateFilter();

  Uint8List pack(List<int> raw) {
    _z.process(raw, 0, raw.length);
    final out = BytesBuilder();
    for (;;) {
      final c = _z.processed(flush: true);
      if (c == null || c.isEmpty) break;
      out.add(c);
    }
    return out.takeBytes();
  }
}

// A CPIXEL is B, G, R.
List<int> px(int r, int g, int b) => [b, g, r];

void main() {
  test('solid, packed-palette, RLE and palette-RLE tiles decode to RGBA', () {
    final d = _Deflater();
    final z = ZrleDecoder();

    // 70 x 2: a 64-wide solid tile, then a 6-wide two-colour tile.
    final first = <int>[
      1, ...px(10, 20, 30),
      2, ...px(1, 2, 3), ...px(4, 5, 6),
      0x2A << 2, // row 0: 1,0,1,0,1,0 (MSB first)
      0x15 << 2, // row 1: 0,1,0,1,0,1
    ];
    // 0x2A<<2 = 101010 00, 0x15<<2 = 010101 00
    final a = z.decode(d.pack(first), 70, 2);
    expect(a.sublist(0, 4), [10, 20, 30, 255]);
    expect(a.sublist(63 * 4, 63 * 4 + 4), [10, 20, 30, 255]);
    expect(a.sublist(64 * 4, 64 * 4 + 4), [4, 5, 6, 255]); // index 1
    expect(a.sublist(65 * 4, 65 * 4 + 4), [1, 2, 3, 255]); // index 0
    expect(a.sublist((70 + 64) * 4, (70 + 64) * 4 + 4), [1, 2, 3, 255]);

    // The same zlib stream carries on: 4 x 2 plain RLE (one 8-pixel run),
    // then 4 x 2 palette RLE (two colours, runs of 3 and 5).
    final rle = <int>[128, ...px(9, 9, 9), 7]; // length 1 + 7 = 8
    final b = z.decode(d.pack(rle), 4, 2);
    expect(b.sublist(28, 32), [9, 9, 9, 255]);

    final pal = <int>[
      130, ...px(1, 1, 1), ...px(2, 2, 2),
      0x80 | 0, 2, // palette 0, run 1 + 2 = 3
      0x80 | 1, 4, // palette 1, run 1 + 4 = 5
    ];
    final c = z.decode(d.pack(pal), 4, 2);
    expect(c.sublist(8, 12), [1, 1, 1, 255]);
    expect(c.sublist(12, 16), [2, 2, 2, 255]);
  });

  test('the parser turns a ZRLE rectangle into one RGBA rectangle', () {
    final d = _Deflater();
    final data = d.pack([1, ...px(5, 6, 7)]);
    final msg = BytesBuilder()
      ..add([0, 0, 0, 1]) // FramebufferUpdate, one rectangle
      ..add([0, 0, 0, 0, 0, 2, 0, 2]) // x y w h = 0 0 2 2
      ..add([0, 0, 0, encodingZrle])
      ..add([0, 0, 0, data.length])
      ..add(data);
    final p = RfbParser();
    p.add([...'RFB 003.008\n'.codeUnits, 1, 1, 0, 0, 0, 0]);
    p.add(Uint8List(25)
      ..[1] = 4
      ..[3] = 4
      ..[23] = 1);
    final events = p.add(msg.takeBytes());
    final rect = events.first as RfbRawRect;
    expect(rect.rgba.sublist(0, 4), [5, 6, 7, 255]);
    expect(rect.rgba.length, 16);
    expect(events.last, isA<RfbUpdateEnd>());
  });

  test('a bad palette index is refused', () {
    final d = _Deflater();
    final z = ZrleDecoder();
    expect(
        () => z.decode(
            d.pack([130, ...px(1, 1, 1), ...px(2, 2, 2), 0x80 | 5, 0]), 2, 1),
        throwsA(isA<RfbProtocolFault>()));
  });

  // Owner, 2026-11-01: the live screen dropped whenever the bot's page changed. A whole new page is one big ZRLE
  // rectangle of raw tiles; every inflated byte of it must come out at once, none held in zlib for later.
  test('a page-sized update of raw tiles decodes whole, twice on one stream', () {
    final d = _Deflater();
    final z = ZrleDecoder();
    const w = 1280, h = 720;
    var seed = 7;
    int next() => seed = (seed * 1103515245 + 12345) & 0x7fffffff;
    List<int> page() {
      final raw = <int>[];
      for (var ty = 0; ty < h; ty += 64) {
        for (var tx = 0; tx < w; tx += 64) {
          final tw = tx + 64 > w ? w - tx : 64;
          final th = ty + 64 > h ? h - ty : 64;
          raw.add(0); // a raw tile: every CPIXEL in full
          for (var i = 0; i < tw * th; i++) {
            raw.addAll([next() & 255, next() & 255, next() & 255]);
          }
        }
      }
      return raw;
    }
    for (var round = 0; round < 2; round++) {
      final raw = page();
      final out = z.decode(d.pack(raw), w, h);
      final last = raw.sublist(raw.length - 3); // B, G, R of the bottom-right pixel
      expect(out.sublist(out.length - 4), [last[2], last[1], last[0], 255]);
    }
  });
}
