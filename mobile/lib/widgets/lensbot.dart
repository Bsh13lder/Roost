import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../api/models.dart';
import '../theme/tokens.dart';
import 'lens_doing.dart';
import 'lens_eyes.dart';
import 'lens_geometry.dart';
import 'lens_specs.dart';

/// A bot's avatar: one of the eighteen Lensbot bodies in the bot's colour, a
/// dark visor with two lens eyes, and the main bot's star. Ported from
/// web/src/components/robot/lensbot.ts. Older stored shapes draw as a Lensbot.
class LensbotAvatar extends StatelessWidget {
  const LensbotAvatar({
    super.key,
    required this.avatar,
    this.size = 56,
    this.star = false,
    this.status = BotStatus.resting,
  });

  final Avatar avatar;
  final double size;
  final bool star;
  final BotStatus status;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: size,
      height: size,
      child: CustomPaint(
        painter: LensbotPainter(avatar.colour,
            shape: avatar.shape, star: star, status: status),
      ),
    );
  }
}

class LensbotPainter extends CustomPainter {
  LensbotPainter(this.colour,
      {this.shape = 'mochi',
      this.star = false,
      this.status = BotStatus.resting,
      this.shadow = true,
      this.pose});

  final Color colour;
  final String shape;
  final bool star;
  final BotStatus status;

  /// The soft ground shadow; an icon leaves it out.
  final bool shadow;

  /// A working robot's moment: its head bobs, tilts and nods, its pupils look
  /// where the work is (lens_doing.dart). Null: at rest.
  final LensPose? pose;

  @override
  void paint(Canvas canvas, Size size) {
    final spec = lensSpec(shape);
    final g = lensGeometry(spec);
    canvas.save();
    canvas.scale(size.width / lensView);
    if (shadow) _shadow(canvas);
    final p = pose ?? const LensPose();
    canvas.translate(0, p.bob + p.nod);
    _behind(canvas, spec, g);
    canvas.save();
    final centre = Offset(24, g.cy);
    canvas.translate(centre.dx, centre.dy);
    canvas.rotate(spec.rot * math.pi / 180 + p.tilt);
    canvas.translate(-centre.dx, -centre.dy);
    _body(canvas, g);
    _visor(canvas, g);
    paintEyes(canvas, g, status == BotStatus.offDuty, pupil: p.pupil);
    canvas.restore();
    canvas.restore();
    if (star) {
      _star(canvas, Offset(size.width * 0.86, size.width * 0.14),
          size.width * 0.14);
    }
  }

  void _shadow(Canvas canvas) {
    canvas.drawOval(Rect.fromCenter(center: const Offset(24, 45), width: 26, height: 3),
        Paint()..color = const Color(0x33000000));
  }

  Color get _dark => Color.lerp(colour, const Color(0xFF000000), 0.3)!;

  void _behind(Canvas canvas, LensSpec spec, LensGeometry g) {
    final paint = Paint()..color = _dark;
    for (final (c, r) in g.ears) {
      canvas.drawCircle(c, r, paint);
    }
    if (spec.feet) {
      for (final sd in [-1.0, 1.0]) {
        canvas.drawRRect(
            RRect.fromRectAndRadius(
                Rect.fromCenter(
                    center: Offset(24 + sd * spec.w * 0.22, 41.5),
                    width: 7,
                    height: 4.4),
                const Radius.circular(2)),
            paint);
      }
    }
    if (spec.nub != null) {
      canvas.drawCircle(Offset(g.pts[0].dx, g.pts[0].dy - spec.nub! * 0.35),
          spec.nub!, paint);
    }
  }

  void _body(Canvas canvas, LensGeometry g) {
    final path = smoothPath(g.pts);
    canvas.drawPath(path, Paint()..color = colour);
    canvas.drawPath(
        path,
        Paint()
          ..style = PaintingStyle.stroke
          ..strokeWidth = 0.9
          ..color = const Color(0x2E000000));
  }

  void _visor(Canvas canvas, LensGeometry g) {
    final paint = Paint()..color = Tokens.lensVisor;
    final r = g.visorRect;
    switch (g.visor) {
      case VisorKind.goggle:
        for (final x in g.eyeX) {
          canvas.drawCircle(Offset(x, r.center.dy), g.visorRadius, paint);
        }
        canvas.drawRect(
            Rect.fromLTRB(g.eyeX[0], r.center.dy - g.visorRadius * 0.42,
                g.eyeX[1], r.center.dy + g.visorRadius * 0.42),
            paint);
      case VisorKind.screen:
        canvas.drawRRect(RRect.fromRectAndRadius(r, const Radius.circular(4.6)), paint);
      case VisorKind.brow:
        canvas.drawRRect(
            RRect.fromRectAndCorners(r,
                topLeft: const Radius.circular(2.2),
                topRight: const Radius.circular(2.2),
                bottomLeft: Radius.circular(r.height / 2),
                bottomRight: Radius.circular(r.height / 2)),
            paint);
      case VisorKind.mask:
        canvas.drawRRect(
            RRect.fromRectAndCorners(r.inflate(0.6),
                topLeft: const Radius.circular(4),
                topRight: const Radius.circular(4),
                bottomLeft: Radius.circular(r.height / 2.4),
                bottomRight: Radius.circular(r.height / 2.4)),
            paint);
      case VisorKind.band || VisorKind.pill:
        canvas.drawRRect(
            RRect.fromRectAndRadius(r, Radius.circular(r.height / 2)), paint);
    }
  }

  void _star(Canvas canvas, Offset c, double r) {
    final path = Path();
    for (var i = 0; i < 10; i++) {
      final radius = i.isEven ? r : r * 0.45;
      final a = -math.pi / 2 + i * math.pi / 5;
      final p = Offset(c.dx + radius * math.cos(a), c.dy + radius * math.sin(a));
      i == 0 ? path.moveTo(p.dx, p.dy) : path.lineTo(p.dx, p.dy);
    }
    path.close();
    canvas.drawPath(path, Paint()..color = Tokens.robotStar);
  }

  @override
  bool shouldRepaint(LensbotPainter old) =>
      old.colour != colour ||
      old.shape != shape ||
      old.star != star ||
      old.status != status ||
      old.shadow != shadow ||
      old.pose != pose;
}
