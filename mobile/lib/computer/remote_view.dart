import 'package:flutter/material.dart';

import '../theme/accent.dart';
import 'rfb_codec.dart';
import 'rfb_session.dart';
import 'touch_interpreter.dart';
import 'view_math.dart';

const ringDuration = Duration(milliseconds: 900);
const ringSize = 44.0;

/// Where the bot just clicked, in remote screen pixels; [n] counts them.
class RingMark {
  const RingMark(this.pixel, this.n);
  final Offset pixel;
  final int n;
}

class _ScreenPainter extends CustomPainter {
  _ScreenPainter(this.session, this.view) : super(repaint: session);
  final RfbSession session;
  final ScreenView view;

  @override
  void paint(Canvas canvas, Size size) {
    final image = session.image;
    if (image == null) return;
    final box = ScreenView.fit(size, session.screenSize);
    canvas.save();
    canvas.translate(view.offset.dx, view.offset.dy);
    canvas.scale(view.scale);
    canvas.drawImageRect(
      image,
      Rect.fromLTWH(0, 0, image.width.toDouble(), image.height.toDouble()),
      box,
      Paint()..filterQuality = FilterQuality.medium,
    );
    canvas.restore();
  }

  @override
  bool shouldRepaint(_ScreenPainter old) =>
      old.view.scale != view.scale || old.view.offset != view.offset;
}

/// The remote screen, letterboxed, with touch input while [controlling].
/// Not controlling, one finger moving or two fingers pan a zoomed screen and
/// nothing is ever sent.
class RemoteView extends StatefulWidget {
  const RemoteView(
      {super.key,
      required this.session,
      required this.controlling,
      this.ring,
      this.trackpad = false});

  final RfbSession session;

  /// Trackpad mode: one finger moves a pointer, a tap clicks where it is.
  final bool trackpad;
  final bool controlling;
  final RingMark? ring;

  @override
  State<RemoteView> createState() => _RemoteViewState();
}

