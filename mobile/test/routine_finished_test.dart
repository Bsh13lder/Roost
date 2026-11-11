import 'package:flutter_test/flutter_test.dart';
import 'package:roost_mobile/routines/routines_repo.dart';

import 'cards_test.dart' show cardMessage, pumpCard;
import 'fake_adapter.dart';

const _text =
    "Finished routine · Watch physio: The appointment is booked. I'll delete it in 7 days.";
const _body =
    '{"routine_id":"r1","name":"Watch physio","reason":"The appointment is booked",'
    '"delete_at":"2026-11-18T08:00:00+00:00","text":"$_text"}';

void main() {
  testWidgets('a Finished routine line shows Resume and Delete now, and Resume resumes it',
      (tester) async {
    final adapter =
        await pumpCard(tester, cardMessage('routine_finished', _body), (o) {
      expect(o.method, 'POST');
      expect(o.path, '/api/routines/r1/resume');
      return FakeAdapter.json({'id': 'r1', 'enabled': true, 'finished': null});
    });
    expect(find.text(_text), findsOneWidget);
    expect(find.text('Resume'), findsOneWidget);
    expect(find.text('Delete now'), findsOneWidget);
    await tester.tap(find.text('Resume'));
    await tester.pumpAndSettle();
    expect(adapter.requests, hasLength(1));
    expect(find.text('Resumed routine · Watch physio'), findsOneWidget);
    expect(find.text('Resume'), findsNothing);
  });

  testWidgets('Delete now deletes it at once', (tester) async {
    final adapter =
        await pumpCard(tester, cardMessage('routine_finished', _body), (o) {
      expect(o.method, 'DELETE');
      expect(o.path, '/api/routines/r1');
      return FakeAdapter.json(null, status: 204);
    });
    await tester.tap(find.text('Delete now'));
    await tester.pumpAndSettle();
    expect(adapter.requests, hasLength(1));
    expect(find.text('Deleted routine · Watch physio'), findsOneWidget);
  });

  testWidgets('a routine already gone says so', (tester) async {
    await pumpCard(tester, cardMessage('routine_finished', _body),
        (o) => FakeAdapter.json({'detail': 'Routine not found'}, status: 404));
    await tester.tap(find.text('Delete now'));
    await tester.pumpAndSettle();
    expect(find.text('That routine is already gone.'), findsOneWidget);
  });

  test('finishedLine says the reason and the delete date', () {
    final line = finishedLine({
      'finished': {
        'at': '2026-11-11T08:00:00+00:00',
        'reason': 'booked',
        'delete_at': '2026-11-18T08:00:00+00:00',
      },
    });
    expect(line, startsWith('Finished: booked · deleted '));
    expect(line, contains('18 Nov'));
    expect(finishedLine({'finished': null}), isNull);
  });
}
