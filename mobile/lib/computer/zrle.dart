import 'dart:io' show RawZLibFilter;
import 'dart:typed_data';

import 'rfb_codec.dart' show RfbProtocolFault;

const encodingZrle = 16;
const _tile = 64;

/// Decodes ZRLE rectangles (RFC 6143 §7.7.6) into RGBA. One zlib stream
/// lasts the whole connection, so a decoder is made once per session and fed
/// every ZRLE rectangle in order. The pixel format is the one this app asks
/// for (32 bpp, depth 24, little endian), so a CPIXEL is three bytes: B, G, R.
class ZrleDecoder {
  ZrleDecoder() : _z = RawZLibFilter.inflateFilter();

  final RawZLibFilter _z;

  Uint8List decode(Uint8List compressed, int w, int h) {
    final bytes = _inflate(compressed);
    final out = Uint8List(w * h * 4);
    final r = _Reader(bytes);
    try {
      for (var ty = 0; ty < h; ty += _tile) {
        for (var tx = 0; tx < w; tx += _tile) {
          final tw = tx + _tile > w ? w - tx : _tile;
          final th = ty + _tile > h ? h - ty : _tile;
          _tileInto(r, out, w, tx, ty, tw, th);
        }
      }
    } on RangeError {
      throw const RfbProtocolFault('Short ZRLE data');
    }
    return out;
  }

  Uint8List _inflate(Uint8List data) {
    try {
      _z.process(data, 0, data.length);
      final out = BytesBuilder(copy: false);
      for (;;) {
        final chunk = _z.processed(flush: false);
        if (chunk == null || chunk.isEmpty) break;
        out.add(chunk);
      }
      return out.takeBytes();
    } on Exception {
      throw const RfbProtocolFault('Bad ZRLE data');
    }
  }

  void _tileInto(
      _Reader r, Uint8List out, int w, int tx, int ty, int tw, int th) {
    final sub = r.byte();
    final rle = sub & 128 != 0;
    final palSize = sub & 127;
    final count = tw * th;
    final palette = <int>[];
    if (!rle && sub == 0) {
      for (var i = 0; i < count; i++) {
        _put(out, w, tx, ty, tw, i, r.pixel());
      }
      return;
    }
    if (!rle && sub == 1) {
      final p = r.pixel();
      for (var i = 0; i < count; i++) {
        _put(out, w, tx, ty, tw, i, p);
      }
      return;
    }
    if ((!rle && sub > 16) || sub == 129) {
      throw const RfbProtocolFault('Bad ZRLE tile');
    }
    if (sub != 128) {
      for (var i = 0; i < palSize; i++) {
        palette.add(r.pixel());
      }
    }
    if (!rle) {
      final bits = palSize == 2 ? 1 : (palSize <= 4 ? 2 : 4);
      for (var row = 0; row < th; row++) {
        var left = 0, cur = 0;
        for (var col = 0; col < tw; col++) {
          if (left == 0) {
            cur = r.byte();
            left = 8;
          }
          left -= bits;
          final idx = (cur >> left) & ((1 << bits) - 1);
          if (idx >= palette.length) {
            throw const RfbProtocolFault('Bad ZRLE palette index');
          }
          _put(out, w, tx, ty, tw, row * tw + col, palette[idx]);
        }
      }
      return;
    }
    var at = 0;
    while (at < count) {
      int pixel;
      if (sub == 128) {
        pixel = r.pixel();
      } else {
        var idx = r.byte();
        final isRun = idx & 128 != 0;
        idx &= 127;
        if (idx >= palette.length) {
          throw const RfbProtocolFault('Bad ZRLE palette index');
        }
        pixel = palette[idx];
        if (!isRun) {
          _put(out, w, tx, ty, tw, at++, pixel);
          continue;
        }
      }
      var len = 1;
      int b;
      do {
        b = r.byte();
        len += b;
      } while (b == 255);
      if (at + len > count) throw const RfbProtocolFault('ZRLE run too long');
      for (var i = 0; i < len; i++) {
        _put(out, w, tx, ty, tw, at++, pixel);
      }
    }
  }

  /// [pixel] is r | g << 8 | b << 16, as [_Reader.pixel] returns it.
  void _put(Uint8List out, int w, int tx, int ty, int tw, int i, int pixel) {
    final x = tx + i % tw, y = ty + i ~/ tw;
    final o = (y * w + x) * 4;
    out[o] = pixel & 255;
    out[o + 1] = (pixel >> 8) & 255;
    out[o + 2] = (pixel >> 16) & 255;
    out[o + 3] = 255;
  }
}

class _Reader {
  _Reader(this.data);
  final Uint8List data;
  int pos = 0;

  int byte() => data[pos++];

  /// One CPIXEL: B, G, R in the stream, returned as r | g << 8 | b << 16.
  int pixel() {
    final b = data[pos], g = data[pos + 1], r = data[pos + 2];
    pos += 3;
    return r | (g << 8) | (b << 16);
  }
}
