import 'dart:math';

import 'package:flutter/material.dart';

import '../theme/accent.dart';
import 'call_controller.dart';

/// The call's orb: grows with your voice while it listens, breathes while it
/// thinks, sends out rings while it speaks. Still when motion is reduced.
class CallOrb extends StatefulWidget {
  const CallOrb({super.key, required this.phase, required this.level, required this.child});

  final CallPhase phase;
  final double level;
  final Widget child;

  static const size = 220.0;

  @override
  State<CallOrb> createState() => _CallOrbState();
}

class _CallOrbState extends State<CallOrb> with SingleTickerProviderStateMixin {
  late final AnimationController _t =
      AnimationController(vsync: this, duration: const Duration(milliseconds: 1800))..repeat();

  @override
  void dispose() {
    _t.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final still = MediaQuery.maybeDisableAnimationsOf(context) ?? false;
    final accent = AccentColors.of(context);
    return SizedBox.square(
      dimension: CallOrb.size,
      child: AnimatedBuilder(
        animation: _t,
        builder: (_, child) => CustomPaint(
          painter: _OrbPainter(
            phase: widget.phase,
            level: widget.level,
            t: still ? 0 : _t.value,
            fill: accent.accent,
            glow: accent.soft,
          ),
          child: child,
        ),
        child: Center(child: widget.child),
      ),
    );
  }
}

class _OrbPainter extends CustomPainter {
  _OrbPainter({required this.phase, required this.level, required this.t, required this.fill, required this.glow});

  final CallPhase phase;
  final double level;
  final double t;
  final Color fill;
  final Color glow;

  static const _core = 0.30;
  static const _alive = {CallPhase.listening, CallPhase.hearing, CallPhase.thinking, CallPhase.speaking, CallPhase.asking};

  @override
  void paint(Canvas canvas, Size size) {
    final c = size.center(Offset.zero);
    final r = size.shortestSide / 2;
    final wave = sin(t * 2 * pi);
    final grow = switch (phase) {
      CallPhase.listening => 1 + level * 0.35,
      CallPhase.thinking || CallPhase.hearing => 1 + wave * 0.05,
      CallPhase.speaking => 1.05 + wave * 0.03,
      _ => 1.0,
    };
    if (phase == CallPhase.speaking) {
      for (var i = 0; i < 3; i++) {
        final p = (t + i / 3) % 1;
        canvas.drawCircle(c, r * _core * (1.4 + p * 1.8),
            Paint()..color = glow.withValues(alpha: (1 - p) * 0.25)..style = PaintingStyle.stroke..strokeWidth = 2);
      }
    }
    final opacity = _alive.contains(phase) ? 1.0 : 0.4;
    canvas.drawCircle(c, r * _core * 1.6 * grow, Paint()..color = fill.withValues(alpha: 0.18 * opacity));
    canvas.drawCircle(c, r * _core * 1.3 * grow, Paint()..color = fill.withValues(alpha: 0.35 * opacity));
  }

  @override
  bool shouldRepaint(_OrbPainter old) =>
      old.t != t || old.level != level || old.phase != phase || old.fill != fill;
}
