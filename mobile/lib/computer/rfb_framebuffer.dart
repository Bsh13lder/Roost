import 'dart:typed_data';

import 'rfb_codec.dart';

/// The remote screen as RGBA bytes. It is the one mutable buffer on purpose:
/// a screen update rewrites a few rectangles of a few megabytes, and copying
/// the whole buffer for each would stall the picture.
class RfbFramebuffer {
  RfbFramebuffer(this.width, this.height)
      : rgba = Uint8List(width * height * 4);

  final int width, height;
  final Uint8List rgba;

  void apply(RfbEvent event) {
    if (event is RfbRawRect) {
      _raw(event);
    } else if (event is RfbCopyRect) {
      _copy(event);
    }
  }

  bool _inside(int x, int y, int w, int h) =>
      x >= 0 && y >= 0 && w >= 0 && h >= 0 && x + w <= width && y + h <= height;

  void _raw(RfbRawRect r) {
    if (!_inside(r.x, r.y, r.w, r.h)) return;
    for (var row = 0; row < r.h; row++) {
      final from = row * r.w * 4;
      final to = ((r.y + row) * width + r.x) * 4;
      rgba.setRange(to, to + r.w * 4, r.rgba, from);
    }
  }

  void _copy(RfbCopyRect r) {
    if (!_inside(r.x, r.y, r.w, r.h) || !_inside(r.srcX, r.srcY, r.w, r.h)) {
      return;
    }
    // Read the source first: the two rectangles may overlap.
    final copy = Uint8List(r.w * r.h * 4);
    for (var row = 0; row < r.h; row++) {
      final from = ((r.srcY + row) * width + r.srcX) * 4;
      copy.setRange(row * r.w * 4, (row + 1) * r.w * 4, rgba, from);
    }
    for (var row = 0; row < r.h; row++) {
      final to = ((r.y + row) * width + r.x) * 4;
      rgba.setRange(to, to + r.w * 4, copy, row * r.w * 4);
    }
  }
}
