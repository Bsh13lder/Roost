import 'package:flutter/material.dart';

import '../../theme/tokens.dart';

/// Calm motion for the computer card. Every piece stands still when the
/// phone asks for less motion.
const cardMotion = Duration(milliseconds: 280);
const _shimmerPeriod = Duration(milliseconds: 1600);

bool reduceMotion(BuildContext context) =>
    MediaQuery.maybeDisableAnimationsOf(context) ?? false;

/// [base] when motion is on, else no time at all.
Duration motion(BuildContext context, [Duration base = cardMotion]) =>
    reduceMotion(context) ? Duration.zero : base;

/// A soft light that sweeps across [child] while [active].
class Shimmer extends StatefulWidget {
  const Shimmer({super.key, required this.child, this.active = true});

  final Widget child;
  final bool active;

  @override
  State<Shimmer> createState() => _ShimmerState();
}

class _ShimmerState extends State<Shimmer> with SingleTickerProviderStateMixin {
  late final AnimationController _c = AnimationController(
    vsync: this,
    duration: _shimmerPeriod,
  );

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _sync();
  }

  @override
  void didUpdateWidget(Shimmer old) {
    super.didUpdateWidget(old);
    _sync();
  }

  void _sync() {
    final run = widget.active && !reduceMotion(context);
    if (run && !_c.isAnimating) _c.repeat();
    if (!run && _c.isAnimating) _c.stop();
  }

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.active || reduceMotion(context)) return widget.child;
    return AnimatedBuilder(
      animation: _c,
      child: widget.child,
      builder: (_, child) => ShaderMask(
        blendMode: BlendMode.srcATop,
        shaderCallback: (rect) {
          final x = -1.0 + 3.0 * _c.value;
          return LinearGradient(
            begin: Alignment(x - 1, 0),
            end: Alignment(x, 0),
            colors: const [
              Tokens.shimmerClear,
              Tokens.shimmerLight,
              Tokens.shimmerClear,
            ],
          ).createShader(rect);
        },
        child: child,
      ),
    );
  }
}