class _RemoteViewState extends State<RemoteView>
    with SingleTickerProviderStateMixin
    implements TouchActions {
  ScreenView _view = const ScreenView();
  Size _viewport = Size.zero;
  late final TouchInterpreter _touch =
      TouchInterpreter(this, zoomed: () => _view.zoomed);
  late final AnimationController _ring;
  final Stopwatch _clock = Stopwatch()..start();

  @override
  void initState() {
    super.initState();
    // Made here, not lazily: a lazy one would first be made in dispose, when
    // looking up the ticker mode is no longer allowed.
    _ring = AnimationController(vsync: this, duration: ringDuration);
  }

  @override
  void didUpdateWidget(RemoteView old) {
    super.didUpdateWidget(old);
    if (widget.ring != null && widget.ring?.n != old.ring?.n) {
      _ring.forward(from: 0);
    }
  }

  @override
  void dispose() {
    _touch.dispose();
    _ring.dispose();
    super.dispose();
  }

  /// The trackpad pointer, in viewport points.
  Offset? _cursor;
  Offset? _padFrom;

  Offset _cursorNow() =>
      _cursor ??= Offset(_viewport.width / 2, _viewport.height / 2);

  bool get _pad => widget.trackpad && widget.controlling;

  Offset? _remote(Offset p) =>
      _view.toScreen(p, _viewport, widget.session.screenSize);

  void _send(int buttons, Offset viewportPoint) {
    if (!widget.controlling) return;
    final r = _remote(viewportPoint);
    if (r == null) return;
    widget.session.pointer(buttons, r.dx.round(), r.dy.round());
  }

  @override
  void tap(Offset at) {
    if (_pad) at = _cursorNow();
    _send(0, at);
    _send(buttonLeft, at);
    _send(0, at);
  }

  @override
  void rightClick(Offset at) {
    if (_pad) at = _cursorNow();
    _send(0, at);
    _send(buttonRight, at);
    _send(0, at);
  }

  @override
  void dragStart(Offset at) {
    if (_pad) {
      _padFrom = at;
      return;
    }
    if (widget.controlling) {
      _send(0, at);
      _send(buttonLeft, at);
    } else {
      _dragPan = true;
    }
  }

  bool _dragPan = false;
  Offset? _panFrom;

  @override
  void dragMove(Offset at) {
    if (_pad) {
      final from = _padFrom ?? at;
      final moved = _cursorNow() + (at - from);
      _padFrom = at;
      setState(() => _cursor = Offset(
          moved.dx.clamp(0.0, _viewport.width), moved.dy.clamp(0.0, _viewport.height)));
      _send(0, _cursor!);
      return;
    }
    if (widget.controlling) {
      _send(buttonLeft, at);
    } else if (_dragPan && _view.zoomed) {
      final from = _panFrom ?? at;
      setState(() => _view = _view.panBy(at - from, _viewport));
      _panFrom = at;
    } else {
      _panFrom = at;
    }
  }

  @override
  void dragEnd(Offset at) {
    if (_pad) {
      _padFrom = null;
      return;
    }
    if (widget.controlling) {
      final r = _remote(at);
      if (r == null) {
        widget.session.pointer(0, 0, 0);
      } else {
        _send(0, at);
      }
    }
    _dragPan = false;
    _panFrom = null;
  }

  @override
  void scroll(Offset at, int ticks) {
    if (!widget.controlling) return;
    if (_pad) at = _cursorNow();
    final button = ticks < 0 ? buttonWheelUp : buttonWheelDown;
    for (var i = 0; i < ticks.abs(); i++) {
      _send(button, at);
      _send(0, at);
    }
  }

  @override
  void pinch(double factor, Offset focal) =>
      setState(() => _view = _view.zoomAbout(factor, focal, _viewport));

  @override
  void pan(Offset delta) =>
      setState(() => _view = _view.panBy(delta, _viewport));

  Duration get _now => _clock.elapsed;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(builder: (context, box) {
      _viewport = box.biggest;
      final session = widget.session;
      return Listener(
        behavior: HitTestBehavior.opaque,
        onPointerDown: (e) => _touch.down(e.pointer, e.localPosition, _now),
        onPointerMove: (e) => _touch.move(e.pointer, e.localPosition),
        onPointerUp: (e) => _touch.up(e.pointer, e.localPosition, _now),
        onPointerCancel: (e) => _touch.cancel(),
        child: ClipRect(
          child: Stack(children: [
            Positioned.fill(
              child: ColoredBox(
                color: Colors.black,
                child: CustomPaint(painter: _ScreenPainter(session, _view)),
              ),
            ),
            if (_pad)
              Positioned(
                left: _cursorNow().dx - 6,
                top: _cursorNow().dy - 6,
                child: IgnorePointer(
                  child: Icon(Icons.near_me, size: 18, color: AccentColors.of(context).soft),
                ),
              ),
            if (widget.ring != null)
              AnimatedBuilder(
                animation: _ring,
                builder: (context, _) => _RingLayer(
                  progress: _ring.value,
                  at: _view.fromScreen(
                      widget.ring!.pixel, _viewport, session.screenSize),
                ),
              ),
          ]),
        ),
      );
    });
  }
}

class _RingLayer extends StatelessWidget {
  const _RingLayer({required this.progress, required this.at});
  final double progress;
  final Offset at;

  @override
  Widget build(BuildContext context) {
    if (progress <= 0 || progress >= 1) return const SizedBox.shrink();
    final size = ringSize * (0.6 + 0.8 * progress);
    return Positioned(
      left: at.dx - size / 2,
      top: at.dy - size / 2,
      width: size,
      height: size,
      child: IgnorePointer(
        child: DecoratedBox(
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            border: Border.all(
                color: AccentColors.of(context).soft.withValues(alpha: 1 - progress),
                width: 3),
          ),
        ),
      ),
    );
  }
}
