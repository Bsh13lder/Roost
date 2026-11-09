import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/api/models.dart';
import 'package:roost_mobile/chat/cards/card_router.dart';
import 'package:roost_mobile/chat/cards/english_fix_card.dart';
import 'package:roost_mobile/chat/english_fix.dart';
import 'package:roost_mobile/features/chat/message_view.dart';
import 'package:roost_mobile/theme/tokens.dart';

Message _line(String body) => Message(
      id: 'f1',
      threadId: 't1',
      role: 'activity',
      body: body,
      seq: 5,
      createdAt: '2026-10-22T12:19:00+00:00',
      kind: 'english_fix',
    );

final _body = jsonEncode({
  'message_id': 'u1',
  'said': 'I has two cat',
  'corrected': 'I have two cats',
  'fixes': [
    {'wrong': 'has', 'right': 'have'},
    {'wrong': 'cat', 'right': 'cats'},
    {'wrong': 'teh', 'right': 'the'},
  ],
});

/// Every span of the rich sentence: (text, colour, struck through).
List<(String, Color?, bool)> spans(WidgetTester tester) {
  final rich = tester.widget<Text>(find.byKey(const Key('english-fix-sentence')));
  final out = <(String, Color?, bool)>[];
  rich.textSpan!.visitChildren((span) {
    if (span is TextSpan && span.text != null) {
      out.add((span.text!, span.style?.color, span.style?.decoration == TextDecoration.lineThrough));
    }
    return true;
  });
  return out;
}

void main() {
  testWidgets('the card: the corrected sentence, wrong words struck in danger, right words in ok, You said',
      (tester) async {
    await tester.pumpWidget(MaterialApp(home: Scaffold(body: cardFor(_line(_body))!)));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('english-fix-f1')), findsOneWidget);
    expect(spans(tester), [
      ('I ', Tokens.text, false),
      ('has', Tokens.danger, true),
      (' ', null, false),
      ('have', Tokens.ok, false),
      (' two ', Tokens.text, false),
      ('cat', Tokens.danger, true),
      (' ', null, false),
      ('cats', Tokens.ok, false),
    ]);
    expect(find.text('teh → the'), findsOneWidget);
    expect(find.text('You said: I has two cat'), findsOneWidget);
  });

  testWidgets('the same line through MessageView is the card, not a quiet line', (tester) async {
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(body: MessageView(message: _line(_body), text: _body)),
    ));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('english-fix-f1')), findsOneWidget);
    expect(find.text('Open this on the web for now.'), findsNothing);
    expect(find.textContaining('{'), findsNothing);
  });

  testWidgets('an unreadable body draws nothing at all', (tester) async {
    await tester.pumpWidget(MaterialApp(home: Scaffold(body: cardFor(_line('junk'))!)));
    await tester.pumpAndSettle();
    expect(find.byType(EnglishFixCard), findsOneWidget);
    expect(find.byKey(const Key('english-fix-sentence')), findsNothing);
    expect(find.textContaining('junk'), findsNothing);
  });

  testWidgets('EnglishFixText alone (the call screen) centres and shows no You said line', (tester) async {
    final fix = parseEnglishFix(_body)!;
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(body: EnglishFixText(fix, textAlign: TextAlign.center, baseColor: Tokens.textFaint)),
    ));
    expect(find.text('You said: I has two cat'), findsNothing);
    expect(spans(tester).first, ('I ', Tokens.textFaint, false));
    expect(tester.widget<Text>(find.byKey(const Key('english-fix-sentence'))).textAlign, TextAlign.center);
  });
}
