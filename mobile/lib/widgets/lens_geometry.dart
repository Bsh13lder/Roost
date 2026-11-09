import 'dart:math' as math;
import 'dart:ui';

import 'lens_specs.dart';

// Geometry of a Lensbot on the 48-unit grid (lensbot.ts bodyPoints / visorLayout).

const lensView = 48.0;
const _centerX = 24.0;
const _ground = 43.0;
const _feetH = 4.2;
const _topRoom = 4.6;
const _eyeLine = 0.07;
const _eyeKMax = 0.74;
const _pointCount = 48;

const _visors = <VisorKind, (double f, double h, double dx)>{
  VisorKind.band: (0.88, 16, 0.25),
  VisorKind.pill: (0.72, 15.5, 0.25),
  VisorKind.goggle: (0.8, 16, 0.25),
  VisorKind.screen: (0.76, 19, 0.24),
  VisorKind.brow: (0.84, 16.5, 0.25),
  VisorKind.mask: (0.92, 17, 0.25),
};

/// Eye style numbers: top, bottom, half width (eye units).
const eyeNumbers = <EyeId, (double top, double bot, double hw)>{
  EyeId.round: (-10, 10, 10),
  EyeId.oval: (-7.8, 7.8, 10.8),
  EyeId.tall: (-11.2, 11.2, 7.4),
  EyeId.square: (-9.2, 9.2, 9.2),
  EyeId.half: (-4.1, 10.7, 10.4),
  EyeId.almond: (-7.2, 7.2, 12.6),
  EyeId.ring: (-11.1, 11.1, 11.1),
};

class LensGeometry {
  const LensGeometry({
    required this.pts,
    required this.cy,
    required this.visor,
    required this.eyeX,
    required this.eyeY,
    required this.k,
    required this.eyes,
    required this.visorRect,
    required this.visorRadius,
    required this.ears,
  });

  final List<Offset> pts;
  final double cy;
  final VisorKind visor;
  final List<double> eyeX;
  final double eyeY;
  final double k;
  final EyeId eyes;
  final Rect visorRect;
  final double visorRadius; // goggle lens radius
  final List<(Offset, double)> ears;
}

double _centerY(LensSpec s) =>
    math.max(s.h / 2 + _topRoom, _ground - (s.feet ? _feetH : 0) - s.h / 2);

double _angleDiff(double a, double b) {
  final d = (a - b) % (2 * math.pi);
  if (d > math.pi) return d - 2 * math.pi;
  return d < -math.pi ? d + 2 * math.pi : d;
}

List<Offset> bodyPoints(LensSpec s) {
  final cy = _centerY(s);
  final out = <Offset>[];
  for (var i = 0; i < _pointCount; i++) {
    final t = -math.pi / 2 + (i / _pointCount) * 2 * math.pi;
    final c = math.cos(t), sn = math.sin(t);
    final n = sn < 0 ? s.nt : s.nb;
    var x = c.sign * math.pow(c.abs(), 2 / n) * (s.w / 2);
    var y = sn.sign * math.pow(sn.abs(), 2 / n) * (s.h / 2);
    x *= 1 + s.taper * (y / (s.h / 2));
    for (final (angle, depth, width) in s.dents) {
      final k = depth *
          math.exp(-math.pow(
              _angleDiff(t, angle * math.pi / 180) / (width * math.pi / 180),
              2));
      x *= 1 - k;
      y *= 1 - k;
    }
    out.add(Offset(_centerX + x, cy + y));
  }
  return out;
}

(double, double) _widthAt(List<Offset> pts, double y) {
  var low = double.infinity, high = double.negativeInfinity;
  for (var i = 0; i < pts.length; i++) {
    final a = pts[i], b = pts[(i + 1) % pts.length];
    if ((a.dy - y) * (b.dy - y) > 0 || a.dy == b.dy) continue;
    final x = a.dx + ((y - a.dy) / (b.dy - a.dy)) * (b.dx - a.dx);
    low = math.min(low, x);
    high = math.max(high, x);
  }
  return high > low ? (low, high) : (_centerX - 10, _centerX + 10);
}

final _cache = <String, LensGeometry>{};

LensGeometry lensGeometry(LensSpec s) {
  return _cache.putIfAbsent(s.id, () {
    final cy = _centerY(s);
    final pts = bodyPoints(s);
    final (f, vh0, dxf) = _visors[s.visor]!;
    final (top, bot, hw) = eyeNumbers[s.eyes]!;
    final mid = (top + bot) / 2, hh = (bot - top) / 2;
    final ey = cy - s.h * _eyeLine;
    final (left, right) = _widthAt(pts, ey);
    final centre = (left + right) / 2;
    final w = ((right - left) * f).clamp(22.0, 37.0);
    final h = s.vh ?? vh0;
    final dx = w * dxf;
    final k = math.min(
        math.min((h / 2 - 1.5) / hh, (dx - 1.2) / hw), _eyeKMax);
    final r = math.max(hw, hh) * k + 2.3;
    return LensGeometry(
      pts: pts,
      cy: cy,
      visor: s.visor,
      eyeX: [centre - dx, centre + dx],
      eyeY: ey - mid * k,
      k: k,
      eyes: s.eyes,
      visorRect: Rect.fromLTWH(centre - w / 2, ey - h / 2, w, h),
      visorRadius: r,
      ears: _ears(s, pts, cy),
    );
  });
}

List<(Offset, double)> _ears(LensSpec s, List<Offset> pts, double cy) {
  final e = s.ears;
  if (e == null) return const [];
  final (a, r, side) = e;
  final inset = side ? -0.12 : 0.35;
  return [-1, 1].map((sd) {
    final i = ((sd * a / 360 * _pointCount).round() + _pointCount) % _pointCount;
    final p = pts[i];
    final dx = p.dx - _centerX, dy = p.dy - cy;
    final d = math.sqrt(dx * dx + dy * dy);
    final dd = d == 0 ? 1 : d;
    return (Offset(p.dx - dx / dd * r * inset, p.dy - dy / dd * r * inset), r);
  }).toList();
}

/// A closed Catmull-Rom path through the points.
Path smoothPath(List<Offset> pts) {
  final n = pts.length;
  Offset at(int i) => pts[(i + n) % n];
  final path = Path()..moveTo(pts[0].dx, pts[0].dy);
  for (var i = 0; i < n; i++) {
    final p0 = at(i - 1), p1 = at(i), p2 = at(i + 1), p3 = at(i + 2);
    path.cubicTo(
      p1.dx + (p2.dx - p0.dx) / 6, p1.dy + (p2.dy - p0.dy) / 6,
      p2.dx - (p3.dx - p1.dx) / 6, p2.dy - (p3.dy - p1.dy) / 6,
      p2.dx, p2.dy,
    );
  }
  return path..close();
}
