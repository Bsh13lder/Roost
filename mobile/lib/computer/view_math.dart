import 'dart:math' as math;
import 'dart:ui';

const zoomMax = 5.0;

/// How the remote screen sits in the viewport: letterboxed to fit, then
/// zoomed by [scale] about the viewport's top-left and moved by [offset].
class ScreenView {
  const ScreenView(
      {this.scale = 1, this.offset = Offset.zero});

  final double scale;
  final Offset offset;

  bool get zoomed => scale > 1.02;

  /// The rectangle the screen fills in the viewport before zoom.
  static Rect fit(Size viewport, Size screen) {
    if (screen.isEmpty || viewport.isEmpty) return Rect.zero;
    final s = math.min(
        viewport.width / screen.width, viewport.height / screen.height);
    final w = screen.width * s, h = screen.height * s;
    return Rect.fromLTWH((viewport.width - w) / 2, (viewport.height - h) / 2, w, h);
  }

  /// A viewport point as a pixel of the remote screen, or null outside it.
  Offset? toScreen(Offset point, Size viewport, Size screen) {
    final box = fit(viewport, screen);
    if (box.isEmpty) return null;
    final p = (point - offset) / scale;
    if (!box.contains(p)) return null;
    return Offset((p.dx - box.left) / box.width * screen.width,
        (p.dy - box.top) / box.height * screen.height);
  }

  /// A remote screen pixel as a viewport point (for the bot's ring).
  Offset fromScreen(Offset pixel, Size viewport, Size screen) {
    final box = fit(viewport, screen);
    final p = Offset(box.left + pixel.dx / screen.width * box.width,
        box.top + pixel.dy / screen.height * box.height);
    return p * scale + offset;
  }

  ScreenView zoomAbout(double factor, Offset focal, Size viewport) {
    final next = (scale * factor).clamp(1.0, zoomMax);
    final ratio = next / scale;
    return ScreenView(scale: next, offset: focal - (focal - offset) * ratio)
        .clamped(viewport);
  }

  ScreenView panBy(Offset delta, Size viewport) =>
      ScreenView(scale: scale, offset: offset + delta).clamped(viewport);

  /// Keeps the zoomed screen covering the viewport; unzoomed it is centred.
  ScreenView clamped(Size viewport) {
    if (scale <= 1.0) return const ScreenView();
    final minX = viewport.width - viewport.width * scale;
    final minY = viewport.height - viewport.height * scale;
    return ScreenView(
      scale: scale,
      offset: Offset(offset.dx.clamp(minX, 0.0), offset.dy.clamp(minY, 0.0)),
    );
  }
}
