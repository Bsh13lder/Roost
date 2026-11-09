import 'package:flutter/material.dart';

import '../theme/tokens.dart';
import 'lens_geometry.dart';
import 'lens_specs.dart';

/// The seven eye styles, in eye units (eyeStyles.ts), drawn at [k] scale.
Path _eyePath(EyeId id) {
  switch (id) {
    case EyeId.round:
      return Path()..addOval(Rect.fromCenter(center: Offset.zero, width: 20, height: 20));
    case EyeId.oval:
      return Path()..addOval(Rect.fromCenter(center: Offset.zero, width: 21.6, height: 15.6));
    case EyeId.tall:
      return Path()..addOval(Rect.fromCenter(center: Offset.zero, width: 14.8, height: 22.4));
    case EyeId.square:
      return Path()
        ..addRRect(RRect.fromRectAndRadius(
            Rect.fromCenter(center: Offset.zero, width: 18.4, height: 18.4),
            const Radius.circular(5)));
    case EyeId.half:
      return Path()
        ..moveTo(-10, -2.6)
        ..cubicTo(-5, -4.6, 5, -4.6, 10, -2.6)
        ..arcToPoint(const Offset(-10, -2.6),
            radius: const Radius.circular(10.4), largeArc: true)
        ..close();
    case EyeId.almond:
      return Path()
        ..moveTo(-12.6, 0)
        ..cubicTo(-7.8, -9.6, 7.8, -9.6, 12.6, 0)
        ..cubicTo(7.8, 9.6, -7.8, 9.6, -12.6, 0)
        ..close();
    case EyeId.ring:
      return Path()..addOval(Rect.fromCenter(center: Offset.zero, width: 16.8, height: 16.8));
  }
}

const _pupil = <EyeId, (double r, double py)>{
  EyeId.round: (4.4, 0),
  EyeId.oval: (4, 0),
  EyeId.tall: (3.9, 0),
  EyeId.square: (4.2, 0),
  EyeId.half: (4.1, 3.4),
  EyeId.almond: (3.9, 0),
  EyeId.ring: (3.7, 0),
};

/// [pupil] moves both pupils (eye units) while the bot works.
void paintEyes(Canvas canvas, LensGeometry g, bool asleep, {Offset pupil = Offset.zero}) {
  final (pr, py) = _pupil[g.eyes]!;
  for (final x in g.eyeX) {
    canvas.save();
    canvas.translate(x, g.eyeY);
    canvas.scale(g.k);
    final eye = _eyePath(g.eyes);
    canvas.drawPath(eye, Paint()..color = Tokens.lensSclera);
    canvas.save();
    canvas.clipPath(eye);
    canvas.drawCircle(Offset(1, py + 0.8) + pupil, pr, Paint()..color = Tokens.lensPupil);
    canvas.drawCircle(Offset(-0.8 - pr * 0.1, py - pr * 0.45) + pupil, pr * 0.28,
        Paint()..color = Tokens.lensHighlight);
    if (asleep) {
      canvas.drawRect(const Rect.fromLTRB(-14, -14, 14, 1.5),
          Paint()..color = Tokens.lensVisor);
    }
    canvas.restore();
    canvas.restore();
  }
}
