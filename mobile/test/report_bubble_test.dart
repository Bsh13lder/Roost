import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/chat/cards/card_base.dart';
import 'package:roost_mobile/chat/cards/report_bubble.dart';
import 'package:roost_mobile/routines/next_run.dart';

import 'cards_test.dart' show cardMessage, pumpCard;
import 'fake_adapter.dart';

/// Owner, 2026-10-26: a Report is the bot's own message, like Grok's, with a
/// quiet footer; a routine list says when it runs next in words.
void main() {
  Map<String, dynamic> routineReport([Map<String, dynamic> over = const {}]) => {
        'source': 'routine',
        'headline': 'Only the server keeps this',
        'text': 'Three **new** emails.',
        'routine_id': 'r-1',
        'run_id': 'run-1',
        'log_thread_id': 't-log',
        'tainted': false,
        'routine_name': 'Morning digest',
        ...over,
      };

  testWidgets('a routine Report is a bubble with a quiet footer, no headline, no card',
      (tester) async {
    await pumpCard(tester, cardMessage('report', jsonEncode(routineReport())),
        (_) => FakeAdapter.json({}));
    expect(find.byType(ReportBubble), findsOneWidget);
    expect(find.byType(CardFrame), findsNothing);
    expect(find.textContaining('Only the server keeps this'), findsNothing);
    expect(find.textContaining('Report:'), findsNothing);
    expect(find.text('↻ Morning digest'), findsOneWidget);
    expect(find.text('Run log ›'), findsOneWidget);
    expect(find.text('Open run log'), findsNothing);
    expect(find.byKey(const Key('web-mark')), findsNothing);
  });

  testWidgets('an older Report says Routine, a tainted one wears the mark, an empty one shows its headline',
      (tester) async {
    await pumpCard(
        tester,
        cardMessage('report',
            jsonEncode(routineReport({'routine_name': null, 'tainted': true, 'text': ''}))),
        (_) => FakeAdapter.json({}));
    expect(find.text('↻ Routine'), findsOneWidget);
    expect(find.byKey(const Key('web-mark')), findsOneWidget);
    expect(find.text('Only the server keeps this'), findsOneWidget);
  });

  group('nextRunWords', () {
    final now = DateTime.utc(2026, 10, 21, 8); // Wednesday, 10:00 in Madrid

    test('says how long while it is today', () {
      expect(nextRunWords('2026-10-21T08:30:00Z', now), 'in 30 min');
      expect(nextRunWords('2026-10-21T11:00:00Z', now), 'in 3 h');
      expect(nextRunWords('2026-10-21T13:07+02:00', now), 'in 3 h');
    });

    test('then tomorrow, the weekday, or the date, with Madrid time', () {
      expect(nextRunWords('2026-10-22T07:00:00Z', now), 'tomorrow 09:00');
      expect(nextRunWords('2026-10-24T07:00:00Z', now), 'Sat 09:00');
      expect(nextRunWords('2026-11-05T08:00:00Z', now), 'Thu 5 Nov 09:00');
    });

    test('a passed time reads now, and nothing reads as nothing', () {
      expect(nextRunWords('2026-10-21T07:59:00Z', now), 'now');
      expect(nextRunWords('', now), '');
      expect(nextRunWords(null, now), '');
      expect(nextRunWords('not a time', now), '');
    });
  });
}
