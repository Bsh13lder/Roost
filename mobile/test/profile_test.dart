import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/api/models.dart';
import 'package:roost_mobile/profile/model_picker.dart';
import 'package:roost_mobile/widgets/lens_specs.dart';
import 'package:roost_mobile/widgets/lensbot.dart';

void main() {
  testWidgets('the Model picker lists four models', (tester) async {
    final models = ModelsOut.fromJson({
      'choices': [
        {'id': 'claude-fable-5-1', 'label': 'Fable 5.1', 'new': false},
        {'id': 'claude-sonnet-5-5', 'label': 'Sonnet 5.5', 'new': false},
        {'id': 'claude-opus-5-5', 'label': 'Opus 5.5', 'new': false},
        {'id': 'claude-haiku-5-5', 'label': 'Haiku 5.5', 'new': false},
      ],
      'efforts': ['low', 'medium', 'high', 'max'],
      'default_effort': <String, String>{},
    });
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: ModelList(choices: models.choices, current: 'claude-sonnet-5-5'),
      ),
    ));
    expect(find.byType(ListTile), findsNWidgets(4));
    for (final label in ['Fable 5.1', 'Sonnet 5.5', 'Opus 5.5', 'Haiku 5.5']) {
      expect(find.text(label), findsOneWidget);
    }
  });

  test('the painter draws every shape name, old and new, without throwing', () {
    final names = [...lensbotShapes, ...legacyShapeToLensbot.keys, 'unknown'];
    expect(lensbotShapes, hasLength(18));
    for (final shape in names) {
      for (final status in [BotStatus.resting, BotStatus.offDuty]) {
        final recorder = ui.PictureRecorder();
        final canvas = Canvas(recorder);
        LensbotPainter(const Color(0xFF8B5CF6),
                shape: shape, star: true, status: status)
            .paint(canvas, const Size(96, 96));
        recorder.endRecording().dispose();
      }
    }
  });
}
