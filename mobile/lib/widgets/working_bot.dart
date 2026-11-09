import 'package:flutter/material.dart';

import '../api/models.dart';
import 'lens_doing.dart';
import 'lensbot.dart';

/// A working bot's robot in its chat: just large enough for its eyes to read.
const workingBotSize = 32.0;

/// One cycle of the work's motion (a scan, a line read, a pen stroke).
const workingBotCycle = Duration(milliseconds: 2400);

/// A working bot in its chat (owner, 2026-10-27, like Grok's moving mark): its
/// own Lensbot, its head bobbing gently, its eyes acting out what it is doing
/// ([doingOf] the running step's kind). One controller, stopped and still when
/// the phone asks for less motion. Its words sit beside it, so it is decorative.
class WorkingBot extends StatefulWidget {
  const WorkingBot({super.key, required this.avatar, this.kind, this.size = workingBotSize, this.star = false});

  final Avatar avatar;

  /// The running step's kind (run_step kinds); none is thinking.
  final String? kind;
  final double size;
  final bool star;

  @override
  State<WorkingBot> createState() => _WorkingBotState();
}

class _WorkingBotState extends State<WorkingBot> with SingleTickerProviderStateMixin {
  late final AnimationController _c = AnimationController(vsync: this, duration: workingBotCycle);

  bool get _still => MediaQuery.maybeDisableAnimationsOf(context) ?? false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_still) {
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

  Widget _paint(LensPose pose) => CustomPaint(
        size: Size.square(widget.size),
        painter: LensbotPainter(
          widget.avatar.colour,
          shape: widget.avatar.shape,
          star: widget.star,
          status: BotStatus.onIt,
          pose: pose,
        ),
      );

  @override
  Widget build(BuildContext context) {
    final doing = doingOf(widget.kind);
    return ExcludeSemantics(
      child: SizedBox.square(
        key: const Key('working-bot'),
        dimension: widget.size,
        child: _still
            ? _paint(stillPose(doing))
            : AnimatedBuilder(animation: _c, builder: (_, _) => _paint(poseFor(doing, _c.value))),
      ),
    );
  }
}
