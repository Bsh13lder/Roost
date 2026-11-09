import 'dart:math' as math;
import 'dart:ui';

/// Owner, 2026-10-27: while a bot works, its eyes act out what it is doing
/// (web components/robot/moments.ts and styles/robot-doing.css): thinking
/// glances up with a tilt, searching scans side to side, reading sweeps along
/// lines and drops to the next, the computer looks down and taps, writing
/// follows the pen, records glance down and nod, a program whirrs.
enum RobotDoing { think, search, read, computer, write, records, program }

/// The activity pill's step kinds (run_step kinds) as what the eyes do. The one place.
const doingOfKind = <String, RobotDoing>{
  'think': RobotDoing.think,
  'other': RobotDoing.think,
  'search': RobotDoing.search,
  'read': RobotDoing.read,
  'computer': RobotDoing.computer,
  'program': RobotDoing.program,
  'file': RobotDoing.write,
  'notes': RobotDoing.write,
  'message': RobotDoing.write,
  'memory': RobotDoing.write,
  'tasks': RobotDoing.records,
  'money': RobotDoing.records,
  'calendar': RobotDoing.records,
  'bots': RobotDoing.records,
};

RobotDoing doingOf(String? kind) => doingOfKind[kind] ?? RobotDoing.think;

/// One moment of a working robot: where its pupils look (eye units, from the
/// lens centre), how its head tilts (radians), its bob and its nod (both
/// downward, in the 48-unit grid).
class LensPose {
  const LensPose({this.pupil = Offset.zero, this.tilt = 0, this.bob = 0, this.nod = 0});

  final Offset pupil;
  final double tilt;
  final double bob;
  final double nod;
}

const _bobUnits = 0.5;
const _degree = math.pi / 180;
const _scanReach = 3.6;
const _whirrRadius = 2.6;
const _whirrTurns = 3;
const _nodDepth = 1.2;
const _nodFrom = 0.6, _nodPeak = 0.7, _nodTo = 0.85;

const _readFrames = <(double, Offset)>[
  (0, Offset(-3.4, -1.6)),
  (0.4, Offset(3.4, -1.6)),
  (0.46, Offset(-3.4, 1.4)),
  (0.86, Offset(3.4, 1.4)),
  (0.92, Offset(-3.4, -1.6)),
  (1, Offset(-3.4, -1.6)),
];

const _tapFrames = <(double, Offset)>[
  (0, Offset(-1.4, 2.6)),
  (0.3, Offset(2, 2.8)),
  (0.45, Offset(2, 3.8)),
  (0.6, Offset(2, 2.8)),
  (1, Offset(-1.4, 2.6)),
];

/// The pen: small strokes left to right, low in the eye.
const _penFrames = <(double, Offset)>[
  (0, Offset(-3, 2.6)),
  (0.2, Offset(-1.5, 3.4)),
  (0.4, Offset(0, 2.4)),
  (0.6, Offset(1.5, 3.4)),
  (0.8, Offset(3, 2.6)),
  (1, Offset(-3, 2.6)),
];

const _glanceFrames = <(double, Offset)>[
  (0, Offset.zero),
  (0.25, Offset(0.8, 3)),
  (0.55, Offset(0.8, 3)),
  (0.7, Offset(0, -0.6)),
  (1, Offset.zero),
];

/// The pose at [t] (0..1) of one cycle.
LensPose poseFor(RobotDoing doing, double t) {
  final wave = math.sin(2 * math.pi * t);
  final bob = _bobUnits * wave;
  switch (doing) {
    case RobotDoing.think:
      return LensPose(
        pupil: Offset(1.2 * wave, -3.2 + 0.4 * math.sin(4 * math.pi * t)),
        tilt: (-0.5 + 2.5 * wave) * _degree,
        bob: bob,
      );
    case RobotDoing.search:
      return LensPose(
        pupil: Offset(-_scanReach * math.cos(4 * math.pi * t), -0.3),
        tilt: 2 * wave * _degree,
        bob: bob,
      );
    case RobotDoing.read:
      return LensPose(pupil: _keyed(_readFrames, t), tilt: wave * _degree, bob: bob);
    case RobotDoing.computer:
      return LensPose(pupil: _keyed(_tapFrames, t), bob: bob);
    case RobotDoing.write:
      return LensPose(pupil: _keyed(_penFrames, t), tilt: wave * _degree, bob: bob);
    case RobotDoing.records:
      return LensPose(pupil: _keyed(_glanceFrames, t), bob: bob, nod: _nod(t));
    case RobotDoing.program:
      final a = 2 * math.pi * _whirrTurns * t;
      return LensPose(
        pupil: Offset(_whirrRadius * math.cos(a), _whirrRadius * math.sin(a)),
        bob: bob,
      );
  }
}

/// With less motion: the kind's look, standing still.
LensPose stillPose(RobotDoing doing) => LensPose(
      pupil: switch (doing) {
        RobotDoing.think => const Offset(0, -2.6),
        RobotDoing.read => const Offset(-1.5, -1),
        RobotDoing.computer || RobotDoing.write => const Offset(0, 2.8),
        RobotDoing.records => const Offset(0, 2.4),
        RobotDoing.search || RobotDoing.program => Offset.zero,
      },
    );

double _nod(double t) {
  if (t <= _nodFrom || t >= _nodTo) return 0;
  final up = t <= _nodPeak;
  final f = up ? (t - _nodFrom) / (_nodPeak - _nodFrom) : (_nodTo - t) / (_nodTo - _nodPeak);
  return _nodDepth * f;
}

/// Straight lines between key frames (sorted by time, from 0 to 1).
Offset _keyed(List<(double, Offset)> frames, double t) {
  for (var i = 1; i < frames.length; i++) {
    final (t1, b) = frames[i];
    if (t <= t1) {
      final (t0, a) = frames[i - 1];
      final span = t1 - t0;
      return span <= 0 ? b : Offset.lerp(a, b, (t - t0) / span)!;
    }
  }
  return frames.last.$2;
}
