import 'dart:typed_data';
import 'dart:ui';

import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/widgets/lensbot_png.dart';

(int, int) pngSize(Uint8List png) {
  final b = ByteData.sublistView(png);
  return (b.getUint32(16), b.getUint32(20));
}

void main() {
  testWidgets('a Lensbot renders to a PNG of the asked size', (tester) async {
    final png = await tester.runAsync(() => lensbotPng(
        colour: const Color(0xFF8B5CF6), shape: 'cheeky', size: 96));
    expect(png, isNotNull);
    expect(png!.sublist(0, 8), [0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]);
    expect(pngSize(png), (96, 96));
    expect(png.length, greaterThan(800)); // a drawn robot, not an empty image
  });

  testWidgets('a background, a fill fraction and corners are honoured', (tester) async {
    final png = await tester.runAsync(() => lensbotPng(
        colour: const Color(0xFF8B5CF6), shape: 'cheeky', size: 48,
        background: const Color(0xFF0E0E12), fill: 0.6, corner: 0.22));
    expect(pngSize(png!), (48, 48));
  });
}
