import 'dart:math' as math;
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'lens_geometry.dart';
import 'lens_specs.dart';
import 'lensbot.dart';

/// The box a Lensbot's body (and ears) covers on the 48-unit grid.
ui.Rect lensbotBounds(String shape) {
  final g = lensGeometry(lensSpec(shape));
  var box = ui.Rect.fromPoints(g.pts.first, g.pts.first);
  for (final p in g.pts) {
    box = box.expandToInclude(ui.Rect.fromPoints(p, p));
  }
  for (final (c, r) in g.ears) {
    box = box.expandToInclude(ui.Rect.fromCircle(center: c, radius: r));
  }
  return box;
}

/// Draws a Lensbot exactly as the app does (no shadow, no star) into a
/// [size]×[size] PNG: centred, its longer side [fill] of the image, on an
/// optional [background] with corners of [corner]×size. Used for the app's
/// launcher icon (tool) and each bot's face on its notifications.
Future<Uint8List> lensbotPng({
  required ui.Color colour,
  required String shape,
  required int size,
  ui.Color? background,
  double fill = 0.9,
  double corner = 0,
}) async {
  final recorder = ui.PictureRecorder();
  final canvas = ui.Canvas(recorder);
  final side = size.toDouble();
  if (background != null) {
    final rect = ui.Rect.fromLTWH(0, 0, side, side);
    canvas.drawRRect(ui.RRect.fromRectAndRadius(rect, ui.Radius.circular(side * corner)),
        ui.Paint()..color = background);
  }
  final box = lensbotBounds(shape);
  final scale = side * fill / math.max(box.width, box.height);
  canvas.translate(side / 2, side / 2);
  canvas.scale(scale);
  canvas.translate(-box.center.dx, -box.center.dy);
  LensbotPainter(colour, shape: shape, shadow: false)
      .paint(canvas, const ui.Size(lensView, lensView));
  final image = await recorder.endRecording().toImage(size, size);
  try {
    final data = await image.toByteData(format: ui.ImageByteFormat.png);
    if (data == null) throw StateError('the PNG could not be made');
    return data.buffer.asUint8List();
  } finally {
    image.dispose();
  }
}
