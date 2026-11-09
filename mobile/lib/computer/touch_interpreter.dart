import 'dart:async';
import 'dart:math' as math;
import 'dart:ui';

const touchSlop = 10.0;
const longPressAfter = Duration(milliseconds: 500);
const twoFingerTapMax = Duration(milliseconds: 300);
const scrollTickPx = 36.0;

/// What a touch means on the remote screen. All points are viewport points.
abstract class TouchActions {
  void tap(Offset at);
  void rightClick(Offset at);
  void dragStart(Offset at);
  void dragMove(Offset at);
  void dragEnd(Offset at);

  /// Wheel ticks at a point: negative scrolls up, positive scrolls down.
  void scroll(Offset at, int ticks);
  void pinch(double factor, Offset focal);
  void pan(Offset delta);
}

enum _Mode { none, single, drag, twoUndecided, pinch, scroll, spent }

/// Turns raw pointers into the gestures the Help sheet describes: tap is a
/// click, long-press or a two-finger tap is a right-click, one finger moving
/// drags, two fingers moving scroll (or pan when zoomed), pinch zooms.
class TouchInterpreter {
  TouchInterpreter(this.actions, {required this.zoomed});

  final TouchActions actions;

  /// Read on each gesture: two fingers pan instead of scroll while zoomed.
  bool Function() zoomed;

  final Map<int, Offset> _at = {};
  final Map<int, Offset> _start = {};
  _Mode _mode = _Mode.none;
  Timer? _hold;
  Duration _twoDownAt = Duration.zero;
  double _lastSpread = 0;
  Offset _lastCentre = Offset.zero;
  double _scrollCarry = 0;
  double _startSpread = 0;

  void down(int id, Offset p, Duration t) {
    _at[id] = p;
    _start[id] = p;
    if (_at.length == 1) {
      _mode = _Mode.single;
      _hold?.cancel();
      _hold = Timer(longPressAfter, () {
        if (_mode == _Mode.single) {
          _mode = _Mode.spent;
          actions.rightClick(_at.values.first);
        }
      });
    } else if (_at.length == 2) {
      _hold?.cancel();
      if (_mode == _Mode.drag) actions.dragEnd(_centreOf(_at.values.first));
      _mode = _Mode.twoUndecided;
      _twoDownAt = t;
      _startSpread = _spread();
      _lastSpread = _startSpread;
      _lastCentre = _centre();
      _scrollCarry = 0;
    } else {
      _mode = _Mode.spent;
    }
  }

  void move(int id, Offset p) {
    if (!_at.containsKey(id)) return;
    _at[id] = p;
    switch (_mode) {
      case _Mode.single:
        if ((p - _start[id]!).distance > touchSlop) {
          _hold?.cancel();
          _mode = _Mode.drag;
          actions.dragStart(_start[id]!);
          actions.dragMove(p);
        }
      case _Mode.drag:
        actions.dragMove(p);
      case _Mode.twoUndecided:
        _decide();
      case _Mode.pinch:
        _pinch();
      case _Mode.scroll:
        _scroll();
      case _Mode.none || _Mode.spent:
        break;
    }
  }

  void up(int id, Offset p, Duration t) {
    if (!_at.containsKey(id)) return;
    _at[id] = p;
    final mode = _mode;
    final wasTwo = _at.length == 2;
    if (mode == _Mode.single) {
      _hold?.cancel();
      actions.tap(p);
    } else if (mode == _Mode.drag) {
      actions.dragEnd(p);
    } else if (mode == _Mode.twoUndecided && wasTwo) {
      if (t - _twoDownAt <= twoFingerTapMax) actions.rightClick(_centre());
    }
    _at.remove(id);
    _start.remove(id);
    _mode = _at.isEmpty ? _Mode.none : _Mode.spent;
  }

  void cancel() {
    _hold?.cancel();
    if (_mode == _Mode.drag && _at.isNotEmpty) actions.dragEnd(_at.values.first);
    _at.clear();
    _start.clear();
    _mode = _Mode.none;
  }

  Offset _centre() {
    final pts = _at.values.take(2).toList();
    return (pts[0] + pts[1]) / 2;
  }

  Offset _centreOf(Offset p) => p;

  double _spread() {
    final pts = _at.values.take(2).toList();
    return (pts[0] - pts[1]).distance;
  }

  void _decide() {
    final spreadMove = (_spread() - _startSpread).abs();
    final centreMove = (_centre() - _lastCentre).distance;
    if (math.max(spreadMove, centreMove) < touchSlop) return;
    _mode = spreadMove > centreMove ? _Mode.pinch : _Mode.scroll;
    _lastSpread = _spread();
    _lastCentre = _centre();
  }

  void _pinch() {
    final s = _spread();
    if (_lastSpread > 0 && s > 0) actions.pinch(s / _lastSpread, _centre());
    _lastSpread = s;
    _lastCentre = _centre();
  }

  void _scroll() {
    final c = _centre();
    final delta = c - _lastCentre;
    _lastCentre = c;
    if (zoomed()) {
      actions.pan(delta);
      return;
    }
    // Fingers moving up read lower on the page: wheel down.
    _scrollCarry -= delta.dy;
    final ticks = (_scrollCarry / scrollTickPx).truncate();
    if (ticks != 0) {
      _scrollCarry -= ticks * scrollTickPx;
      actions.scroll(c, ticks);
    }
  }

  void dispose() => _hold?.cancel();
}
