// Draws Roost's launcher and notification icons from the app's own Lensbot:
// Gela's look (owner, 2026-10-23: "I like Gela's icon, make the main logo
// that"). Skipped in normal runs; to redraw them, from mobile/:
//
//   MAKE_ROOST_ICONS=1 flutter test test/tool/make_icons_test.dart
//
// It writes the legacy launcher PNGs (mipmap-*/ic_launcher.png), the adaptive
// icon's foreground PNGs (drawable-*/ic_launcher_foreground.png) and the
// white notification silhouette (drawable/ic_stat_roost.xml), and copies
// previews to ROOST_ICON_PREVIEW_DIR when it is set.
import 'dart:io';
import 'dart:math' as math;
import 'dart:ui';

import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/theme/tokens.dart';
import 'package:roost_mobile/widgets/lens_geometry.dart';
import 'package:roost_mobile/widgets/lens_specs.dart';
import 'package:roost_mobile/widgets/lensbot_png.dart';

const logoShape = 'cheeky';
const logoColour = Color(0xFF8B5CF6);
const res = 'android/app/src/main/res';

/// Legacy icons: the whole square shows; a rounded dark tile.
const legacy = {'mdpi': 48, 'hdpi': 72, 'xhdpi': 96, 'xxhdpi': 144, 'xxxhdpi': 192};

/// Adaptive foreground: 108 dp a side; the launcher's mask shows the middle 72
/// and the content stays inside the 66 dp safe circle.
const adaptiveDensity = {'mdpi': 1.0, 'hdpi': 1.5, 'xhdpi': 2.0, 'xxhdpi': 3.0, 'xxxhdpi': 4.0};
const adaptiveFill = 52 / 108;

String _n(double v) => v.toStringAsFixed(2).replaceFirst(RegExp(r'\.?0+$'), '');

String _circle(Offset c, double r) =>
    'M${_n(c.dx - r)},${_n(c.dy)} a${_n(r)},${_n(r)} 0 1,0 ${_n(2 * r)},0 a${_n(r)},${_n(r)} 0 1,0 ${_n(-2 * r)},0 Z';

String _pill(Rect r) {
  final rad = r.height / 2;
  return 'M${_n(r.left + rad)},${_n(r.top)} H${_n(r.right - rad)} '
      'A${_n(rad)},${_n(rad)} 0 0 1 ${_n(r.right - rad)},${_n(r.bottom)} '
      'H${_n(r.left + rad)} A${_n(rad)},${_n(rad)} 0 0 1 ${_n(r.left + rad)},${_n(r.top)} Z';
}

/// The Lensbot as a white silhouette on the 48-unit grid: the body with its
/// visor cut out, the two lens eyes inside, their pupils cut out.
String statIconXml() {
  final g = lensGeometry(lensSpec(logoShape));
  final box = lensbotBounds(logoShape);
  final s = 44 / math.max(box.width, box.height);
  Offset at(Offset p) => Offset(24 + (p.dx - box.center.dx) * s, 24 + (p.dy - box.center.dy) * s);
  final pts = g.pts.map(at).toList();
  final n = pts.length;
  Offset p(int i) => pts[(i + n) % n];
  final body = StringBuffer('M${_n(pts[0].dx)},${_n(pts[0].dy)}');
  for (var i = 0; i < n; i++) {
    final p0 = p(i - 1), p1 = p(i), p2 = p(i + 1), p3 = p(i + 2);
    body.write(' C${_n(p1.dx + (p2.dx - p0.dx) / 6)},${_n(p1.dy + (p2.dy - p0.dy) / 6)} '
        '${_n(p2.dx - (p3.dx - p1.dx) / 6)},${_n(p2.dy - (p3.dy - p1.dy) / 6)} ${_n(p2.dx)},${_n(p2.dy)}');
  }
  body.write(' Z');
  final v = g.visorRect;
  final visor = Rect.fromPoints(at(v.topLeft), at(v.bottomRight));
  final eyes = StringBuffer();
  for (final x in g.eyeX) {
    final c = at(Offset(x, g.eyeY));
    eyes.write('${_circle(c, 10 * g.k * s)} ');
    eyes.write('${_circle(c + Offset(1 * g.k * s, 0.8 * g.k * s), 4.4 * g.k * s)} ');
  }
  return '''<?xml version="1.0" encoding="utf-8"?>
<!-- Roost's notification icon: Gela's Lensbot (cheeky) as a white silhouette, its visor cut out and its two
     lens eyes inside. Android draws a notification's small icon from alpha alone. Drawn by
     test/tool/make_icons_test.dart from the app's own Lensbot geometry. -->
<vector xmlns:android="http://schemas.android.com/apk/res/android"
    android:width="24dp"
    android:height="24dp"
    android:viewportWidth="48"
    android:viewportHeight="48">
    <path
        android:fillColor="#FFFFFFFF"
        android:fillType="evenOdd"
        android:pathData="$body ${_pill(visor)}" />
    <path
        android:fillColor="#FFFFFFFF"
        android:fillType="evenOdd"
        android:pathData="${eyes.toString().trim()}" />
</vector>
''';
}

Future<void> _write(String path, List<int> bytes, String? preview) async {
  File(path)
    ..parent.createSync(recursive: true)
    ..writeAsBytesSync(bytes);
  if (preview != null) {
    File('$preview/${path.split('/res/').last.replaceAll('/', '_')}')
      ..parent.createSync(recursive: true)
      ..writeAsBytesSync(bytes);
  }
}

void main() {
  final on = Platform.environment['MAKE_ROOST_ICONS'] == '1';
  final preview = Platform.environment['ROOST_ICON_PREVIEW_DIR'];

  testWidgets('draw the launcher and notification icons', (tester) async {
    await tester.runAsync(() async {
      for (final MapEntry(key: dpi, value: px) in legacy.entries) {
        final png = await lensbotPng(colour: logoColour, shape: logoShape, size: px,
            background: Tokens.bg, fill: 0.72, corner: 0.22);
        await _write('$res/mipmap-$dpi/ic_launcher.png', png, preview);
      }
      for (final MapEntry(key: dpi, value: d) in adaptiveDensity.entries) {
        final png = await lensbotPng(
            colour: logoColour, shape: logoShape, size: (108 * d).round(), fill: adaptiveFill);
        await _write('$res/drawable-$dpi/ic_launcher_foreground.png', png, preview);
      }
      final big = await lensbotPng(colour: logoColour, shape: logoShape, size: 512,
          background: Tokens.bg, fill: 0.72, corner: 0.22);
      if (preview != null) await _write('$preview/logo-512.png', big, null);
    });
    final xml = statIconXml();
    File('$res/drawable/ic_stat_roost.xml').writeAsStringSync(xml);
    if (preview != null) File('$preview/ic_stat_roost.xml').writeAsStringSync(xml);
  }, skip: !on);
}
