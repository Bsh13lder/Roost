import 'dart:math' as math;

import 'package:flutter/material.dart';

import 'computer_motion.dart';

/// The still icon for a step's kind (the steps sheet, the finished line).
IconData activityIcon(String kind) => switch (kind) {
      'think' => Icons.more_horiz_rounded,
      'search' => Icons.travel_explore_rounded,
      'read' => Icons.public_rounded,
      'computer' => Icons.ads_click_rounded,
      'program' => Icons.settings_rounded,
      'file' => Icons.description_outlined,
      'tasks' => Icons.check_circle_outline_rounded,
      'notes' => Icons.edit_note_rounded,
      'money' => Icons.payments_outlined,
      'calendar' => Icons.event_outlined,
      'bots' => Icons.forum_outlined,
      'memory' => Icons.psychology_outlined,
      'message' => Icons.edit_rounded,
      'note' => Icons.chat_bubble_outline_rounded,
      'approved' => Icons.thumb_up_alt_outlined,
      'declined' => Icons.do_not_disturb_on_outlined,
      _ => Icons.bolt_rounded,
    };

enum _Motion { spin, slowSpin, tick, wiggle, breathe }

_Motion _motionFor(String kind) => switch (kind) {
      'search' || 'read' => _Motion.slowSpin,
      'program' => _Motion.spin,
      'computer' => _Motion.tick,
      'file' || 'notes' || 'message' || 'tasks' => _Motion.wiggle,
      _ => _Motion.breathe,
    };

/// The pill's icon, moving calmly in its own way: a globe turning while it
/// browses, a gear while a program runs, a cursor tick on the computer, a pen
/// that writes, three dots that think. Still when the phone asks for less motion.
class ActivityIcon extends StatefulWidget {
  const ActivityIcon({super.key, required this.kind, required this.color, this.size = 16});

  final String kind;
  final Color color;
  final double size;

  @override
  State<ActivityIcon> createState() => _ActivityIconState();
}

class _ActivityIconState extends State<ActivityIcon> with SingleTickerProviderStateMixin {
  late final AnimationController _c = AnimationController(vsync: this);

  Duration get _period => switch (_motionFor(widget.kind)) {
        _Motion.slowSpin => const Duration(milliseconds: 6000),
        _Motion.spin => const Duration(milliseconds: 3200),
        _Motion.tick => const Duration(milliseconds: 1400),
        _Motion.wiggle => const Duration(milliseconds: 900),
        _Motion.breathe => const Duration(milliseconds: 1600),
      };

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _sync();
  }

  @override
  void didUpdateWidget(ActivityIcon old) {
    super.didUpdateWidget(old);
    if (old.kind != widget.kind) {
      _c.stop();
      _sync();
    }
  }

  void _sync() {
    if (reduceMotion(context)) {
      _c.stop();
      return;
    }
    _c.duration = _period;
    if (!_c.isAnimating) _c.repeat();
  }

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (widget.kind == 'think') {
      return ThinkingDots(color: widget.color, size: widget.size);
    }
    final icon = Icon(activityIcon(widget.kind), size: widget.size, color: widget.color);
    if (reduceMotion(context)) return icon;
    final motion = _motionFor(widget.kind);
    return AnimatedBuilder(
      animation: _c,
      child: icon,
      builder: (_, child) {
        final t = _c.value;
        return switch (motion) {
          _Motion.spin || _Motion.slowSpin =>
            Transform.rotate(angle: t * 2 * math.pi, child: child),
          _Motion.tick => Transform.scale(
              scale: 1 - 0.18 * math.max(0, math.sin(t * 2 * math.pi * 1.0)), child: child),
          _Motion.wiggle => Transform.translate(
              offset: Offset(1.2 * math.sin(t * 2 * math.pi), 0),
              child: Transform.rotate(angle: 0.14 * math.sin(t * 2 * math.pi), child: child)),
          _Motion.breathe =>
            Opacity(opacity: 0.6 + 0.4 * (0.5 + 0.5 * math.sin(t * 2 * math.pi)), child: child),
        };
      },
    );
  }
}

/// Three dots that rise in turn while the bot thinks.
class ThinkingDots extends StatefulWidget {
  const ThinkingDots({super.key, required this.color, this.size = 16});

  final Color color;
  final double size;

  @override
  State<ThinkingDots> createState() => _ThinkingDotsState();
}

class _ThinkingDotsState extends State<ThinkingDots> with SingleTickerProviderStateMixin {
  late final AnimationController _c =
      AnimationController(vsync: this, duration: const Duration(milliseconds: 1200));

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (reduceMotion(context)) {
      _c.stop();
    } else if (!_c.isAnimating) {
      _c.repeat();
    }
  }

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final dot = widget.size / 5;
    Widget row(double t) => Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            for (var i = 0; i < 3; i++) ...[
              if (i > 0) SizedBox(width: dot * 0.6),
              Transform.translate(
                offset: Offset(0, -dot * 0.9 * _lift(t, i)),
                child: Opacity(
                  opacity: 0.6 + 0.4 * _lift(t, i),
                  child: Container(
                    width: dot,
                    height: dot,
                    decoration: BoxDecoration(color: widget.color, shape: BoxShape.circle),
                  ),
                ),
              ),
            ],
          ],
        );
    return SizedBox(
      width: widget.size,
      height: widget.size,
      child: Center(
        child: reduceMotion(context)
            ? row(0.25)
            : AnimatedBuilder(animation: _c, builder: (_, _) => row(_c.value)),
      ),
    );
  }

  /// 0..1: how high dot [i] is at time [t] (each starts a third later).
  static double _lift(double t, int i) {
    final phase = (t - i / 6) % 1.0;
    return phase < 0.5 ? math.sin(phase * 2 * math.pi).clamp(0.0, 1.0) : 0.0;
  }
}
